"""Image entity (vehicle render) for the MyŠkoda Public API integration."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity, ImageEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import MySkodaConfigEntry, MySkodaVehicleCoordinator
from .entity import MySkodaEntity

PARALLEL_UPDATES = 0

VEHICLE_IMAGE = ImageEntityDescription(key="vehicle_image", translation_key="vehicle_image")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MySkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the image entity when the API provides a render of the vehicle."""
    coordinator = entry.runtime_data
    if coordinator.vehicle.get("renderUrl"):
        async_add_entities([MySkodaVehicleImage(coordinator)])


class MySkodaVehicleImage(MySkodaEntity, ImageEntity):
    """Render image of the vehicle as provided by Škoda."""

    entity_description = VEHICLE_IMAGE

    def __init__(self, coordinator: MySkodaVehicleCoordinator) -> None:
        """Initialise the image entity."""
        MySkodaEntity.__init__(self, coordinator, VEHICLE_IMAGE.key)
        ImageEntity.__init__(self, coordinator.hass)
        self._attr_image_url = None
        self._update_url()

    @callback
    def _update_url(self) -> None:
        url = self.vehicle.get("renderUrl")
        if url != self._attr_image_url:
            self._attr_image_url = url
            self._cached_image = None
            self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Pick up a changed render URL."""
        self._update_url()
        super()._handle_coordinator_update()
