"""Number entity for the adjustable ZeroMouse prey block duration.

Writes to the AWS IoT shadow's desired state via the same PATCH
mechanism as the Block Prey switch - see switch.py's module docstring
for why this is a separate write path from the GraphQL-based controls.
Uses OptimisticMixin for the same reason the switches do - see
shadow_entity.py.

(Inconclusive Handling Mode moved to select.py once its three options
were confirmed from a real app screenshot - a raw number never made
sense for an enum.)"""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZeroMouseShadowCoordinator
from .device import shadow_reported, zeromouse_device_info
from .shadow_entity import OptimisticMixin

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    shadow = coordinators["shadow"]
    async_add_entities([ZeroMousePreyBlockDuration(shadow, entry)])


class ZeroMousePreyBlockDuration(
    OptimisticMixin, CoordinatorEntity[ZeroMouseShadowCoordinator], NumberEntity
):
    """Mirrors the app's 'Prey block duration' setting - how long the
    flap stays blocked after detecting prey. Maps to shadow field
    proximity.irPreyEventTime, confirmed exact match (30) against a real
    screenshot showing '30 seconds'.

    App description states this can go up to 60 minutes (3600s); using
    that as the upper bound. A sensible lower bound of 10s avoids
    accidentally setting something the device would treat as effectively
    disabled."""

    _attr_name = "Prey Block Duration"
    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-lock"
    _attr_native_unit_of_measurement = "s"
    _attr_native_min_value = 10
    _attr_native_max_value = 3600
    _attr_native_step = 5
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        OptimisticMixin.__init__(self)
        self._attr_unique_id = f"{entry.entry_id}_prey_block_duration"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> float | None:
        reported = shadow_reported(self.coordinator.data)
        actual = reported.get("proximity", {}).get("irPreyEventTime")
        return self._resolve(actual)

    async def async_set_native_value(self, value: float) -> None:
        int_value = int(value)
        await self._write_and_hold(
            int_value,
            self.coordinator.async_patch_desired(
                {"proximity": {"irPreyEventTime": int_value}}
            ),
        )

