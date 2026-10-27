"""Diagnostics support for the MyŠkoda Public API integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .const import CONF_SPIN, CONF_VIN
from .coordinator import MySkodaConfigEntry

# "name" is redacted explicitly on the vehicle only, so that operation and
# charging-profile names stay readable.
TO_REDACT = {
    CONF_API_KEY,
    CONF_SPIN,
    CONF_VIN,
    "licensePlate",
    "renderUrl",
    "latitude",
    "longitude",
    "formattedAddress",
    "title",
    "unique_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MySkodaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a vehicle entry, with personal data redacted."""
    coordinator = entry.runtime_data
    data = coordinator.data
    rate_limit = coordinator.rate_limit
    vehicle = coordinator.vehicle

    return {
        "entry": async_redact_data(
            {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            TO_REDACT,
        ),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "supported_operations": [
                op.get("name")
                for op in vehicle.get("operations", [])
                if isinstance(op, dict)
            ],
            "sections": sorted(
                key for key, value in vehicle.items() if isinstance(value, dict)
            ),
        },
        "rate_limit": {
            "limit": rate_limit.limit,
            "remaining": rate_limit.remaining,
            "reset_seconds": rate_limit.reset_seconds,
            "received_at": rate_limit.received_at.isoformat(),
        }
        if rate_limit
        else None,
        "api_key_expires_at": data.api_key_expires_at.isoformat()
        if data and data.api_key_expires_at
        else None,
        "errors": data.errors if data else None,
        "vehicle": async_redact_data({**vehicle, "name": "**REDACTED**"}, TO_REDACT)
        if data
        else None,
    }
