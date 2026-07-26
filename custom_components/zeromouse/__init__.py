"""The ZeroMouse integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .auth import ZeroMouseAuth
from .const import DOMAIN
from .coordinator import (
    ZeroMouseCoordinator,
    ZeroMouseFlapMetaCoordinator,
    ZeroMouseShadowCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["binary_sensor", "sensor", "image", "switch", "number", "select"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    auth = ZeroMouseAuth(hass, entry)

    event_coordinator = ZeroMouseCoordinator(hass, entry, auth)
    shadow_coordinator = ZeroMouseShadowCoordinator(hass, entry, auth)
    flap_meta_coordinator = ZeroMouseFlapMetaCoordinator(hass, entry, auth)

    await event_coordinator.async_config_entry_first_refresh()
    await shadow_coordinator.async_config_entry_first_refresh()
    await flap_meta_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "events": event_coordinator,
        "shadow": shadow_coordinator,
        "flap_meta": flap_meta_coordinator,
    }

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options (e.g. poll interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
