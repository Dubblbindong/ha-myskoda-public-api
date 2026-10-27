"""Switches (charging, active ventilation, auxiliary heating) for MyŠkoda vehicles."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ACTIVE_VENTILATION_RUNNING_STATES,
    AUX_HEATING_RUNNING_STATES,
    DOMAIN,
    OP_START_ACTIVE_VENTILATION,
    OP_START_AUXILIARY_HEATING,
    OP_START_CHARGING,
    OP_STOP_ACTIVE_VENTILATION,
    OP_STOP_AUXILIARY_HEATING,
    OP_STOP_CHARGING,
    SECTION_ACTIVE_VENTILATION,
    SECTION_AUXILIARY_HEATING,
    SECTION_CHARGING,
)
from .coordinator import MySkodaConfigEntry, MySkodaVehicleCoordinator
from .entity import MySkodaEntity
from .helpers import get_in, section_present, temperature_to_celsius

PARALLEL_UPDATES = 1

type VehicleMapping = Mapping[str, Any]
type CommandFn = Callable[[MySkodaVehicleCoordinator], Awaitable[None]]


@dataclass(frozen=True, kw_only=True)
class MySkodaSwitchDescription(SwitchEntityDescription):
    """Describes a MyŠkoda switch."""

    section: str
    start_operation: str
    stop_operation: str
    is_on_fn: Callable[[VehicleMapping], bool | None]
    turn_on_fn: CommandFn
    turn_off_fn: CommandFn


def _running(path: str, running: set[str]) -> Callable[[VehicleMapping], bool | None]:
    def _get(vehicle: VehicleMapping) -> bool | None:
        value = get_in(vehicle, path)
        if not isinstance(value, str) or value in ("UNKNOWN", "UNSUPPORTED"):
            return None
        return value in running

    return _get


async def _start_auxiliary_heating(coordinator: MySkodaVehicleCoordinator) -> None:
    """Start the auxiliary heater with the settings the vehicle reports."""
    spin = coordinator.spin
    if not spin:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="spin_required")
    heating = coordinator.vehicle.get(SECTION_AUXILIARY_HEATING) or {}
    await coordinator.api.async_start_auxiliary_heating(
        coordinator.vin,
        spin=spin,
        duration_seconds=heating.get("durationInSeconds"),
        start_mode=heating.get("startMode"),
        target_temperature_celsius=temperature_to_celsius(heating.get("targetTemperature")),
    )


SWITCHES: tuple[MySkodaSwitchDescription, ...] = (
    MySkodaSwitchDescription(
        key="charging",
        translation_key="charging",
        section=SECTION_CHARGING,
        start_operation=OP_START_CHARGING,
        stop_operation=OP_STOP_CHARGING,
        is_on_fn=_running(f"{SECTION_CHARGING}.status.state", {"CHARGING"}),
        turn_on_fn=lambda c: c.api.async_start_charging(c.vin),
        turn_off_fn=lambda c: c.api.async_stop_charging(c.vin),
    ),
    MySkodaSwitchDescription(
        key="active_ventilation",
        translation_key="active_ventilation",
        section=SECTION_ACTIVE_VENTILATION,
        start_operation=OP_START_ACTIVE_VENTILATION,
        stop_operation=OP_STOP_ACTIVE_VENTILATION,
        is_on_fn=_running(
            f"{SECTION_ACTIVE_VENTILATION}.state", ACTIVE_VENTILATION_RUNNING_STATES
        ),
        turn_on_fn=lambda c: c.api.async_start_active_ventilation(c.vin),
        turn_off_fn=lambda c: c.api.async_stop_active_ventilation(c.vin),
    ),
    MySkodaSwitchDescription(
        key="auxiliary_heating",
        translation_key="auxiliary_heating",
        section=SECTION_AUXILIARY_HEATING,
        start_operation=OP_START_AUXILIARY_HEATING,
        stop_operation=OP_STOP_AUXILIARY_HEATING,
        is_on_fn=_running(f"{SECTION_AUXILIARY_HEATING}.state", AUX_HEATING_RUNNING_STATES),
        turn_on_fn=_start_auxiliary_heating,
        turn_off_fn=lambda c: c.api.async_stop_auxiliary_heating(c.vin),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MySkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create switches for the remote operations the vehicle supports."""
    coordinator = entry.runtime_data
    vehicle = coordinator.vehicle
    async_add_entities(
        MySkodaSwitch(coordinator, description)
        for description in SWITCHES
        if section_present(vehicle, description.section)
        and coordinator.supports_operation(description.start_operation)
        and coordinator.supports_operation(description.stop_operation)
    )


class MySkodaSwitch(MySkodaEntity, SwitchEntity):
    """A switch that starts or stops a function of the vehicle."""

    entity_description: MySkodaSwitchDescription

    def __init__(
        self,
        coordinator: MySkodaVehicleCoordinator,
        description: MySkodaSwitchDescription,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, description.key, description.section)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the state, optimistic right after a command."""
        if self._optimistic_value is not None:
            return self._optimistic_value
        return self.entity_description.is_on_fn(self.vehicle)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the function."""
        await self.coordinator.async_execute_command(
            self.entity_description.turn_on_fn(self.coordinator),
            section=self.entity_description.section,
        )
        self._set_optimistic(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the function."""
        await self.coordinator.async_execute_command(
            self.entity_description.turn_off_fn(self.coordinator),
            section=self.entity_description.section,
        )
        self._set_optimistic(False)
