"""Binary sensors for the MyŠkoda Public API integration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    AC_RUNNING_STATES,
    ACTIVE_VENTILATION_RUNNING_STATES,
    AUX_HEATING_RUNNING_STATES,
    SECTION_ACTIVE_VENTILATION,
    SECTION_AIR_CONDITIONING,
    SECTION_AUXILIARY_HEATING,
    SECTION_CHARGING,
    SECTION_STATUS,
)
from .coordinator import MySkodaConfigEntry, MySkodaVehicleCoordinator
from .entity import MySkodaEntity
from .helpers import get_in, section_present

PARALLEL_UPDATES = 0

type VehicleMapping = Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class MySkodaBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a MyŠkoda binary sensor."""

    is_on_fn: Callable[[VehicleMapping], bool | None]
    section: str | None = None
    exists_fn: Callable[[VehicleMapping], bool] | None = None


def _states(
    path: str, on: tuple[str, ...], off: tuple[str, ...]
) -> Callable[[VehicleMapping], bool | None]:
    """Map enum values at ``path`` to on/off, anything else to unknown."""

    def _get(vehicle: VehicleMapping) -> bool | None:
        value = get_in(vehicle, path)
        if value in on:
            return True
        if value in off:
            return False
        return None

    return _get


def _running(path: str, running: set[str]) -> Callable[[VehicleMapping], bool | None]:
    def _get(vehicle: VehicleMapping) -> bool | None:
        value = get_in(vehicle, path)
        if not isinstance(value, str) or value in ("UNKNOWN", "UNSUPPORTED"):
            return None
        return value in running

    return _get


def _bool(path: str) -> Callable[[VehicleMapping], bool | None]:
    def _get(vehicle: VehicleMapping) -> bool | None:
        value = get_in(vehicle, path)
        return value if isinstance(value, bool) else None

    return _get


def _supported(path: str) -> Callable[[VehicleMapping], bool]:
    return lambda vehicle: get_in(vehicle, path) not in (None, "UNSUPPORTED")


OPEN_CLOSED = ("OPEN",), ("CLOSED",)

BINARY_SENSORS: tuple[MySkodaBinarySensorDescription, ...] = (
    # ---------------------------------------------------------------- status
    MySkodaBinarySensorDescription(
        key="locked",
        translation_key="locked",
        section=SECTION_STATUS,
        # Device class LOCK: on = unlocked.
        is_on_fn=_states(f"{SECTION_STATUS}.overall.locked", ("NO",), ("YES",)),
        device_class=BinarySensorDeviceClass.LOCK,
    ),
    MySkodaBinarySensorDescription(
        key="doors",
        translation_key="doors",
        section=SECTION_STATUS,
        is_on_fn=_states(f"{SECTION_STATUS}.overall.doors", *OPEN_CLOSED),
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    MySkodaBinarySensorDescription(
        key="windows",
        translation_key="windows",
        section=SECTION_STATUS,
        is_on_fn=_states(f"{SECTION_STATUS}.overall.windows", *OPEN_CLOSED),
        device_class=BinarySensorDeviceClass.WINDOW,
    ),
    MySkodaBinarySensorDescription(
        key="lights",
        translation_key="lights",
        section=SECTION_STATUS,
        is_on_fn=_states(f"{SECTION_STATUS}.overall.lights", ("ON",), ("OFF",)),
        device_class=BinarySensorDeviceClass.LIGHT,
    ),
    MySkodaBinarySensorDescription(
        key="trunk",
        translation_key="trunk",
        section=SECTION_STATUS,
        is_on_fn=_states(f"{SECTION_STATUS}.detail.trunk", *OPEN_CLOSED),
        device_class=BinarySensorDeviceClass.OPENING,
    ),
    MySkodaBinarySensorDescription(
        key="bonnet",
        translation_key="bonnet",
        section=SECTION_STATUS,
        is_on_fn=_states(f"{SECTION_STATUS}.detail.bonnet", *OPEN_CLOSED),
        device_class=BinarySensorDeviceClass.OPENING,
    ),
    MySkodaBinarySensorDescription(
        key="sunroof",
        translation_key="sunroof",
        section=SECTION_STATUS,
        exists_fn=_supported(f"{SECTION_STATUS}.detail.sunroof"),
        is_on_fn=_states(f"{SECTION_STATUS}.detail.sunroof", *OPEN_CLOSED),
        device_class=BinarySensorDeviceClass.WINDOW,
    ),
    # ---------------------------------------------------------------- charging
    MySkodaBinarySensorDescription(
        key="plug_connected",
        translation_key="plug_connected",
        section=SECTION_CHARGING,
        is_on_fn=_states(
            f"{SECTION_CHARGING}.status.plugConnectionState",
            ("CONNECTED",),
            ("DISCONNECTED",),
        ),
        device_class=BinarySensorDeviceClass.PLUG,
    ),
    MySkodaBinarySensorDescription(
        key="plug_locked",
        translation_key="plug_locked",
        section=SECTION_CHARGING,
        # Device class LOCK: on = unlocked.
        is_on_fn=_states(
            f"{SECTION_CHARGING}.status.plugLockState", ("UNLOCKED",), ("LOCKED",)
        ),
        device_class=BinarySensorDeviceClass.LOCK,
    ),
    MySkodaBinarySensorDescription(
        key="charging",
        translation_key="charging",
        section=SECTION_CHARGING,
        is_on_fn=_running(f"{SECTION_CHARGING}.status.state", {"CHARGING"}),
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    MySkodaBinarySensorDescription(
        key="in_saved_location",
        translation_key="in_saved_location",
        section=SECTION_CHARGING,
        is_on_fn=_bool(f"{SECTION_CHARGING}.isVehicleInSavedLocation"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # ---------------------------------------------------------------- air conditioning
    MySkodaBinarySensorDescription(
        key="air_conditioning_running",
        translation_key="air_conditioning_running",
        section=SECTION_AIR_CONDITIONING,
        is_on_fn=_running(f"{SECTION_AIR_CONDITIONING}.state", AC_RUNNING_STATES),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    MySkodaBinarySensorDescription(
        key="window_heating_front",
        translation_key="window_heating_front",
        section=SECTION_AIR_CONDITIONING,
        exists_fn=_supported(f"{SECTION_AIR_CONDITIONING}.windowHeating.front"),
        is_on_fn=_states(
            f"{SECTION_AIR_CONDITIONING}.windowHeating.front", ("ON",), ("OFF",)
        ),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    MySkodaBinarySensorDescription(
        key="window_heating_rear",
        translation_key="window_heating_rear",
        section=SECTION_AIR_CONDITIONING,
        exists_fn=_supported(f"{SECTION_AIR_CONDITIONING}.windowHeating.rear"),
        is_on_fn=_states(
            f"{SECTION_AIR_CONDITIONING}.windowHeating.rear", ("ON",), ("OFF",)
        ),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    MySkodaBinarySensorDescription(
        key="window_heating_enabled",
        translation_key="window_heating_enabled",
        section=SECTION_AIR_CONDITIONING,
        exists_fn=_supported(f"{SECTION_AIR_CONDITIONING}.windowHeating.enabled"),
        is_on_fn=_bool(f"{SECTION_AIR_CONDITIONING}.windowHeating.enabled"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MySkodaBinarySensorDescription(
        key="ac_without_external_power",
        translation_key="ac_without_external_power",
        section=SECTION_AIR_CONDITIONING,
        exists_fn=_supported(f"{SECTION_AIR_CONDITIONING}.airConditioningWithoutExternalPower"),
        is_on_fn=_bool(f"{SECTION_AIR_CONDITIONING}.airConditioningWithoutExternalPower"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MySkodaBinarySensorDescription(
        key="ac_at_unlock",
        translation_key="ac_at_unlock",
        section=SECTION_AIR_CONDITIONING,
        exists_fn=_supported(f"{SECTION_AIR_CONDITIONING}.airConditioningAtUnlock"),
        is_on_fn=_bool(f"{SECTION_AIR_CONDITIONING}.airConditioningAtUnlock"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # ---------------------------------------------------------------- auxiliary heating
    MySkodaBinarySensorDescription(
        key="auxiliary_heating_running",
        translation_key="auxiliary_heating_running",
        section=SECTION_AUXILIARY_HEATING,
        is_on_fn=_running(f"{SECTION_AUXILIARY_HEATING}.state", AUX_HEATING_RUNNING_STATES),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    # ---------------------------------------------------------------- active ventilation
    MySkodaBinarySensorDescription(
        key="active_ventilation_running",
        translation_key="active_ventilation_running",
        section=SECTION_ACTIVE_VENTILATION,
        is_on_fn=_running(
            f"{SECTION_ACTIVE_VENTILATION}.state", ACTIVE_VENTILATION_RUNNING_STATES
        ),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MySkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the binary sensors the vehicle supports."""
    coordinator = entry.runtime_data
    vehicle = coordinator.vehicle
    async_add_entities(
        MySkodaBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if section_present(vehicle, description.section)
        and (description.exists_fn is None or description.exists_fn(vehicle))
    )


class MySkodaBinarySensor(MySkodaEntity, BinarySensorEntity):
    """A binary sensor backed by one value of the vehicle response."""

    entity_description: MySkodaBinarySensorDescription

    def __init__(
        self,
        coordinator: MySkodaVehicleCoordinator,
        description: MySkodaBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, description.key, description.section)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.is_on_fn(self.vehicle)
