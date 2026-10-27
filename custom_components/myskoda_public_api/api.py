"""Async client for the MyŠkoda Public API.

This module deliberately has no Home Assistant dependencies so it can be exercised
on its own, outside of Home Assistant.

API documentation: https://public.api.connect.skoda-auto.cz/docs
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import aiohttp
from multidict import CIMultiDictProxy

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://public.api.connect.skoda-auto.cz"
PROBLEM_PREFIX = "https://public.api.connect.skoda-auto.cz/problems/"

PROBLEM_API_KEY_EXPIRED = "api-key-expired"
PROBLEM_API_KEY_NOT_AUTHORIZED = "api-key-not-authorized"
PROBLEM_OPERATION_NOT_AUTHORIZED = "operation-not-authorized"
PROBLEM_OPERATION_NOT_SUPPORTED = "operation-not-supported"
PROBLEM_OPERATION_DISABLED = "operation-disabled"
PROBLEM_RATE_LIMIT_EXCEEDED = "rate-limit-exceeded"
PROBLEM_VEHICLE_NOT_ACCEPTING_REQUESTS = "vehicle-not-accepting-requests"

HEADER_API_KEY = "X-API-Key"
HEADER_API_KEY_EXPIRES_AT = "X-API-Key-Expires-At"
HEADER_RATE_LIMIT_LIMIT = "RateLimit-Limit"
HEADER_RATE_LIMIT_REMAINING = "RateLimit-Remaining"
HEADER_RATE_LIMIT_RESET = "RateLimit-Reset"
HEADER_RETRY_AFTER = "Retry-After"

INCLUDE_PARTS = (
    "info",
    "status",
    "fuelStatus",
    "odometer",
    "parkingPosition",
    "airConditioning",
    "auxiliaryHeating",
    "activeVentilation",
    "charging",
    "chargingProfiles",
    "operations",
)


class MySkodaApiError(Exception):
    """Base error raised by the API client."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        problem_type: str | None = None,
        title: str | None = None,
        detail: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Initialise the error."""
        super().__init__(message)
        self.status = status
        self.problem_type = problem_type
        self.title = title
        self.detail = detail
        self.retry_after = retry_after


class MySkodaConnectionError(MySkodaApiError):
    """Network problem or timeout while talking to the API."""


class MySkodaAuthError(MySkodaApiError):
    """The API key is invalid, expired or not authorised for the request."""


class MySkodaNotFoundError(MySkodaApiError):
    """The requested resource (vehicle, profile) does not exist."""


class MySkodaRateLimitError(MySkodaApiError):
    """The rate limit of the API key has been exceeded."""


class MySkodaVehicleBusyError(MySkodaApiError):
    """The vehicle declined the operation; it can be retried later."""


class MySkodaOperationError(MySkodaApiError):
    """The vehicle refused, does not support or has disabled the operation."""


class MySkodaServerError(MySkodaApiError):
    """The API returned a 5xx response."""


@dataclass(frozen=True)
class RateLimitInfo:
    """Rate-limit information taken from the response headers."""

    limit: int | None
    remaining: int | None
    reset_seconds: int | None
    received_at: datetime

    @property
    def reset_at(self) -> datetime | None:
        """Return the moment the quota replenishes."""
        if self.reset_seconds is None:
            return None
        return self.received_at + timedelta(seconds=self.reset_seconds)


@dataclass
class VehicleData:
    """Vehicle response together with the metadata from the response headers."""

    vehicle: dict[str, Any]
    errors: list[dict[str, Any]] = field(default_factory=list)
    rate_limit: RateLimitInfo | None = None
    api_key_expires_at: datetime | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def vin(self) -> str | None:
        """Return the VIN of the vehicle."""
        return self.vehicle.get("vin")

    @property
    def error_types(self) -> set[str]:
        """Return the machine-readable error types of the response."""
        return {
            err["type"]
            for err in self.errors
            if isinstance(err, Mapping) and isinstance(err.get("type"), str)
        }


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def short_problem_type(problem_type: str | None) -> str | None:
    """Return the short name of a problem type URI (``api-key-expired``)."""
    if not problem_type:
        return None
    if problem_type.startswith(PROBLEM_PREFIX):
        return problem_type[len(PROBLEM_PREFIX) :]
    return problem_type


class MySkodaPublicApi:
    """Minimal client for the MyŠkoda Public API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        request_timeout: float = 30.0,
    ) -> None:
        """Initialise the client with an existing aiohttp session."""
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self.last_rate_limit: RateLimitInfo | None = None
        self.api_key_expires_at: datetime | None = None

    def set_api_key(self, api_key: str) -> None:
        """Replace the API key, e.g. after re-authentication."""
        self._api_key = api_key

    # ------------------------------------------------------------------ requests

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Any | None = None,
    ) -> tuple[Any, CIMultiDictProxy[str]]:
        """Perform a request and return the decoded body and the response headers."""
        url = f"{self._base_url}{path}"
        headers = {
            HEADER_API_KEY: self._api_key,
            "Accept": "application/json, application/problem+json",
        }
        _LOGGER.debug("%s %s", method, path)
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
                timeout=self._timeout,
            ) as response:
                self._read_common_headers(response.headers)
                if 200 <= response.status < 300:
                    body: Any = None
                    if response.status != 204 and response.content_length != 0:
                        try:
                            body = await response.json(content_type=None)
                        except (aiohttp.ContentTypeError, ValueError):
                            body = None
                    return body, response.headers
                problem = await self._read_problem(response)
                raise self._error_from_response(
                    response.status, problem, response.headers
                )
        except asyncio.TimeoutError as err:
            raise MySkodaConnectionError(
                f"Timeout while calling {method} {path}"
            ) from err
        except aiohttp.ClientError as err:
            raise MySkodaConnectionError(
                f"Connection error while calling {method} {path}: {err}"
            ) from err

    def _read_common_headers(self, headers: CIMultiDictProxy[str]) -> None:
        """Remember rate-limit and key-expiry information from the headers."""
        if any(
            header in headers
            for header in (
                HEADER_RATE_LIMIT_LIMIT,
                HEADER_RATE_LIMIT_REMAINING,
                HEADER_RATE_LIMIT_RESET,
            )
        ):
            self.last_rate_limit = RateLimitInfo(
                limit=_parse_int(headers.get(HEADER_RATE_LIMIT_LIMIT)),
                remaining=_parse_int(headers.get(HEADER_RATE_LIMIT_REMAINING)),
                reset_seconds=_parse_int(headers.get(HEADER_RATE_LIMIT_RESET)),
                received_at=datetime.now(timezone.utc),
            )
        expires_at = _parse_datetime(headers.get(HEADER_API_KEY_EXPIRES_AT))
        if expires_at is not None:
            self.api_key_expires_at = expires_at

    @staticmethod
    async def _read_problem(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            body = await response.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError, aiohttp.ClientError):
            return {}
        return body if isinstance(body, dict) else {}

    @staticmethod
    def _error_from_response(
        status: int, problem: Mapping[str, Any], headers: CIMultiDictProxy[str]
    ) -> MySkodaApiError:
        """Map an error response to the matching exception."""
        problem_type = short_problem_type(problem.get("type"))
        title = problem.get("title") or "Request failed"
        detail = problem.get("detail")
        retry_after = _parse_int(headers.get(HEADER_RETRY_AFTER))
        message = f"{title} ({status})"
        if problem_type and problem_type != "about:blank":
            message = f"{message} [{problem_type}]"
        if detail:
            message = f"{message}: {detail}"
        kwargs: dict[str, Any] = {
            "status": status,
            "problem_type": problem_type,
            "title": title,
            "detail": detail,
            "retry_after": retry_after,
        }
        if status == 401:
            return MySkodaAuthError(message, **kwargs)
        if status == 403:
            if problem_type == PROBLEM_OPERATION_NOT_AUTHORIZED:
                return MySkodaOperationError(message, **kwargs)
            return MySkodaAuthError(message, **kwargs)
        if status == 404:
            return MySkodaNotFoundError(message, **kwargs)
        if status in (412, 422):
            return MySkodaOperationError(message, **kwargs)
        if status == 429:
            if problem_type == PROBLEM_VEHICLE_NOT_ACCEPTING_REQUESTS:
                return MySkodaVehicleBusyError(message, **kwargs)
            return MySkodaRateLimitError(message, **kwargs)
        if status >= 500:
            return MySkodaServerError(message, **kwargs)
        return MySkodaApiError(message, **kwargs)

    # ------------------------------------------------------------------ vehicle data

    async def async_get_vehicle(
        self, vin: str, include: Iterable[str] | None = None
    ) -> VehicleData:
        """Return the vehicle and its current state.

        ``include`` limits the response to the given parts. When omitted, all parts the
        vehicle supports are returned without ``*_UNSUPPORTED`` errors.
        """
        params: dict[str, str] | None = None
        if include:
            params = {"include": ",".join(include)}
        body, headers = await self._request(
            "GET", f"/api/v1/vehicles/{vin}", params=params
        )
        if not isinstance(body, dict) or not isinstance(body.get("vehicle"), dict):
            raise MySkodaApiError("Unexpected response body for vehicle request")
        errors = body.get("errors")
        return VehicleData(
            vehicle=body["vehicle"],
            errors=[err for err in errors if isinstance(err, dict)]
            if isinstance(errors, list)
            else [],
            rate_limit=self.last_rate_limit,
            api_key_expires_at=_parse_datetime(headers.get(HEADER_API_KEY_EXPIRES_AT))
            or self.api_key_expires_at,
        )

    # ------------------------------------------------------------------ charging

    async def async_start_charging(self, vin: str) -> None:
        """Start charging."""
        await self._request("POST", f"/api/v1/vehicles/{vin}/charging/start")

    async def async_stop_charging(self, vin: str) -> None:
        """Stop charging."""
        await self._request("POST", f"/api/v1/vehicles/{vin}/charging/stop")

    async def async_set_charging_limit(
        self, vin: str, target_state_of_charge: int
    ) -> None:
        """Set the charging limit (target state of charge in percent)."""
        await self._request(
            "PUT",
            f"/api/v1/vehicles/{vin}/charging/limit",
            json={"targetStateOfChargeInPercent": int(target_state_of_charge)},
        )

    async def async_set_charge_mode(self, vin: str, charge_mode: str) -> None:
        """Change the charge mode (MANUAL, TIMER, ...)."""
        await self._request(
            "PUT",
            f"/api/v1/vehicles/{vin}/charging/mode",
            json={"chargeMode": charge_mode},
        )

    async def async_update_charging_profile(
        self, vin: str, profile_id: int, profile: Mapping[str, Any]
    ) -> None:
        """Update a charging profile (saved charging location)."""
        await self._request(
            "PUT",
            f"/api/v1/vehicles/{vin}/charging-profiles/{profile_id}",
            json=dict(profile),
        )

    # ------------------------------------------------------------------ climate

    async def async_start_air_conditioning(
        self,
        vin: str,
        *,
        target_temperature_celsius: float | None = None,
        without_external_power: bool | None = None,
    ) -> None:
        """Start the air conditioning."""
        payload: dict[str, Any] = {}
        if target_temperature_celsius is not None:
            payload["targetTemperature"] = {
                "value": float(target_temperature_celsius),
                "unit": "CELSIUS",
            }
        if without_external_power is not None:
            payload["airConditioningWithoutExternalPower"] = bool(
                without_external_power
            )
        await self._request(
            "POST", f"/api/v1/vehicles/{vin}/air-conditioning/start", json=payload
        )

    async def async_stop_air_conditioning(self, vin: str) -> None:
        """Stop the air conditioning."""
        await self._request("POST", f"/api/v1/vehicles/{vin}/air-conditioning/stop")

    async def async_start_auxiliary_heating(
        self,
        vin: str,
        *,
        spin: str,
        duration_seconds: int | None = None,
        start_mode: str | None = None,
        target_temperature_celsius: float | None = None,
    ) -> None:
        """Start the auxiliary heater. Requires the S-PIN of the MyŠkoda account."""
        payload: dict[str, Any] = {"spin": spin}
        if duration_seconds is not None:
            payload["durationInSeconds"] = int(duration_seconds)
        if start_mode is not None:
            payload["startMode"] = start_mode
        if target_temperature_celsius is not None:
            payload["targetTemperature"] = {
                "value": float(target_temperature_celsius),
                "unit": "CELSIUS",
            }
        await self._request(
            "POST", f"/api/v1/vehicles/{vin}/auxiliary-heating/start", json=payload
        )

    async def async_stop_auxiliary_heating(self, vin: str) -> None:
        """Stop the auxiliary heater."""
        await self._request("POST", f"/api/v1/vehicles/{vin}/auxiliary-heating/stop")

    async def async_start_active_ventilation(self, vin: str) -> None:
        """Start the active ventilation."""
        await self._request("POST", f"/api/v1/vehicles/{vin}/active-ventilation/start")

    async def async_stop_active_ventilation(self, vin: str) -> None:
        """Stop the active ventilation."""
        await self._request("POST", f"/api/v1/vehicles/{vin}/active-ventilation/stop")
