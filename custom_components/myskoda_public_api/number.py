"""Number entity (charging limit) for the MyŠkoda Public API integration."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import OP_SET_CHARGING_LIMIT, SECTION_CHARGING
from .coordinator import MySkodaConfigEntry, MySkodaVehicleCoordinator
from .entity import MySkodaEntity
from .helpers import get_in, section_present

PARALLEL_UPDATES = 1

# Vehicles typically accept 50-100 % in steps of 10 and reject other values.
CHARGING_LIMIT = NumberEntityDescription(
    key="charging_limit",
    translation_key="charging_limit",
    native_min_value=50.0,
    native_max_value=100.0,
    native_step=10.0,
    native_unit_of_measurement=PERCENTAGE,
    device_class=NumberDeviceClass.BATTERY,
    mode=NumberMode.SLIDER,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MySkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the charging-limit entity when the vehicle supports it."""
    coordinator = entry.runtime_data
    if section_present(
        coordinator.vehicle, SECTION_CHARGING
    ) and coordinator.supports_operation(OP_SET_CHARGING_LIMIT):
        async_add_entities([MySkodaChargingLimit(coordinator)])


class MySkodaChargingLimit(MySkodaEntity, NumberEntity):
    """Target state of charge."""

    entity_description = CHARGING_LIMIT

    def __init__(self, coordinator: MySkodaVehicleCoordinator) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, CHARGING_LIMIT.key, SECTION_CHARGING)

    @property
    def native_value(self) -> float | None:
        """Return the charging limit."""
        if self._optimistic_value is not None:
            return self._optimistic_value
        return get_in(self.vehicle, f"{SECTION_CHARGING}.settings.targetStateOfChargeInPercent")

    async def async_set_native_value(self, value: float) -> None:
        """Send the new charging limit to the vehicle."""
        target = int(round(value))
        await self.coordinator.async_execute_command(
            self.coordinator.api.async_set_charging_limit(self.coordinator.vin, target),
            section=SECTION_CHARGING,
        )
        self._set_optimistic(float(target))
