"""Climate entity (air conditioning) for the MyŠkoda Public API integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    AC_RUNNING_STATES,
    MAX_TARGET_TEMPERATURE,
    MIN_TARGET_TEMPERATURE,
    OP_START_AIR_CONDITIONING,
    OP_STOP_AIR_CONDITIONING,
    SECTION_AIR_CONDITIONING,
    TARGET_TEMPERATURE_STEP,
)
from .coordinator import MySkodaConfigEntry, MySkodaVehicleCoordinator
from .entity import MySkodaEntity
from .helpers import parse_timestamp, section_present, temperature_to_celsius

PARALLEL_UPDATES = 1

HVAC_ACTIONS = {
    "COOLING": HVACAction.COOLING,
    "HEATING": HVACAction.HEATING,
    "HEATING_AUXILIARY": HVACAction.HEATING,
    "VENTILATION": HVACAction.FAN,
    "OFF": HVACAction.OFF,
    "COMPLETED": HVACAction.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MySkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the climate entity when the vehicle can be climatised remotely."""
    coordinator = entry.runtime_data
    if (
        section_present(coordinator.vehicle, SECTION_AIR_CONDITIONING)
        and coordinator.supports_operation(OP_START_AIR_CONDITIONING)
        and coordinator.supports_operation(OP_STOP_AIR_CONDITIONING)
    ):
        async_add_entities([MySkodaAirConditioning(coordinator)])


class MySkodaAirConditioning(MySkodaEntity, ClimateEntity):
    """Remote air conditioning of the vehicle.

    The API only accepts a target temperature when starting the air conditioning.
    Setting a temperature while it is off therefore stores the value locally and uses
    it on the next start; while it is running the air conditioning is restarted with
    the new target.
    """

    _attr_translation_key = "air_conditioning"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = MIN_TARGET_TEMPERATURE
    _attr_max_temp = MAX_TARGET_TEMPERATURE
    _attr_target_temperature_step = TARGET_TEMPERATURE_STEP

    def __init__(self, coordinator: MySkodaVehicleCoordinator) -> None:
        """Initialise the climate entity."""
        super().__init__(coordinator, "air_conditioning", SECTION_AIR_CONDITIONING)
        self._pending_target: float | None = None

    @property
    def _air_conditioning(self) -> dict[str, Any]:
        return self.vehicle.get(SECTION_AIR_CONDITIONING) or {}

    @property
    def _reported_target(self) -> float | None:
        return temperature_to_celsius(self._air_conditioning.get("targetTemperature"))

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature in °C."""
        if self._pending_target is not None:
            return self._pending_target
        return self._reported_target

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return whether the air conditioning is running."""
        if self._optimistic_value is not None:
            return self._optimistic_value
        state = self._air_conditioning.get("state")
        if state in AC_RUNNING_STATES:
            return HVACMode.HEAT_COOL
        if state in ("OFF", "COMPLETED"):
            return HVACMode.OFF
        return None

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return what the air conditioning is doing right now."""
        return HVAC_ACTIONS.get(self._air_conditioning.get("state"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional details reported by the vehicle."""
        reached_at = parse_timestamp(
            self._air_conditioning.get("estimatedReachOfTargetTemperatureAt")
        )
        return {
            "target_temperature_reached_at": reached_at.isoformat() if reached_at else None,
            "without_external_power": self._air_conditioning.get(
                "airConditioningWithoutExternalPower"
            ),
            "at_unlock": self._air_conditioning.get("airConditioningAtUnlock"),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Store the target temperature and apply it when the AC is running."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        if temperature is not None:
            self._pending_target = float(temperature)
        if hvac_mode is not None:
            await self.async_set_hvac_mode(hvac_mode)
            return
        if temperature is None:
            return
        if self.hvac_mode == HVACMode.HEAT_COOL:
            await self._async_start()
        else:
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Start or stop the air conditioning."""
        if hvac_mode == HVACMode.OFF:
            await self._async_stop()
        else:
            await self._async_start()

    async def async_turn_on(self) -> None:
        """Start the air conditioning."""
        await self._async_start()

    async def async_turn_off(self) -> None:
        """Stop the air conditioning."""
        await self._async_stop()

    async def _async_start(self) -> None:
        await self.coordinator.async_execute_command(
            self.coordinator.api.async_start_air_conditioning(
                self.coordinator.vin,
                target_temperature_celsius=self.target_temperature,
            ),
            section=SECTION_AIR_CONDITIONING,
        )
        self._set_optimistic(HVACMode.HEAT_COOL)

    async def _async_stop(self) -> None:
        await self.coordinator.async_execute_command(
            self.coordinator.api.async_stop_air_conditioning(self.coordinator.vin),
            section=SECTION_AIR_CONDITIONING,
        )
        self._set_optimistic(HVACMode.OFF)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Forget the pending target once the vehicle reports it."""
        if self._pending_target is not None and self._reported_target == self._pending_target:
            self._pending_target = None
        super()._handle_coordinator_update()
