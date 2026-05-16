"""OAuth2 implementation for the Navimow i210 integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.config_entry_oauth2_flow import LocalOAuth2Implementation

from .const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN

_LOGGER = logging.getLogger(__name__)


class NavimowOAuth2Implementation(LocalOAuth2Implementation):
    """OAuth2 implementation for Navimow i210."""

    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        super().__init__(
            hass=hass,
            domain=domain,
            client_id=client_id,
            client_secret=client_secret,
            authorize_url=OAUTH2_AUTHORIZE,
            token_url=OAUTH2_TOKEN,
        )

    @property
    def name(self) -> str:
        return "Navimow i210"

    async def async_generate_authorize_url(self, *args: Any, **kwargs: Any) -> str:
        """Append channel=homeassistant to the authorize URL."""
        url = await super().async_generate_authorize_url(*args, **kwargs)
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault("channel", "homeassistant")
        return urlunparse(parsed._replace(query=urlencode(query)))

    async def _async_refresh_token(self, token: dict[str, Any]) -> dict[str, Any]:
        """Handle token refresh with Navimow-specific error handling.

        Navimow tokens last ~1-2 days.  If there is no refresh_token
        (first-time auth), ask the user to re-authenticate immediately.
        Network / transient errors are re-raised so HA can retry.
        """
        if "refresh_token" not in token:
            raise ConfigEntryAuthFailed(
                "Navimow access token has expired and no refresh token is "
                "available – please re-authenticate."
            )
        try:
            return await super()._async_refresh_token(token)
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            err_lower = str(err).lower()
            if any(k in err_lower for k in ("401", "403", "invalid", "expired", "unauthorized", "forbidden")):
                _LOGGER.warning("Navimow refresh token rejected (%s) – re-auth required.", err)
                raise ConfigEntryAuthFailed(
                    f"Navimow refresh token rejected – please re-authenticate: {err}"
                ) from err
            _LOGGER.warning("Navimow token refresh failed (transient): %s", err)
            raise
