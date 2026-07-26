"""GIF building and on-disk storage for ZeroMouse's two curated event
'slots'.

The two slots:
- 'latest': the most recent event - or, if the integration's
  'include_exits' option is off, the most recent event that wasn't an
  exit (classification != 'out'). One toggle instead of two
  always-on entities.
- 'last_prey': the most recent event with a confirmed-prey
  classification (see const.PREY_CLASSIFICATIONS). Reflects "most
  recent going forward" within the polled window, not a full
  historical archive - stays empty until a genuine prey event is
  actually seen while the integration is running."""
from __future__ import annotations

import json
import logging
import os
from io import BytesIO
from typing import Any, Callable

import boto3
import requests
from PIL import Image

from .const import BUCKET_NAME, HISTORY_SUBDIR, PREY_CLASSIFICATIONS, REGION

_LOGGER = logging.getLogger(__name__)

_IMAGE_FETCH_HEADERS = {
    "user-agent": "ZeroMouseRn/55 CFNetwork/3855.100.1 Darwin/25.0.0",
    "accept-language": "en-GB,en;q=0.9",
    "accept": "*/*",
}

# Only 'last_prey' has a fixed predicate. The other slot ('latest') is
# parameterized at call time by sync()'s include_exits argument - see
# below - so a single toggle in the integration's options controls
# whether exits count as "the last event" or get skipped over.
_PREY_PREDICATE: Callable[[dict[str, Any]], bool] = (
    lambda event: event.get("classification_byNet") in PREY_CLASSIFICATIONS
)


def build_gif_bytes(
    identity_id: str,
    creds: dict[str, Any],
    device_id: str,
    event_id: str,
    image_indices: list[int],
) -> bytes | None:
    """Download an event's frames from S3 and stitch them into a GIF.
    Blocking - must be run via executor job.

    S3 key pattern confirmed by directly listing the bucket (the
    GraphQL 'Images' connection field never resolves - see coordinator.py
    for the working alternative this reads imageIndex from):
        private/{identity_id}/devices/{device_id}/events/{event_id}/images/{imageIndex}.jpg
    """
    if not image_indices:
        return None

    s3 = boto3.client(
        "s3",
        region_name=REGION,
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretKey"],
        aws_session_token=creds["SessionToken"],
    )

    frames: list[Image.Image] = []
    for index in sorted(image_indices):
        key = (
            f"private/{identity_id}/devices/{device_id}/events/{event_id}"
            f"/images/{index}.jpg"
        )
        try:
            url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET_NAME, "Key": key},
                ExpiresIn=900,
            )
            resp = requests.get(url, headers=_IMAGE_FETCH_HEADERS, timeout=15)
            resp.raise_for_status()
            frames.append(Image.open(BytesIO(resp.content)).convert("RGB"))
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to fetch ZeroMouse frame %s: %s", key, err)

    if not frames:
        return None

    buffer = BytesIO()
    frames[0].save(
        buffer, format="GIF", save_all=True, append_images=frames[1:],
        duration=300, loop=0,
    )
    return buffer.getvalue()


class HistoryStore:
    """Manages one GIF per slot ('latest' and 'last_prey', see module
    docstring above) under
    config/www/zeromouse/history/, plus a JSON index describing them.

    Storing under www/ means each saved GIF is reachable at a stable,
    unauthenticated /local/ URL - useful for Lovelace cards and mobile
    notifications, and means each slot's snapshot survives HA restarts
    without re-hitting AWS for anything already downloaded."""

    def __init__(self, www_path: str) -> None:
        self.base_dir = os.path.join(www_path, HISTORY_SUBDIR)
        self.index_path = os.path.join(self.base_dir, "index.json")
        os.makedirs(self.base_dir, exist_ok=True)

    def load_index(self) -> dict[str, dict[str, Any]]:
        """Blocking. Returns {slot_name: {event_id, event_time, ...}}."""
        if not os.path.exists(self.index_path):
            return {}
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as err:
            _LOGGER.warning("Failed to read ZeroMouse history index: %s", err)
            return {}

        if not isinstance(data, dict):
            # Leftover from an older index format - discard rather than
            # crash. Everything simply re-downloads on the next sync.
            _LOGGER.info(
                "ZeroMouse history index was in an old format - resetting."
            )
            return {}

        return data

    def save_index(self, index: dict[str, dict[str, Any]]) -> None:
        """Blocking."""
        try:
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(index, f)
        except OSError as err:
            _LOGGER.warning("Failed to write ZeroMouse history index: %s", err)

    def gif_path(self, slot: str) -> str:
        return os.path.join(self.base_dir, f"{slot}.gif")

    def local_url(self, slot: str) -> str:
        return f"/local/{HISTORY_SUBDIR}/{slot}.gif"

    def save_gif(self, slot: str, gif_bytes: bytes) -> None:
        """Blocking."""
        try:
            with open(self.gif_path(slot), "wb") as f:
                f.write(gif_bytes)
        except OSError as err:
            _LOGGER.warning("Failed to save ZeroMouse GIF for slot %s: %s", slot, err)

    def _save_event_to_slot(
        self,
        index: dict[str, dict[str, Any]],
        slot_name: str,
        event: dict[str, Any],
        identity_id: str,
        creds: dict[str, Any],
        device_id: str,
    ) -> bool:
        """Blocking. Downloads+saves a single event into a slot if it
        isn't already there. Returns True if it actually wrote something
        (used by backfill to know whether it found real data)."""
        event_id = event.get("eventID")
        if not event_id:
            return False

        existing = index.get(slot_name)
        if existing and existing.get("event_id") == event_id:
            return False  # already have this exact event stored

        image_indices = [
            img["imageIndex"]
            for img in (event.get("images") or [])
            if "imageIndex" in img
        ]
        gif_bytes = build_gif_bytes(identity_id, creds, device_id, event_id, image_indices)
        if gif_bytes is None:
            return False

        self.save_gif(slot_name, gif_bytes)
        index[slot_name] = {
            "event_id": event_id,
            "event_time": event.get("eventTime"),
            "classification": event.get("classification_byNet"),
            "type": event.get("type"),
            "image_url": self.local_url(slot_name),
        }
        return True

    def sync(
        self,
        latest_events: list[dict[str, Any]],
        identity_id: str,
        creds: dict[str, Any],
        device_id: str,
        include_exits: bool = True,
    ) -> dict[str, dict[str, Any]]:
        """Blocking. Given the newest events from the API (already sorted
        newest-first), find each slot's most recent matching event and
        download+save it if it's new. Returns the updated index, keyed
        by slot name.

        Two slots:
        - 'latest': the most recent event, or (if include_exits=False)
          the most recent event that wasn't an exit - single toggle
          controls this instead of two separate always-on entities.
        - 'last_prey': the most recent confirmed-prey event (see
          const.PREY_CLASSIFICATIONS). Normally only populated from
          events seen during regular polling ("most recent going
          forward") - see backfill_last_prey() for seeding it from
          further back in history once, at setup."""
        index = self.load_index()

        latest_predicate: Callable[[dict[str, Any]], bool] = (
            (lambda event: True)
            if include_exits
            else (lambda event: event.get("classification_byNet") != "out")
        )
        slots: dict[str, Callable[[dict[str, Any]], bool]] = {
            "latest": latest_predicate,
            "last_prey": _PREY_PREDICATE,
        }

        for slot_name, predicate in slots.items():
            event = next((e for e in latest_events if predicate(e)), None)
            if event is None:
                continue  # nothing in this batch matches (e.g. no prey yet)
            self._save_event_to_slot(index, slot_name, event, identity_id, creds, device_id)

        self.save_index(index)
        return index

    # -- historical backfill for 'last_prey' ------------------------------------
    # Regular polling only ever sees the last EVENT_FETCH_BATCH_SIZE events,
    # so 'last_prey' can go a long time without populating even though real
    # prey events exist further back in history. This lets the coordinator
    # seed it once per HA session from a targeted query (see
    # ZeroMouseCoordinator._fetch_most_recent_prey_event) without needing to
    # walk the entire history like the standalone search script does.
    #
    # NOTE: "should we attempt this" is deliberately tracked in-memory on
    # the coordinator (self._prey_backfill_attempted), not persisted here.
    # An earlier version persisted a permanent done-flag to disk, which
    # meant a failed/empty attempt could never retry without someone
    # manually deleting the index file - a real support headache in
    # practice. Tracking it in-memory instead means every HA restart gets
    # a fresh attempt for free, self-healing without any manual step,
    # while still not hammering the API on every single poll cycle
    # within a session.

    def backfill_last_prey(
        self,
        event: dict[str, Any] | None,
        identity_id: str,
        creds: dict[str, Any],
        device_id: str,
    ) -> None:
        """Blocking. `event` is the most recent confirmed-prey event
        found by a targeted query, or None if the search found nothing.
        No-op if None - nothing to save, and there's no on-disk flag to
        update anymore (see module note above)."""
        if event is None:
            return
        index = self.load_index()
        self._save_event_to_slot(index, "last_prey", event, identity_id, creds, device_id)
        self.save_index(index)
