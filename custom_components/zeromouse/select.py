"""Select entity for ZeroMouse's 'Inconclusive event handling' setting.

Writes to the AWS IoT shadow's desired state via the same PATCH mechanism
as the Block Prey switch - see switch.py's module docstring for why this
is a separate write path from the GraphQL-based controls. Uses
OptimisticMixin for the same reason the switches do - see
shadow_entity.py."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZeroMouseShadowCoordinator
from .device import shadow_reported, zeromouse_device_info
from .shadow_entity import OptimisticMixin

_LOGGER = logging.getLogger(__name__)

# Confirmed via a real screenshot of the app's "Inconclusive event
# handling" settings screen - exact descriptions and list order:
#   Smart mode    - blocks inconclusive events only if prey was recently
#                    detected (balanced safety, minimizes false blocks)
#   Always allow  - never blocks on inconclusive events
#   Always block  - always blocks on inconclusive events
#
# Only mode 0 = "Smart mode" is confirmed against a live shadow value.
# 1 = "Always allow" and 2 = "Always block" follow the app's UI list
# order, which is a reasonable but NOT independently confirmed mapping -
# worth verifying by toggling the app setting and diffing the shadow
# before/after if this ever matters for something safety-critical.
_MODE_TO_LABEL = {
    0: "Smart mode",
    1: "Always allow",
    2: "Always block",
}
_LABEL_TO_MODE = {v: k for k, v in _MODE_TO_LABEL.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ZeroMouseInconclusiveHandlingMode(coordinators["shadow"], entry)])


class ZeroMouseInconclusiveHandlingMode(
    OptimisticMixin, CoordinatorEntity[ZeroMouseShadowCoordinator], SelectEntity
):
    """Mirrors the app's 'Inconclusive event handling' setting. Maps to
    shadow field system.undecidableMode."""

    _attr_name = "Inconclusive Handling Mode"
    _attr_has_entity_name = True
    _attr_icon = "mdi:help-circle-outline"
    _attr_options = list(_MODE_TO_LABEL.values())

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        OptimisticMixin.__init__(self)
        self._attr_unique_id = f"{entry.entry_id}_undecidable_mode"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def current_option(self) -> str | None:
        reported = shadow_reported(self.coordinator.data)
        actual_mode = reported.get("system", {}).get("undecidableMode")
        resolved_mode = self._resolve(actual_mode)
        if resolved_mode is None:
            return None
        # Unknown integer (a mode we haven't seen/confirmed) shows as
        # unavailable rather than silently mapping to the wrong label.
        return _MODE_TO_LABEL.get(resolved_mode)

    async def async_select_option(self, option: str) -> None:
        mode = _LABEL_TO_MODE[option]
        await self._write_and_hold(
            mode,
            self.coordinator.async_patch_desired({"system": {"undecidableMode": mode}}),
        )
