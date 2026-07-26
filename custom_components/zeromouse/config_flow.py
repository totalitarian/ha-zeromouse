"""Config flow for ZeroMouse integration."""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

import boto3
import requests
import voluptuous as vol
from pycognito.aws_srp import AWSSRP

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CLIENT_ID,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_INCLUDE_EXITS,
    CONF_OWNER_ID,
    CONF_POLL_INTERVAL,
    CONF_REFRESH_TOKEN,
    DEFAULT_INCLUDE_EXITS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    GRAPHQL_ENDPOINT,
    IDENTITY_POOL_ID,
    REGION,
    USER_POOL_ID,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,
    }
)

# Fallback schema used only if device discovery finds nothing and the user
# has to enter IDs manually.
STEP_DEVICE_MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_OWNER_ID): str,
        vol.Required(CONF_DEVICE_ID): str,
    }
)

# Confirmed via live GraphQL testing: listFlapByOwnerID takes ownerID as
# String! (introspection's arg listing showed a bare NON_NULL wrapper with
# no ofType detail, so the underlying scalar had to be confirmed by trial -
# ID! was rejected with a VariableTypeMismatch, String! works and returns
# real device data including a friendly name and model).
_LIST_FLAPS_QUERY = """
query listFlapByOwnerID($ownerID: String!) {
    listFlapByOwnerID(ownerID: $ownerID) {
        items {
            deviceID
            name
            model
            networkName
        }
        nextToken
    }
}
"""


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


def _authenticate(username: str, password: str) -> dict[str, Any]:
    """Blocking call: perform SRP auth against Cognito and resolve identity."""
    client = boto3.client("cognito-idp", region_name=REGION)
    try:
        srp = AWSSRP(
            username=username,
            password=password,
            pool_id=USER_POOL_ID,
            client_id=CLIENT_ID,
            client=client,
        )
        auth_result = srp.authenticate_user()["AuthenticationResult"]
    except Exception as err:  # noqa: BLE001 - surface as InvalidAuth to the flow
        raise InvalidAuth from err

    id_token = auth_result["IdToken"]
    refresh_token = auth_result.get("RefreshToken")

    try:
        id_client = boto3.client("cognito-identity", region_name=REGION)
        login_key = f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
        identity_id = id_client.get_id(
            IdentityPoolId=IDENTITY_POOL_ID,
            Logins={login_key: id_token},
        )["IdentityId"]
    except Exception as err:  # noqa: BLE001
        raise CannotConnect from err

    return {
        "identity_id": identity_id,
        "refresh_token": refresh_token,
        "id_token": id_token,
    }


def _discover_devices(id_token: str, owner_id: str) -> list[dict[str, str]]:
    """List devices tied to this account via the confirmed listFlapByOwnerID
    query. Returns [] on failure/empty rather than raising, so the flow can
    fall back to manual entry."""
    headers = {"Content-Type": "application/json", "Authorization": id_token}
    variables = {"ownerID": owner_id}
    try:
        resp = requests.post(
            GRAPHQL_ENDPOINT,
            headers=headers,
            json={"query": _LIST_FLAPS_QUERY, "variables": variables},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            _LOGGER.debug("listFlapByOwnerID returned errors: %s", payload["errors"])
            return []
        connection = (payload.get("data") or {}).get("listFlapByOwnerID") or {}
        items = connection.get("items", [])
        return [
            {
                "device_id": i["deviceID"],
                "name": i.get("name") or i["deviceID"],
                "model": i.get("model") or "",
            }
            for i in items
        ]
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Device discovery failed, will fall back to manual entry: %s", err)
        return []


def _guess_owner_id_from_token(id_token: str) -> str | None:
    """Best-effort, unverified decode of the JWT payload to read 'sub'.
    This does NOT validate the token signature - it's only used to pre-fill
    a guess for owner_id so the user doesn't have to hunt for it manually.
    If it's wrong, the manual fallback step lets them correct it."""
    try:
        payload_b64 = id_token.split(".")[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
        return payload.get("sub")
    except Exception:  # noqa: BLE001
        return None


class ZeroMouseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ZeroMouse."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str | None = None
        self._password: str | None = None
        self._refresh_token: str | None = None
        self._identity_id: str | None = None
        self._id_token: str | None = None
        self._owner_id_guess: str | None = None
        self._discovered_devices: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """First step: collect ZeroMouse account credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                result = await self.hass.async_add_executor_job(
                    _authenticate, user_input["username"], user_input["password"]
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during ZeroMouse auth")
                errors["base"] = "unknown"
            else:
                self._username = user_input["username"]
                self._password = user_input["password"]
                self._refresh_token = result["refresh_token"]
                self._identity_id = result["identity_id"]
                self._id_token = result.get("id_token")

                self._owner_id_guess = (
                    _guess_owner_id_from_token(self._id_token) if self._id_token else None
                )

                if self._owner_id_guess:
                    self._discovered_devices = await self.hass.async_add_executor_job(
                        _discover_devices, self._id_token, self._owner_id_guess
                    )

                if self._discovered_devices:
                    return await self.async_step_pick_device()
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Real device picker, backed by the confirmed listFlapByOwnerID
        query - shows friendly names, not raw IDs."""
        if user_input is not None:
            chosen_id = user_input[CONF_DEVICE_ID]

            if chosen_id == "__manual__":
                return await self.async_step_device()

            await self.async_set_unique_id(chosen_id)
            self._abort_if_unique_id_configured()

            chosen_device = next(
                (d for d in self._discovered_devices if d["device_id"] == chosen_id),
                None,
            )
            device_name = (chosen_device or {}).get("name") or f"ZeroMouse {chosen_id[:8]}"

            return self.async_create_entry(
                title=device_name,
                data={
                    "username": self._username,
                    "password": self._password,
                    CONF_REFRESH_TOKEN: self._refresh_token,
                    "identity_id": self._identity_id,
                    CONF_OWNER_ID: self._owner_id_guess,
                    CONF_DEVICE_ID: chosen_id,
                    CONF_DEVICE_NAME: device_name,
                },
            )

        options = {
            d["device_id"]: f"{d['name']} ({d['model']})" if d["model"] else d["name"]
            for d in self._discovered_devices
        }
        options["__manual__"] = "Enter device ID manually..."

        schema = vol.Schema({vol.Required(CONF_DEVICE_ID): vol.In(options)})
        return self.async_show_form(step_id="pick_device", data_schema=schema)

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual fallback: used when discovery finds nothing, or the user
        picked the manual-entry escape hatch from the picker step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_DEVICE_ID])
            self._abort_if_unique_id_configured()

            device_name = f"ZeroMouse {user_input[CONF_DEVICE_ID][:8]}"

            return self.async_create_entry(
                title=device_name,
                data={
                    "username": self._username,
                    "password": self._password,
                    CONF_REFRESH_TOKEN: self._refresh_token,
                    "identity_id": self._identity_id,
                    CONF_OWNER_ID: user_input[CONF_OWNER_ID],
                    CONF_DEVICE_ID: user_input[CONF_DEVICE_ID],
                    CONF_DEVICE_NAME: device_name,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_OWNER_ID, default=self._owner_id_guess or ""
                ): str,
                vol.Required(CONF_DEVICE_ID): str,
            }
        )
        return self.async_show_form(
            step_id="device", data_schema=schema, errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return ZeroMouseOptionsFlow()


class ZeroMouseOptionsFlow(config_entries.OptionsFlow):
    """Options flow: lets the user tune the poll interval and
    include_exits setting after setup.

    Deliberately no __init__ here - newer Home Assistant versions
    (2024.12+) manage self.config_entry automatically via a read-only
    property on the base OptionsFlow class. Manually assigning to it (as
    older HA custom-component tutorials show) now raises an error and
    crashes the options flow with a 500."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_poll = self.config_entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        current_include_exits = self.config_entry.options.get(
            CONF_INCLUDE_EXITS, DEFAULT_INCLUDE_EXITS
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_POLL_INTERVAL, default=current_poll): vol.All(
                    vol.Coerce(int), vol.Range(min=15, max=3600)
                ),
                vol.Required(
                    CONF_INCLUDE_EXITS, default=current_include_exits
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
