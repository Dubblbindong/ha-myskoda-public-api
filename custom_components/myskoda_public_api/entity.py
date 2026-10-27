"""Base entity for the MyŠkoda Public API integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import API_KEY_MANAGEMENT_URL, DOMAIN, MANUFACTURER
from .coordinator import MySkodaVehicleCoordinator
from .helpers import section_present


class MySkodaEntity(CoordinatorEntity[MySkodaVehicleCoordinator]):
    """Entity bound to one vehicle of the MyŠkoda Public API."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MySkodaVehicleCoordinator,
        key: str,
        section: str | None = None,
    ) -> None:
        """Initialise the entity.

        ``section`` names the part of the vehicle response the entity depends on; the
        entity becomes unavailable while that part is missing from the response.
        """
        super().__init__(coordinator)
        self._section = section
        self._optimistic_value: Any = None
        self._attr_unique_id = f"{coordinator.vin}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.vin)},
            manufacturer=MANUFACTURER,
            name=coordinator.vehicle_name,
            serial_number=coordinator.vin,
            configuration_url=API_KEY_MANAGEMENT_URL,
        )

    @property
    def vehicle(self) -> dict[str, Any]:
        """Return the vehicle data of the last update."""
        return self.coordinator.vehicle

    @property
    def available(self) -> bool:
        """Return True while the backing part of the vehicle data is present."""
        return super().available and section_present(self.vehicle, self._section)

    @callback
    def _set_optimistic(self, value: Any) -> None:
        """Show the expected state until the next update arrives from the API."""
        self._optimistic_value = value
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Drop the optimistic state once fresh data arrives."""
        self._optimistic_value = None
        super()._handle_coordinator_update()
