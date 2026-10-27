"""Small helpers shared by the platforms of the MyŠkoda Public API integration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.const import UnitOfTemperature
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

UNKNOWN_VALUES = {"UNKNOWN", "UNSUPPORTED"}


def get_in(data: Mapping[str, Any] | None, path: str, default: Any = None) -> Any:
    """Return the value at a dotted path inside nested mappings."""
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def enum_value(value: Any) -> str | None:
    """Normalise an API enum value to a lower-case state, treating UNKNOWN as None."""
    if not isinstance(value, str) or value in UNKNOWN_VALUES:
        return None
    return value.lower()


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp from the API into an aware datetime."""
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


def temperature_to_celsius(target: Mapping[str, Any] | None) -> float | None:
    """Convert a ``TargetTemperature`` object from the API to degrees Celsius."""
    if not isinstance(target, Mapping):
        return None
    value = target.get("value")
    if not isinstance(value, (int, float)):
        return None
    if target.get("unit") == "FAHRENHEIT":
        return round(
            TemperatureConverter.convert(
                float(value), UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
            ),
            1,
        )
    return float(value)


def has_operation(vehicle: Mapping[str, Any], name: str) -> bool:
    """Return True if the vehicle lists the given remote operation."""
    operations = vehicle.get("operations")
    if not isinstance(operations, list):
        return False
    return any(isinstance(op, Mapping) and op.get("name") == name for op in operations)


def section_present(vehicle: Mapping[str, Any], section: str | None) -> bool:
    """Return True if a part of the vehicle data is present in the response."""
    if section is None:
        return True
    return isinstance(vehicle.get(section), Mapping)
