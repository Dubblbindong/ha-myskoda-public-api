"""Data update coordinator for the MyŠkoda Public API integration."""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    MySkodaApiError,
    MySkodaAuthError,
    MySkodaOperationError,
    MySkodaPublicApi,
    MySkodaRateLimitError,
    MySkodaVehicleBusyError,
    RateLimitInfo,
    VehicleData,
)
from .const import (
    API_KEY_EXPIRY_WARNING_DAYS,
    CONF_SCAN_INTERVAL,
    CONF_SPIN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    POST_COMMAND_REFRESH_DELAYS,
    RATE_LIMIT_RESERVE,
)
from .helpers import get_in, has_operation, parse_timestamp

_LOGGER = logging.getLogger(__name__)

type MySkodaConfigEntry = ConfigEntry[MySkodaVehicleCoordinator]


class MySkodaVehicleCoordinator(DataUpdateCoordinator[VehicleData]):
    """Fetch the state of one vehicle, respecting the per-VIN rate limit."""

    config_entry: MySkodaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MySkodaConfigEntry,
        api: MySkodaPublicApi,
        vin: str,
    ) -> None:
        """Initialise the coordinator."""
        self.api = api
        self.vin = vin
        self._configured_interval = timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._post_command_unsub: CALLBACK_TYPE | None = None
        self._post_command_section: str | None = None
        self._post_command_time: datetime | None = None
        self._post_command_attempt = 0
        self._issue_id = f"api_key_expiring_{entry.entry_id}"
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {vin}",
            update_interval=self._configured_interval,
        )

    # ------------------------------------------------------------------ properties

    @property
    def vehicle(self) -> dict:
        """Return the vehicle part of the last response."""
        return self.data.vehicle if self.data else {}

    @property
    def vehicle_name(self) -> str:
        """Return the user-defined vehicle name, falling back to the VIN."""
        return self.vehicle.get("name") or self.vin

    @property
    def spin(self) -> str | None:
        """Return the configured S-PIN, if any."""
        return self.config_entry.options.get(CONF_SPIN) or None

    @property
    def rate_limit(self) -> RateLimitInfo | None:
        """Return the most recent rate-limit information."""
        return self.api.last_rate_limit

    def supports_operation(self, name: str) -> bool:
        """Return True if the vehicle lists the remote operation."""
        return has_operation(self.vehicle, name)

    # ------------------------------------------------------------------ polling

    async def _async_update_data(self) -> VehicleData:
        """Fetch the vehicle state."""
        try:
            data = await self.api.async_get_vehicle(self.vin)
        except MySkodaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MySkodaRateLimitError as err:
            delay = self._backoff_seconds(err.retry_after)
            self.update_interval = timedelta(seconds=delay)
            raise UpdateFailed(
                f"API rate limit exceeded, next attempt in {delay} s"
            ) from err
        except MySkodaApiError as err:
            self.update_interval = self._configured_interval
            raise UpdateFailed(str(err)) from err

        self._adjust_interval(data.rate_limit)
        self._check_api_key_expiry(data.api_key_expires_at)
        if data.errors:
            _LOGGER.debug(
                "Vehicle %s: partial data, errors reported by the API: %s",
                self.vin,
                ", ".join(sorted(data.error_types)),
            )
        return data

    def _backoff_seconds(self, retry_after: int | None) -> int:
        """Return how long to wait after a 429 response."""
        candidates = [int(self._configured_interval.total_seconds())]
        if retry_after:
            candidates.append(retry_after + 5)
        rate_limit = self.api.last_rate_limit
        if rate_limit and rate_limit.reset_seconds:
            candidates.append(rate_limit.reset_seconds + 5)
        return max(candidates)

    def _adjust_interval(self, rate_limit: RateLimitInfo | None) -> None:
        """Slow down polling when the quota is almost used up."""
        interval = self._configured_interval
        if (
            rate_limit is not None
            and rate_limit.remaining is not None
            and rate_limit.remaining <= RATE_LIMIT_RESERVE
            and rate_limit.reset_seconds
        ):
            wait = timedelta(seconds=rate_limit.reset_seconds + 5)
            if wait > interval:
                interval = wait
                _LOGGER.debug(
                    "Vehicle %s: only %s API requests left, next poll in %s",
                    self.vin,
                    rate_limit.remaining,
                    wait,
                )
        self.update_interval = interval

    def _check_api_key_expiry(self, expires_at: datetime | None) -> None:
        """Raise a repair issue when the API key is about to expire."""
        if expires_at is None:
            return
        remaining = expires_at - dt_util.utcnow()
        if remaining <= timedelta(days=API_KEY_EXPIRY_WARNING_DAYS):
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="api_key_expiring",
                translation_placeholders={
                    "name": self.config_entry.title,
                    "expires_at": dt_util.as_local(expires_at).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                },
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)

    # ------------------------------------------------------------------ commands

    async def async_execute_command(
        self, command: Awaitable[None], *, section: str | None = None
    ) -> None:
        """Run a remote command, translate errors and schedule follow-up refreshes.

        ``section`` names the part of the vehicle data the command affects; its
        ``carCapturedTimestamp`` tells whether the vehicle has reported since.
        """
        try:
            await command
        except MySkodaAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
            ) from err
        except MySkodaVehicleBusyError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="vehicle_busy",
                translation_placeholders={"retry_after": str(err.retry_after or 60)},
            ) from err
        except MySkodaRateLimitError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="rate_limited",
                translation_placeholders={"retry_after": str(err.retry_after or 0)},
            ) from err
        except MySkodaOperationError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="operation_rejected",
                translation_placeholders={"detail": err.detail or str(err)},
            ) from err
        except MySkodaApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"detail": err.detail or str(err)},
            ) from err
        self.async_schedule_post_command_refresh(section)

    def async_schedule_post_command_refresh(self, section: str | None = None) -> None:
        """Re-fetch the state shortly after a command.

        The API acknowledges commands before the vehicle executes them. The first
        refresh happens after a few seconds; a second one follows only if the vehicle
        has not reported fresh data for ``section`` by then.
        """
        self._cancel_post_command_refresh()
        self._post_command_section = section
        self._post_command_time = dt_util.utcnow()
        self._post_command_attempt = 0
        self._schedule_next_post_command_refresh()

    def _schedule_next_post_command_refresh(self) -> None:
        delay = POST_COMMAND_REFRESH_DELAYS[self._post_command_attempt]
        self._post_command_unsub = async_call_later(
            self.hass, delay, self._async_post_command_refresh
        )

    def _cancel_post_command_refresh(self) -> None:
        if self._post_command_unsub is not None:
            self._post_command_unsub()
            self._post_command_unsub = None

    async def _async_post_command_refresh(self, _now: datetime) -> None:
        self._post_command_unsub = None
        self._post_command_attempt += 1
        rate_limit = self.api.last_rate_limit
        if (
            rate_limit is not None
            and rate_limit.remaining is not None
            and rate_limit.remaining <= 1
        ):
            _LOGGER.debug(
                "Vehicle %s: skipping post-command refresh, quota exhausted", self.vin
            )
            return
        await self.async_refresh()
        if (
            self._post_command_attempt >= len(POST_COMMAND_REFRESH_DELAYS)
            or self._vehicle_reported_since_command()
        ):
            return
        _LOGGER.debug(
            "Vehicle %s: %s not updated by the vehicle yet, refreshing again",
            self.vin,
            self._post_command_section,
        )
        self._schedule_next_post_command_refresh()

    def _vehicle_reported_since_command(self) -> bool:
        """Return True if the affected section carries data captured after the command."""
        if self._post_command_section is None or self._post_command_time is None:
            return True
        captured = parse_timestamp(
            get_in(self.vehicle, f"{self._post_command_section}.carCapturedTimestamp")
        )
        return captured is not None and captured >= self._post_command_time

    async def async_shutdown(self) -> None:
        """Cancel pending timers and shut down."""
        self._cancel_post_command_refresh()
        await super().async_shutdown()
