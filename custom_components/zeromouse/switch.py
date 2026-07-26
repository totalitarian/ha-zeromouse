"""Switch entities controlling ZeroMouse write-capable settings.

Two genuinely different controls live here, using two different backend
mechanisms - worth being explicit about which is which:

- ZeroMouseBlockUnknownCats: denies entry to cats not in your known-cat
  clusters. Written via a GraphQL mutation (updateMbrPtfFlapData).
- ZeroMouseBlockPrey: denies entry to ANY cat (known or not) detected
  carrying prey - this is the app's "Block prey" toggle. Written via a
  PATCH to the AWS IoT device shadow's desired state, a completely
  separate backend path from the GraphQL mutation above.

Both are real write actions with physical consequences for the cat, not
passive sensors. Both use OptimisticMixin so the toggle reflects what you
just commanded immediately, rather than flickering back to the old value
while the backend catches up."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZeroMouseFlapMetaCoordinator, ZeroMouseShadowCoordinator
from .device import shadow_reported, zeromouse_device_info
from .shadow_entity import OptimisticMixin

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ZeroMouseBlockUnknownCats(coordinators["flap_meta"], entry),
            ZeroMouseBlockPrey(coordinators["shadow"], entry),
        ]
    )


class ZeroMouseBlockUnknownCats(
    OptimisticMixin, CoordinatorEntity[ZeroMouseFlapMetaCoordinator], SwitchEntity
):
    """When on, the flap denies entry to cats not in your known-cat
    clusters. This is a real physical control, not a passive sensor."""

    _attr_name = "Block Unknown Cats"
    _attr_has_entity_name = True
    _attr_icon = "mdi:cat"

    def __init__(self, coordinator: ZeroMouseFlapMetaCoordinator, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        OptimisticMixin.__init__(self)
        self._attr_unique_id = f"{entry.entry_id}_block_unknown_cats"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def is_on(self) -> bool:
        actual = bool((self.coordinator.data or {}).get("blockUnknownCats"))
        return bool(self._resolve(actual))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._write_and_hold(
            True, self.coordinator.async_set_block_unknown_cats(True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write_and_hold(
            False, self.coordinator.async_set_block_unknown_cats(False)
        )


class ZeroMouseBlockPrey(
    OptimisticMixin, CoordinatorEntity[ZeroMouseShadowCoordinator], SwitchEntity
):
    """Mirrors the app's 'Block prey' toggle - when on, the flap blocks
    ANY cat detected carrying prey, regardless of whether it's a known
    cat. Maps to shadow field rfid.blockEnabled, confirmed against a
    real screenshot of the app's settings screen."""

    _attr_name = "Block Prey"
    _attr_has_entity_name = True
    _attr_icon = "mdi:shield-alert"

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        OptimisticMixin.__init__(self)
        self._attr_unique_id = f"{entry.entry_id}_block_prey"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def is_on(self) -> bool:
        reported = shadow_reported(self.coordinator.data)
        actual = bool(reported.get("rfid", {}).get("blockEnabled"))
        return bool(self._resolve(actual))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._write_and_hold(
            True,
            self.coordinator.async_patch_desired({"rfid": {"blockEnabled": 1}}),
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write_and_hold(
            False,
            self.coordinator.async_patch_desired({"rfid": {"blockEnabled": 0}}),
        )
