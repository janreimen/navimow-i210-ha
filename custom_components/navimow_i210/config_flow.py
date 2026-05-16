"""Config flow for the Segway Navimow i210 integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_entry_oauth2_flow

from .auth import NavimowOAuth2Implementation
from .const import (
    API_BASE_URL,
    CLIENT_ID,
    CLIENT_SECRET,
    DOMAIN,
    MQTT_BROKER,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_USERNAME,
)

_LOGGER = logging.getLogger(__name__)


class NavimowI210FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle a Navimow i210 OAuth2 config flow."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    @property
    def oauth2_implementation(self) -> NavimowOAuth2Implementation:
        impl = NavimowOAuth2Implementation(self.hass, DOMAIN, CLIENT_ID, CLIENT_SECRET)
        config_entry_oauth2_flow.async_register_implementation(self.hass, DOMAIN, impl)
        return impl

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if not CLIENT_ID or not CLIENT_SECRET:
            return self.async_abort(reason="missing_config")
        _ = self.oauth2_implementation
        return await super().async_step_user()

    async def async_step_oauth2_authorize(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        _ = self.oauth2_implementation
        return await super().async_step_oauth2_authorize(user_input)

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm", data_schema=None)
        return await super().async_step_user()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> FlowResult:
        if self.source == config_entries.SOURCE_REAUTH:
            existing = self.entry
            self.hass.config_entries.async_update_entry(
                existing, data={**existing.data, **data}
            )
            await self.hass.config_entries.async_reload(existing.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(
            title="Navimow i210",
            data={
                "auth_implementation": DOMAIN,
                **data,
                "api_base_url":   API_BASE_URL,
                "mqtt_broker":    MQTT_BROKER,
                "mqtt_port":      MQTT_PORT,
                "mqtt_username":  MQTT_USERNAME,
                "mqtt_password":  MQTT_PASSWORD,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return NavimowI210OptionsFlow(config_entry)


class NavimowI210OptionsFlow(config_entries.OptionsFlow):
    """Navimow i210 options (placeholder – nothing configurable yet)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=None)
