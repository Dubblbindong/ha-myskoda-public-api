"""Select entity (charge mode) for the MyŠkoda Public API integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CHARGE_MODES, OP_SET_CHARGE_MODE, SECTION_CHARGING
from .coordinator import MySkodaConfigEntry, MySkodaVehicleCoordinator
from .entity import MySkodaEntity
from .helpers import enum_value, get_in, section_present

PARALLEL_UPDATES = 1

CHARGE_MODE = SelectEntityDescription(key="charge_mode", translation_key="charge_mode")
DEFAULT_OPTIONS = [mode.lower() for mode in CHARGE_MODES]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MySkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the charge-mode entity when the vehicle supports it."""
    coordinator = entry.runtime_data
    if section_present(
        coordinator.vehicle, SECTION_CHARGING
    ) and coordinator.supports_operation(OP_SET_CHARGE_MODE):
        async_add_entities([MySkodaChargeMode(coordinator)])


class MySkodaChargeMode(MySkodaEntity, SelectEntity):
    """Preferred charge mode of the vehicle."""

    entity_description = CHARGE_MODE

    def __init__(self, coordinator: MySkodaVehicleCoordinator) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, CHARGE_MODE.key, SECTION_CHARGING)

    @property
    def options(self) -> list[str]:
        """Return the modes the vehicle offers, plus the current one if unlisted."""
        available = get_in(self.vehicle, f"{SECTION_CHARGING}.settings.availableChargeModes")
        if isinstance(available, list) and available:
            options = [mode.lower() for mode in available if isinstance(mode, str)]
        else:
            options = list(DEFAULT_OPTIONS)
        current = self.current_option
        if current and current not in options:
            options.append(current)
        return options

    @property
    def current_option(self) -> str | None:
        """Return the preferred charge mode."""
        if self._optimistic_value is not None:
            return self._optimistic_value
        return enum_value(get_in(self.vehicle, f"{SECTION_CHARGING}.settings.preferredChargeMode"))

    async def async_select_option(self, option: str) -> None:
        """Change the charge mode."""
        await self.coordinator.async_execute_command(
            self.coordinator.api.async_set_charge_mode(self.coordinator.vin, option.upper()),
            section=SECTION_CHARGING,
        )
        self._set_optimistic(option)
