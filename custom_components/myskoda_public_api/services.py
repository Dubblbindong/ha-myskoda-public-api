"""Actions (services) of the MyŠkoda Public API integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    DOMAIN,
    MAX_TARGET_TEMPERATURE,
    MIN_TARGET_TEMPERATURE,
    OP_START_AIR_CONDITIONING,
    OP_START_AUXILIARY_HEATING,
    SECTION_AIR_CONDITIONING,
    SECTION_AUXILIARY_HEATING,
)
from .coordinator import MySkodaVehicleCoordinator

ATTR_DEVICE_ID = "device_id"
ATTR_TEMPERATURE = "temperature"
ATTR_WITHOUT_EXTERNAL_POWER = "without_external_power"
ATTR_DURATION = "duration"
ATTR_START_MODE = "start_mode"
ATTR_SPIN = "spin"

SERVICE_START_AIR_CONDITIONING = "start_air_conditioning"
SERVICE_START_AUXILIARY_HEATING = "start_auxiliary_heating"

TEMPERATURE_VALIDATOR = vol.All(
    vol.Coerce(float),
    vol.Range(min=MIN_TARGET_TEMPERATURE, max=MAX_TARGET_TEMPERATURE),
)

START_AIR_CONDITIONING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_TEMPERATURE): TEMPERATURE_VALIDATOR,
        vol.Optional(ATTR_WITHOUT_EXTERNAL_POWER): cv.boolean,
    }
)

START_AUXILIARY_HEATING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
        vol.Optional(ATTR_START_MODE): vol.In(["heating", "ventilation"]),
        vol.Optional(ATTR_TEMPERATURE): TEMPERATURE_VALIDATOR,
        vol.Optional(ATTR_SPIN): cv.string,
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions of the integration."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_AIR_CONDITIONING,
        _async_start_air_conditioning,
        schema=START_AIR_CONDITIONING_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_AUXILIARY_HEATING,
        _async_start_auxiliary_heating,
        schema=START_AUXILIARY_HEATING_SCHEMA,
    )


def _get_coordinator(hass: HomeAssistant, device_id: str) -> MySkodaVehicleCoordinator:
    """Resolve the vehicle coordinator behind a device id."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="device_not_found"
        )
    vins = {identifier[1] for identifier in device.identifiers if identifier[0] == DOMAIN}
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        coordinator = entry.runtime_data
        if isinstance(coordinator, MySkodaVehicleCoordinator) and coordinator.vin in vins:
            return coordinator
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="device_not_loaded"
    )


def _require_operation(coordinator: MySkodaVehicleCoordinator, operation: str) -> None:
    if not coordinator.supports_operation(operation):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="operation_not_supported",
            translation_placeholders={"operation": operation},
        )


async def _async_start_air_conditioning(call: ServiceCall) -> None:
    """Start the air conditioning with an optional target temperature."""
    coordinator = _get_coordinator(call.hass, call.data[ATTR_DEVICE_ID])
    _require_operation(coordinator, OP_START_AIR_CONDITIONING)
    await coordinator.async_execute_command(
        coordinator.api.async_start_air_conditioning(
            coordinator.vin,
            target_temperature_celsius=call.data.get(ATTR_TEMPERATURE),
            without_external_power=call.data.get(ATTR_WITHOUT_EXTERNAL_POWER),
        ),
        section=SECTION_AIR_CONDITIONING,
    )


async def _async_start_auxiliary_heating(call: ServiceCall) -> None:
    """Start the auxiliary heater; needs the S-PIN from the call or the options."""
    coordinator = _get_coordinator(call.hass, call.data[ATTR_DEVICE_ID])
    _require_operation(coordinator, OP_START_AUXILIARY_HEATING)
    spin = (call.data.get(ATTR_SPIN) or coordinator.spin or "").strip()
    if not spin:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="spin_required"
        )
    duration = call.data.get(ATTR_DURATION)
    start_mode = call.data.get(ATTR_START_MODE)
    await coordinator.async_execute_command(
        coordinator.api.async_start_auxiliary_heating(
            coordinator.vin,
            spin=spin,
            duration_seconds=duration * 60 if duration else None,
            start_mode=start_mode.upper() if start_mode else None,
            target_temperature_celsius=call.data.get(ATTR_TEMPERATURE),
        ),
        section=SECTION_AUXILIARY_HEATING,
    )
