"""Config flow for the MyŠkoda Public API integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    MySkodaApiError,
    MySkodaAuthError,
    MySkodaConnectionError,
    MySkodaNotFoundError,
    MySkodaPublicApi,
    MySkodaRateLimitError,
)
from .const import (
    API_DOCS_URL,
    API_KEY_MANAGEMENT_URL,
    CONF_REMOVE_SPIN,
    CONF_SCAN_INTERVAL,
    CONF_SPIN,
    CONF_VIN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# 17 characters, no I, O or Q.
VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

API_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
VIN_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="off")
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): API_KEY_SELECTOR,
        vol.Required(CONF_VIN): VIN_SELECTOR,
    }
)
STEP_API_KEY_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): API_KEY_SELECTOR})

PLACEHOLDERS = {"api_keys_url": API_KEY_MANAGEMENT_URL, "docs_url": API_DOCS_URL}


def normalize_vin(value: str) -> str:
    """Return the VIN in upper case without whitespace."""
    return "".join(value.split()).upper()


async def _async_validate(hass: HomeAssistant, api_key: str, vin: str) -> str:
    """Check key and VIN with a single, lightweight request; return the vehicle name."""
    api = MySkodaPublicApi(async_get_clientsession(hass), api_key)
    data = await api.async_get_vehicle(vin, include=("info",))
    return data.vehicle.get("name") or vin


def _error_code(err: MySkodaApiError) -> str:
    """Map an API error to a config-flow error code."""
    if isinstance(err, MySkodaAuthError):
        return "invalid_auth"
    if isinstance(err, MySkodaNotFoundError):
        return "vehicle_not_found"
    if isinstance(err, MySkodaRateLimitError):
        return "rate_limited"
    if isinstance(err, MySkodaConnectionError):
        return "cannot_connect"
    return "unknown"


class MySkodaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow: one entry per vehicle."""

    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MySkodaOptionsFlow:
        """Return the options flow."""
        return MySkodaOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for API key and VIN."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            vin = normalize_vin(user_input[CONF_VIN])
            if not VIN_PATTERN.match(vin):
                errors[CONF_VIN] = "invalid_vin"
            else:
                await self.async_set_unique_id(vin)
                self._abort_if_unique_id_configured()
                try:
                    name = await _async_validate(self.hass, api_key, vin)
                except MySkodaApiError as err:
                    _LOGGER.debug("Validation failed: %s", err)
                    errors["base"] = _error_code(err)
                else:
                    return self.async_create_entry(
                        title=name,
                        data={CONF_API_KEY: api_key, CONF_VIN: vin},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders=PLACEHOLDERS,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication after the key expired or was revoked."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                await _async_validate(self.hass, api_key, entry.data[CONF_VIN])
            except MySkodaApiError as err:
                _LOGGER.debug("Re-authentication failed: %s", err)
                errors["base"] = _error_code(err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_API_KEY_SCHEMA,
            errors=errors,
            description_placeholders={**PLACEHOLDERS, "name": entry.title},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow replacing the API key from the integration page."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                await _async_validate(self.hass, api_key, entry.data[CONF_VIN])
            except MySkodaApiError as err:
                _LOGGER.debug("Reconfiguration failed: %s", err)
                errors["base"] = _error_code(err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=STEP_API_KEY_SCHEMA,
            errors=errors,
            description_placeholders={**PLACEHOLDERS, "name": entry.title},
        )


class MySkodaOptionsFlow(OptionsFlow):
    """Options: polling interval and the S-PIN for the auxiliary heater."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the options."""
        current = self.config_entry.options
        if user_input is not None:
            options = dict(current)
            options[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            spin = (user_input.get(CONF_SPIN) or "").strip()
            if user_input.get(CONF_REMOVE_SPIN):
                options.pop(CONF_SPIN, None)
            elif spin:
                options[CONF_SPIN] = spin
            return self.async_create_entry(data=options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=60,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(CONF_SPIN): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_REMOVE_SPIN, default=False): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "spin_state": "configured" if current.get(CONF_SPIN) else "not configured",
            },
        )
