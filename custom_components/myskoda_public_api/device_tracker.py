"""Device tracker (parking position) for the MyŠkoda Public API integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SECTION_PARKING_POSITION
from .coordinator import MySkodaConfigEntry, MySkodaVehicleCoordinator
from .entity import MySkodaEntity
from .helpers import enum_value, get_in, section_present

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MySkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the location tracker when the vehicle reports a parking position."""
    coordinator = entry.runtime_data
    if section_present(coordinator.vehicle, SECTION_PARKING_POSITION):
        async_add_entities([MySkodaDeviceTracker(coordinator)])


class MySkodaDeviceTracker(MySkodaEntity, TrackerEntity):
    """Last known parking position of the vehicle."""

    _attr_translation_key = "location"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: MySkodaVehicleCoordinator) -> None:
        """Initialise the tracker."""
        super().__init__(coordinator, "location", SECTION_PARKING_POSITION)

    @property
    def latitude(self) -> float | None:
        """Return the latitude; only reported while the vehicle is parked."""
        return get_in(self.vehicle, f"{SECTION_PARKING_POSITION}.gpsCoordinates.latitude")

    @property
    def longitude(self) -> float | None:
        """Return the longitude; only reported while the vehicle is parked."""
        return get_in(self.vehicle, f"{SECTION_PARKING_POSITION}.gpsCoordinates.longitude")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the parking state and the resolved address."""
        return {
            "parking_state": enum_value(get_in(self.vehicle, f"{SECTION_PARKING_POSITION}.state")),
            "address": get_in(self.vehicle, f"{SECTION_PARKING_POSITION}.formattedAddress"),
        }
