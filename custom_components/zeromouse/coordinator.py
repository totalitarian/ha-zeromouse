"""DataUpdateCoordinators for ZeroMouse: events+history, shadow, flap metadata."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import requests
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .auth import ZeroMouseAuth
from .const import (
    CONF_DEVICE_ID,
    CONF_INCLUDE_EXITS,
    CONF_OWNER_ID,
    CONF_POLL_INTERVAL,
    DEFAULT_INCLUDE_EXITS,
    DEFAULT_POLL_INTERVAL,
    DEVICE_SHADOW_ENDPOINT,
    DOMAIN,
    EVENT_FETCH_BATCH_SIZE,
    GRAPHQL_ENDPOINT,
    PREY_CLASSIFICATIONS,
)
from .history import HistoryStore

_LOGGER = logging.getLogger(__name__)

_EVENT_QUERY = """
query listEventbyDeviceChrono(
    $deviceID: String!,
    $sortDirection: ModelSortDirection,
    $filter: ModelMbrPtfEventDataFilterInput,
    $limit: Int
) {
    listEventbyDeviceChrono(
        deviceID: $deviceID,
        sortDirection: $sortDirection,
        filter: $filter,
        limit: $limit
    ) {
        items {
            eventID
            eventTime
            type
            classification_byNet
            images {
                imageIndex
            }
        }
    }
}
"""

_FLAP_META_QUERY = """
query getMbrPtfFlapData($deviceID: ID!) {
    getMbrPtfFlapData(deviceID: $deviceID) {
        deviceID
        name
        model
        networkName
        verHardware
        bootCount
        eventCount
        ai_score
        userFeedback_score
        blockUnknownCats
    }
}
"""


class ZeroMouseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the ZeroMouse GraphQL API for recent detection events and
    keeps the latest GIF for each classification_byNet value on disk."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, auth: ZeroMouseAuth) -> None:
        poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_events",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.entry = entry
        self.auth = auth
        self.device_id = entry.data[CONF_DEVICE_ID]
        self.owner_id = entry.data[CONF_OWNER_ID]
        self.history = HistoryStore(hass.config.path("www"))
        # In-memory only, deliberately not persisted - see backfill_last_prey's
        # docstring in history.py for why. Resets naturally on every HA
        # restart, so the backfill self-heals without any manual step.
        self._prey_backfill_attempted = False

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            id_token, identity_id, creds = await self.auth.async_get_aws_credentials()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"ZeroMouse authentication failed: {err}") from err

        events = await self.hass.async_add_executor_job(
            self._fetch_events, id_token, EVENT_FETCH_BATCH_SIZE
        )

        include_exits = self.entry.options.get(CONF_INCLUDE_EXITS, DEFAULT_INCLUDE_EXITS)

        history_index = await self.hass.async_add_executor_job(
            self.history.sync, events, identity_id, creds, self.device_id, include_exits
        )

        # Backfill: regular polling only sees the last EVENT_FETCH_BATCH_SIZE
        # events, so 'last_prey' can stay empty indefinitely even when real
        # prey events exist further back. Attempted once per HA session
        # (self._prey_backfill_attempted, set in __init__) using a targeted
        # query rather than walking all of history - see history.py's
        # backfill_last_prey docstring for why this is tracked in-memory
        # rather than persisted (self-heals on restart, no manual reset
        # needed if an earlier attempt found nothing or hit an error).
        if not self._prey_backfill_attempted:
            self._prey_backfill_attempted = True
            _LOGGER.info("ZeroMouse: running prey backfill lookup for this session...")
            prey_event = await self.hass.async_add_executor_job(
                self._fetch_most_recent_prey_event, id_token
            )
            if prey_event is None:
                _LOGGER.info(
                    "ZeroMouse: prey backfill found no matching event this "
                    "session (query returned empty or failed - will try "
                    "again on next HA restart)."
                )
            else:
                _LOGGER.info(
                    "ZeroMouse: prey backfill found event %s (time %s) - saving GIF.",
                    prey_event.get("eventID"), prey_event.get("eventTime"),
                )
                await self.hass.async_add_executor_job(
                    self.history.backfill_last_prey, prey_event, identity_id, creds, self.device_id
                )
                # Re-load so this update's returned history reflects the
                # backfilled slot immediately, instead of waiting a full
                # poll interval for it to show up.
                history_index = await self.hass.async_add_executor_job(self.history.load_index)
                if "last_prey" not in history_index:
                    _LOGGER.warning(
                        "ZeroMouse: prey backfill found event %s but it isn't in "
                        "the saved index afterward - GIF download/save likely "
                        "failed (check for 'Failed to fetch ZeroMouse frame' "
                        "warnings above).",
                        prey_event.get("eventID"),
                    )

        latest_with_images = next(
            (
                e for e in events
                if e.get("images") and (include_exits or e.get("classification_byNet") != "out")
            ),
            None,
        )

        return {
            "event": latest_with_images,
            "identity_id": identity_id,
            "creds": creds,
            "history": history_index,
        }

    def _fetch_events(self, id_token: str, limit: int) -> list[dict[str, Any]]:
        variables = {
            "limit": limit,
            "deviceID": self.device_id,
            "sortDirection": "DESC",
            "filter": {"isDeleted": {"eq": 0}},
        }
        headers = {"Content-Type": "application/json", "Authorization": id_token}

        try:
            resp = requests.post(
                GRAPHQL_ENDPOINT,
                headers=headers,
                json={"query": _EVENT_QUERY, "variables": variables},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as err:
            raise UpdateFailed(f"ZeroMouse API request failed: {err}") from err

        payload = resp.json()
        if "errors" in payload:
            raise UpdateFailed(f"ZeroMouse API returned errors: {payload['errors']}")

        connection = (payload.get("data") or {}).get("listEventbyDeviceChrono") or {}
        return connection.get("items", [])

    def _fetch_most_recent_prey_event(self, id_token: str) -> dict[str, Any] | None:
        """Blocking. Confirmed via direct testing that server-side
        filtering on classification_byNet returns an empty array even
        when real matches exist (same pattern as other unreliable
        filters/indexes this API has shown elsewhere) - so this does NOT
        filter server-side. Instead it fetches a larger unfiltered batch
        (still just one or two requests, not a full history walk) and
        searches client-side, the same approach sync() already uses for
        its slots."""
        variables = {
            "limit": 200,
            "deviceID": self.device_id,
            "sortDirection": "DESC",
        }
        headers = {"Content-Type": "application/json", "Authorization": id_token}

        try:
            resp = requests.post(
                GRAPHQL_ENDPOINT,
                headers=headers,
                json={"query": _EVENT_QUERY, "variables": variables},
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()
            if "errors" in payload:
                _LOGGER.warning("ZeroMouse prey backfill query returned errors: %s", payload["errors"])
                return None
            connection = (payload.get("data") or {}).get("listEventbyDeviceChrono") or {}
            items = connection.get("items") or []
            return next(
                (e for e in items if e.get("classification_byNet") in PREY_CLASSIFICATIONS),
                None,
            )
        except requests.RequestException as err:
            _LOGGER.warning("ZeroMouse prey backfill query failed: %s", err)
            return None


class ZeroMouseShadowCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the device's AWS IoT shadow for live connectivity/sensor state.

    Uses a slower default interval than the event coordinator - shadow data
    (connectivity, sensor thresholds, firmware version) changes far less
    often than detection events, so there's no need to hit it every cycle.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, auth: ZeroMouseAuth) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_shadow",
            update_interval=timedelta(minutes=5),
        )
        self.entry = entry
        self.auth = auth
        self.device_id = entry.data[CONF_DEVICE_ID]

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            id_token = await self.auth.async_get_id_token()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"ZeroMouse authentication failed: {err}") from err

        return await self.hass.async_add_executor_job(self._fetch_shadow, id_token)

    def _fetch_shadow(self, id_token: str) -> dict[str, Any]:
        headers = {"auth-token": id_token, "accept": "application/json"}
        try:
            resp = requests.get(
                DEVICE_SHADOW_ENDPOINT,
                headers=headers,
                params={"deviceID": self.device_id},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as err:
            raise UpdateFailed(f"ZeroMouse shadow request failed: {err}") from err

        try:
            return resp.json()
        except ValueError as err:
            raise UpdateFailed(f"ZeroMouse shadow returned invalid JSON: {err}") from err

    async def async_patch_desired(self, patch: dict[str, Any]) -> None:
        """Write to the shadow's desired state and refresh afterward.

        Confirmed via live testing that this endpoint only accepts PATCH
        for writes - POST and PUT both return a generic API Gateway
        "Missing Authentication Token" 403 (meaning no route configured
        for those methods, not an actual auth failure). `patch` should be
        the nested dict to merge under state.desired, e.g.
        {"rfid": {"blockEnabled": 1}} - only the fields you include are
        touched, confirmed by re-fetching after a no-op write and seeing
        everything else unchanged."""
        id_token = await self.auth.async_get_id_token()
        await self.hass.async_add_executor_job(
            self._patch_shadow, id_token, patch
        )
        await self.async_request_refresh()

    def _patch_shadow(self, id_token: str, patch: dict[str, Any]) -> None:
        headers = {
            "auth-token": id_token,
            "Content-Type": "application/json",
        }
        body = {"state": {"desired": patch}}
        try:
            resp = requests.patch(
                DEVICE_SHADOW_ENDPOINT,
                headers=headers,
                params={"deviceID": self.device_id},
                json=body,
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as err:
            raise UpdateFailed(f"ZeroMouse shadow write failed: {err}") from err


_UPDATE_FLAP_MUTATION = """
mutation updateMbrPtfFlapData($input: UpdateMbrPtfFlapDataInput!) {
    updateMbrPtfFlapData(input: $input) {
        deviceID
        blockUnknownCats
    }
}
"""


class ZeroMouseFlapMetaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls getMbrPtfFlapData for device metadata: AI/feedback scores,
    known-cat clusters, and the blockUnknownCats config value.

    NOTE: the CatCluster sub-selection is limited to 'id' for now - the
    full field set on CatCluster hasn't been introspected yet, so this
    only gives a count/id-list until that's confirmed."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, auth: ZeroMouseAuth) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_flap_meta",
            update_interval=timedelta(minutes=5),
        )
        self.entry = entry
        self.auth = auth
        self.device_id = entry.data[CONF_DEVICE_ID]

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            id_token, _, _ = await self.auth.async_get_aws_credentials()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"ZeroMouse authentication failed: {err}") from err

        return await self.hass.async_add_executor_job(self._fetch_flap_meta, id_token)

    def _fetch_flap_meta(self, id_token: str) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "Authorization": id_token}
        variables = {"deviceID": self.device_id}
        try:
            resp = requests.post(
                GRAPHQL_ENDPOINT,
                headers=headers,
                json={"query": _FLAP_META_QUERY, "variables": variables},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as err:
            raise UpdateFailed(f"ZeroMouse flap-meta request failed: {err}") from err

        payload = resp.json()
        if "errors" in payload:
            raise UpdateFailed(f"ZeroMouse flap-meta API returned errors: {payload['errors']}")

        return payload.get("data", {}).get("getMbrPtfFlapData") or {}

    async def async_set_block_unknown_cats(self, value: bool) -> None:
        """Send a partial update mutation setting only blockUnknownCats -
        confirmed via introspection that UpdateMbrPtfFlapDataInput only
        requires deviceID; every other field, including this one, is
        optional, so omitted fields (name, model, catClusters, etc.) are
        left untouched by the backend rather than being nulled out."""
        try:
            id_token, _, _ = await self.auth.async_get_aws_credentials()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"ZeroMouse authentication failed: {err}") from err

        await self.hass.async_add_executor_job(
            self._send_block_unknown_cats, id_token, value
        )
        await self.async_request_refresh()

    def _send_block_unknown_cats(self, id_token: str, value: bool) -> None:
        headers = {"Content-Type": "application/json", "Authorization": id_token}
        variables = {
            "input": {
                "deviceID": self.device_id,
                "blockUnknownCats": 1 if value else 0,
            }
        }
        resp = requests.post(
            GRAPHQL_ENDPOINT,
            headers=headers,
            json={"query": _UPDATE_FLAP_MUTATION, "variables": variables},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise UpdateFailed(
                f"ZeroMouse update mutation returned errors: {payload['errors']}"
            )

