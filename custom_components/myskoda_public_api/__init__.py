"""The MyŠkoda Public API integration.

Connects a Škoda vehicle to Home Assistant through the official MyŠkoda Public API
(https://public.api.connect.skoda-auto.cz/docs). One config entry represents one
vehicle (VIN) and is authenticated with an API key created in the MyŠkoda app.
"""

from __future__ import annotations

import logging

from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import MySkodaPublicApi
from .const import CONF_VIN, DOMAIN, PLATFORMS
from .coordinator import MySkodaConfigEntry, MySkodaVehicleCoordinator
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration-wide services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MySkodaConfigEntry) -> bool:
    """Set up a vehicle from a config entry."""
    session = async_get_clientsession(hass)
    api = MySkodaPublicApi(session, entry.data[CONF_API_KEY])
    coordinator = MySkodaVehicleCoordinator(hass, entry, api, entry.data[CONF_VIN])
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_shutdown)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: MySkodaConfigEntry) -> None:
    """Reload the entry when its options change (polling interval, S-PIN)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MySkodaConfigEntry) -> bool:
    """Unload a vehicle."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
