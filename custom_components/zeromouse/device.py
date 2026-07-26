"""Shared device_info helper so all ZeroMouse entities group under one
device card in Home Assistant, instead of floating as standalone entities
under the integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN


def zeromouse_device_info(entry: ConfigEntry) -> DeviceInfo:
    device_id = entry.data[CONF_DEVICE_ID]
    device_name = entry.data.get(CONF_DEVICE_NAME) or entry.title or "ZeroMouse"
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_name,
        manufacturer="ZeroMouse",
        model="Smart Cat Flap",
        configuration_url="https://www.zero-mouse.com",
    )


def shadow_reported(shadow_data: dict | None) -> dict:
    """Shared accessor for the 'reported' section of a raw device shadow
    dict (as returned by ZeroMouseShadowCoordinator). Previously
    duplicated inline in number.py, select.py, sensor.py, and switch.py -
    consolidated here as the one place that shape lives."""
    return (shadow_data or {}).get("state", {}).get("reported", {})
