"""Binary sensor for ZeroMouse device connectivity."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZeroMouseShadowCoordinator
from .device import zeromouse_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ZeroMouseConnected(coordinators["shadow"], entry)])


class ZeroMouseConnected(CoordinatorEntity[ZeroMouseShadowCoordinator], BinarySensorEntity):
    """On when the device shadow reports an active connection."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "Connected"
    _attr_has_entity_name = True

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_connected"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def is_on(self) -> bool:
        shadow = self.coordinator.data or {}
        return bool(shadow.get("connectivity", {}).get("connected"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        shadow = self.coordinator.data or {}
        return {
            "last_shadow_update": shadow.get("timestamp"),
        }
