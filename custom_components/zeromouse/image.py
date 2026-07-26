"""Image entities for ZeroMouse detection GIFs.

Two fixed entities, matching history.py's two slots ('latest', toggled
by the integration's include_exits option, and 'last_prey') - replaced
an earlier design that created one entity per raw classification_byNet
value (technically thorough, but confusing on a dashboard) and an even
earlier three-entity design that had a separate always-on
"last non-exit" entity instead of a single toggle."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_TYPE_LABELS
from .coordinator import ZeroMouseCoordinator
from .device import zeromouse_device_info

_LOGGER = logging.getLogger(__name__)

_SLOT_NAMES = {
    "latest": "Last Event",
    "last_prey": "Last Prey Detected",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["events"]
    async_add_entities(
        [
            ZeroMouseSlotImage(coordinator, entry, hass, slot, name)
            for slot, name in _SLOT_NAMES.items()
        ]
    )


class ZeroMouseSlotImage(CoordinatorEntity[ZeroMouseCoordinator], ImageEntity):
    """Renders the GIF for one of history.py's two slots - see its
    module docstring for exactly what each slot means. Shows as
    unavailable until that slot has a real match (e.g. 'last_prey' stays
    empty until a genuine prey event actually happens)."""

    _attr_content_type = "image/gif"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZeroMouseCoordinator,
        entry: ConfigEntry,
        hass: HomeAssistant,
        slot: str,
        name: str,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self.slot = slot
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_image_{slot}"
        self._attr_device_info = zeromouse_device_info(entry)
        self._last_event_id: str | None = None

    @property
    def _entry(self) -> dict[str, Any]:
        history = (self.coordinator.data or {}).get("history") or {}
        return history.get(self.slot) or {}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        entry = self._entry
        classification = entry.get("classification")
        return {
            "event_id": entry.get("event_id"),
            "event_time": entry.get("event_time"),
            "event_type": EVENT_TYPE_LABELS.get(classification, classification),
            "raw_classification": classification,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        event_id = self._entry.get("event_id")
        if event_id and event_id != self._last_event_id:
            self._last_event_id = event_id
            event_time = self._entry.get("event_time")
            if event_time:
                parsed = dt_util.parse_datetime(event_time)
                if parsed:
                    self._attr_image_last_updated = (
                        dt_util.as_utc(parsed) if parsed.tzinfo is None else parsed
                    )
                else:
                    self._attr_image_last_updated = dt_util.utcnow()
            else:
                self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        if not self._entry.get("event_id"):
            return None
        path = self.coordinator.history.gif_path(self.slot)
        return await self.hass.async_add_executor_job(_read_file, path)


def _read_file(path: str) -> bytes | None:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as err:
        _LOGGER.debug("ZeroMouse GIF not yet on disk (%s): %s", path, err)
        return None
