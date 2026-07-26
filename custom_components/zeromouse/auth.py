"""Shared Cognito credential handling for ZeroMouse coordinators."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CLIENT_ID, CONF_REFRESH_TOKEN, IDENTITY_POOL_ID, REGION, USER_POOL_ID

_LOGGER = logging.getLogger(__name__)


class ZeroMouseAuth:
    """Handles Cognito ID token refresh and AWS credential federation,
    shared between the event-polling and shadow-polling coordinators so
    both reuse the same cached token instead of re-authenticating twice
    on every cycle."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._id_token: str | None = None
        self._id_token_expiration: datetime | None = None
        self._identity_id: str | None = None
        self._creds: dict[str, Any] | None = None
        self._creds_expiration: datetime | None = None

    async def async_get_id_token(self) -> str:
        """Return a valid ID token, refreshing only if needed."""
        now = datetime.now(timezone.utc)
        if (
            self._id_token
            and self._id_token_expiration
            and now < self._id_token_expiration - timedelta(minutes=5)
        ):
            return self._id_token

        return await self.hass.async_add_executor_job(self._refresh_id_token_sync)

    async def async_get_aws_credentials(self) -> tuple[str, str, dict[str, Any]]:
        """Return (id_token, identity_id, creds), refreshing as needed.
        Used for the GraphQL + S3 path, which needs full AWS credentials
        rather than just the bearer-style ID token the shadow endpoint uses."""
        now = datetime.now(timezone.utc)
        if (
            self._creds
            and self._creds_expiration
            and now < self._creds_expiration - timedelta(minutes=5)
        ):
            return self._id_token, self._identity_id, self._creds

        id_token = await self.async_get_id_token()
        return await self.hass.async_add_executor_job(
            self._resolve_aws_credentials_sync, id_token
        )

    # -- blocking implementations, run via executor jobs ----------------------

    def _refresh_id_token_sync(self) -> str:
        client = boto3.client("cognito-idp", region_name=REGION)
        refresh_token = self.entry.data.get(CONF_REFRESH_TOKEN)

        if refresh_token:
            try:
                resp = client.initiate_auth(
                    AuthFlow="REFRESH_TOKEN_AUTH",
                    AuthParameters={"REFRESH_TOKEN": refresh_token},
                    ClientId=CLIENT_ID,
                )
                auth_result = resp["AuthenticationResult"]
                self._id_token = auth_result["IdToken"]
                self._id_token_expiration = datetime.now(timezone.utc) + timedelta(
                    seconds=auth_result.get("ExpiresIn", 3600)
                )
                return self._id_token
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Refresh token auth failed (%s); falling back to password re-auth",
                    err,
                )

        from pycognito.aws_srp import AWSSRP  # local import: only needed on fallback

        srp = AWSSRP(
            username=self.entry.data["username"],
            password=self.entry.data["password"],
            pool_id=USER_POOL_ID,
            client_id=CLIENT_ID,
            client=client,
        )
        auth_result = srp.authenticate_user()["AuthenticationResult"]

        new_refresh_token = auth_result.get("RefreshToken")
        if new_refresh_token and new_refresh_token != refresh_token:
            new_data = dict(self.entry.data)
            new_data[CONF_REFRESH_TOKEN] = new_refresh_token
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)

        self._id_token = auth_result["IdToken"]
        self._id_token_expiration = datetime.now(timezone.utc) + timedelta(
            seconds=auth_result.get("ExpiresIn", 3600)
        )
        return self._id_token

    def _resolve_aws_credentials_sync(
        self, id_token: str
    ) -> tuple[str, str, dict[str, Any]]:
        id_client = boto3.client("cognito-identity", region_name=REGION)
        login_key = f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"

        identity_id = id_client.get_id(
            IdentityPoolId=IDENTITY_POOL_ID,
            Logins={login_key: id_token},
        )["IdentityId"]

        creds = id_client.get_credentials_for_identity(
            IdentityId=identity_id,
            Logins={login_key: id_token},
        )["Credentials"]

        self._identity_id = identity_id
        self._creds = creds
        self._creds_expiration = creds["Expiration"]

        return id_token, identity_id, creds
