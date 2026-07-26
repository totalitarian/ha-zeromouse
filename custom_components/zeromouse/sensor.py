"""Sensors for ZeroMouse: event data, session diagnostics, and device shadow."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_TYPE_LABELS
from .coordinator import (
    ZeroMouseCoordinator,
    ZeroMouseFlapMetaCoordinator,
    ZeroMouseShadowCoordinator,
)
from .device import shadow_reported, zeromouse_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    events = coordinators["events"]
    shadow = coordinators["shadow"]
    flap_meta = coordinators["flap_meta"]

    async_add_entities(
        [
            ZeroMouseLastClassification(events, entry),
            ZeroMouseEventTimestamp(events, entry),
            ZeroMouseLastPreyTimestamp(events, entry),
            ZeroMouseEventCount(shadow, entry),
            ZeroMouseIRSensorStatus(shadow, entry),
            ZeroMouseFirmwareVersion(shadow, entry),
            ZeroMouseMQTTErrorCount(shadow, entry),
            ZeroMousePIRTriggerCount(shadow, entry),
            ZeroMouseAIScore(flap_meta, entry),
            ZeroMouseFeedbackScore(flap_meta, entry),
            ZeroMouseBlockCount(shadow, entry),
            ZeroMouseUnblockCount(shadow, entry),
            ZeroMouseBootCount(shadow, entry),
        ]
    )


# -- event-derived sensors -----------------------------------------------------


def _reported(shadow_data: dict | None) -> dict:
    """Delegates to the shared helper in device.py. (Restored after an
    earlier automated edit accidentally deleted this function definition
    while removing unrelated classes - caused a NameError crash across
    every shadow-derived sensor.)"""
    return shadow_reported(shadow_data)


class ZeroMouseLastClassification(CoordinatorEntity[ZeroMouseCoordinator], SensorEntity):
    """State = friendly label (see EVENT_TYPE_LABELS) of the most recent
    event. Whether exits ('out'/"Leaving detected") count as "the most
    recent event" or get skipped over is controlled by the integration's
    'include_exits' option - see coordinator.py."""

    _attr_name = "Last Event"
    _attr_has_entity_name = True

    def __init__(self, coordinator: ZeroMouseCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_event"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> str | None:
        event = (self.coordinator.data or {}).get("event")
        if not event:
            return None
        classification = event.get("classification_byNet", "unclassified")
        # Confirmed real labels where known (from the app's own Events
        # filter screen); anything unmapped falls back to the raw value
        # rather than guessing which of the app's categories it belongs to.
        return EVENT_TYPE_LABELS.get(classification, classification)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        event = (self.coordinator.data or {}).get("event") or {}
        return {
            "event_id": event.get("eventID"),
            "event_time": event.get("eventTime"),
            "event_type": event.get("type"),
            "raw_classification": event.get("classification_byNet"),
        }


class ZeroMouseEventTimestamp(CoordinatorEntity[ZeroMouseCoordinator], SensorEntity):
    """Timestamp of the most recent detection event, using the actual
    eventTime from the AWS data rather than when HA last polled."""

    _attr_name = "Last Event Time"
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: ZeroMouseCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_event_time"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> datetime | None:
        event = (self.coordinator.data or {}).get("event")
        if not event:
            return None
        event_time = event.get("eventTime")
        if not event_time:
            return None
        if isinstance(event_time, (int, float)):
            return dt_util.utc_from_timestamp(event_time)
        parsed = dt_util.parse_datetime(str(event_time))
        if parsed is None:
            return None
        return dt_util.as_utc(parsed) if parsed.tzinfo is None else parsed


class ZeroMouseLastPreyTimestamp(CoordinatorEntity[ZeroMouseCoordinator], SensorEntity):
    """Timestamp of the most recent prey detection event, read from
    the history index (same data that feeds the last prey image)."""

    _attr_name = "Last Prey Time"
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: ZeroMouseCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_prey_time"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> datetime | None:
        history = (self.coordinator.data or {}).get("history") or {}
        prey = history.get("last_prey") or {}
        event_time = prey.get("event_time")
        if not event_time:
            return None
        if isinstance(event_time, (int, float)):
            return dt_util.utc_from_timestamp(event_time)
        parsed = dt_util.parse_datetime(str(event_time))
        if parsed is None:
            return None
        return dt_util.as_utc(parsed) if parsed.tzinfo is None else parsed


class ZeroMouseEventCount(CoordinatorEntity[ZeroMouseShadowCoordinator], SensorEntity):
    """Lifetime event count as reported by the device itself (not HA-side)."""

    _attr_name = "Device Event Count"
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_device_event_count"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> int | None:
        system = _reported(self.coordinator.data).get("system", {})
        return system.get("eventCount")


class ZeroMouseIRSensorStatus(CoordinatorEntity[ZeroMouseShadowCoordinator], SensorEntity):
    """Raw proximity/IR sensor status code from the device shadow."""

    _attr_name = "IR Sensor Status"
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ir_sensor_status"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> int | None:
        proximity = _reported(self.coordinator.data).get("proximity", {})
        return proximity.get("irSensorStatus")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        proximity = _reported(self.coordinator.data).get("proximity", {})
        return {
            "ir_ambient": proximity.get("irAmbient"),
            "ir_ambient_percent": proximity.get("irAmbientPercent"),
            "ir_free_value": proximity.get("irFreeValue"),
        }


class ZeroMouseFirmwareVersion(CoordinatorEntity[ZeroMouseShadowCoordinator], SensorEntity):
    """Firmware version string, assembled from verMajor.verMinor.verRevision."""

    _attr_name = "Firmware Version"
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_firmware_version"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> str | None:
        system = _reported(self.coordinator.data).get("system", {})
        major = system.get("verMajor")
        minor = system.get("verMinor")
        revision = system.get("verRevision")
        if major is None:
            return None
        return f"{major}.{minor}.{revision}"


class ZeroMouseMQTTErrorCount(CoordinatorEntity[ZeroMouseShadowCoordinator], SensorEntity):
    """Device-reported count of MQTT errors - a direct health signal for
    whatever MQTT connection the device maintains to its broker."""

    _attr_name = "MQTT Error Count"
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_mqtt_error_count"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> int | None:
        system = _reported(self.coordinator.data).get("system", {})
        return system.get("metricMQTTErrorCount")


class ZeroMousePIRTriggerCount(CoordinatorEntity[ZeroMouseShadowCoordinator], SensorEntity):
    """Lifetime PIR (motion) sensor trigger count."""

    _attr_name = "PIR Trigger Count"
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_pir_trigger_count"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> int | None:
        system = _reported(self.coordinator.data).get("system", {})
        return system.get("pirTriggerCount")


class ZeroMouseAIScore(CoordinatorEntity[ZeroMouseFlapMetaCoordinator], SensorEntity):
    """Confirmed via app screenshot: this is the 'AI Personalization
    Status' shown in the app's device settings (0-100%). Per the app's
    own description: retrained weekly, reflects how well the AI is
    tailored to this specific setup and cat, improving with feedback
    quantity/quality and how long the device has been online."""

    _attr_name = "AI Personalization Status"
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "%"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZeroMouseFlapMetaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ai_score"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("ai_score")


class ZeroMouseFeedbackScore(CoordinatorEntity[ZeroMouseFlapMetaCoordinator], SensorEntity):
    """Confirmed via app screenshot: this is the 'Feedback Score' shown
    in the app's device settings (0-100%). Per the app's own
    description: reflects how much feedback you've given marking the
    AI's classifications as correct/incorrect - more feedback helps the
    AI adapt to your specific flap and cat during training."""

    _attr_name = "Feedback Score"
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "%"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZeroMouseFlapMetaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_feedback_score"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("userFeedback_score")


class ZeroMouseBlockCount(CoordinatorEntity[ZeroMouseShadowCoordinator], SensorEntity):
    """Lifetime count of times the RFID mechanism has actually blocked
    entry (prey or unknown-cat block events)."""

    _attr_name = "Block Count"
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_block_count"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> int | None:
        rfid = _reported(self.coordinator.data).get("rfid", {})
        return rfid.get("blockCount")


class ZeroMouseUnblockCount(CoordinatorEntity[ZeroMouseShadowCoordinator], SensorEntity):
    """Lifetime count of normal (unblocked) entries."""

    _attr_name = "Unblock Count"
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_unblock_count"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> int | None:
        rfid = _reported(self.coordinator.data).get("rfid", {})
        return rfid.get("unblockCount")


class ZeroMouseBootCount(CoordinatorEntity[ZeroMouseShadowCoordinator], SensorEntity):
    """Lifetime device reboot count - basic stability indicator."""

    _attr_name = "Boot Count"
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: ZeroMouseShadowCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_boot_count"
        self._attr_device_info = zeromouse_device_info(entry)

    @property
    def native_value(self) -> int | None:
        system = _reported(self.coordinator.data).get("system", {})
        return system.get("bootCount")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        system = _reported(self.coordinator.data).get("system", {})
        return {"last_reset_reason": system.get("metricLastResetReason")}


