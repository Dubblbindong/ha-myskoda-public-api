"""Button (refresh) for the MyŠkoda Public API integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MySkodaConfigEntry, MySkodaVehicleCoordinator
from .entity import MySkodaEntity

PARALLEL_UPDATES = 1

REFRESH = ButtonEntityDescription(
    key="refresh",
    translation_key="refresh",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MySkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the refresh button."""
    async_add_entities([MySkodaRefreshButton(entry.runtime_data)])


class MySkodaRefreshButton(MySkodaEntity, ButtonEntity):
    """Fetch the vehicle state now (counts against the hourly API quota)."""

    entity_description = REFRESH

    def __init__(self, coordinator: MySkodaVehicleCoordinator) -> None:
        """Initialise the button."""
        super().__init__(coordinator, REFRESH.key)

    async def async_press(self) -> None:
        """Request a refresh."""
        await self.coordinator.async_request_refresh()
