"""Segway Navimow i210 integration for Home Assistant.

Domain: navimow_i210  →  runs independently of any other Navimow integration.

Setup flow
----------
1. Register OAuth2 implementation (domain=navimow_i210)
2. Exchange token → MowerAPI
3. Discover devices via /openapi/smarthome/authList
4. Fetch MQTT credentials via /openapi/mqtt/userInfo/get/v2
5. Create NavimowSDK  →  connects to cloud MQTT broker
6. Attach MQTT hooks  →  state / event / attributes / location channels
7. Create one NavimowI210Coordinator per device (MQTT-first, HTTP fallback)
8. Forward-setup all platforms
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)


def _mask(v: str | None) -> str:
    if not v:
        return "<empty>"
    return f"{v[:2]}***{v[-2:]}" if len(v) > 4 else "****"


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {})
    config_entry_oauth2_flow.async_register_implementation(
        hass,
        DOMAIN,
        NavimowOAuth2Implementation(hass, DOMAIN, CLIENT_ID, CLIENT_SECRET),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Navimow i210 from a config entry."""
    from mower_sdk.api import MowerAPI
    from mower_sdk.errors import MowerAPIError
    from mower_sdk.sdk import NavimowSDK

    from .coordinator import NavimowI210Coordinator
    from .services import async_setup_services

    hass.data.setdefault(DOMAIN, {})

    # ── 1. OAuth2 session ────────────────────────────────────────────────────
    try:
        implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
        oauth_session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

        token: dict[str, Any] | None = None
        for method in ("async_get_valid_token", None):
            if method and hasattr(oauth_session, method):
                try:
                    token = await getattr(oauth_session, method)()
                    break
                except Exception:
                    pass
        if not token:
            if hasattr(oauth_session, "async_ensure_token_valid"):
                await oauth_session.async_ensure_token_valid()
            token = getattr(oauth_session, "token", None) or entry.data.get("token")

        if not (token and token.get("access_token")):
            raise ConfigEntryAuthFailed("No valid token available")

        access_token: str = token["access_token"]

    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err

    # ── 2. MowerAPI ──────────────────────────────────────────────────────────
    api = MowerAPI(
        session=async_get_clientsession(hass),
        token=access_token,
        base_url=entry.data.get("api_base_url", API_BASE_URL),
    )

    # ── 3. Device discovery ──────────────────────────────────────────────────
    try:
        devices = await api.async_get_devices()
    except MowerAPIError as err:
        raise ConfigEntryNotReady(f"Device discovery failed: {err}") from err
    except Exception as err:
        raise ConfigEntryAuthFailed(f"Auth error during discovery: {err}") from err

    if not devices:
        _LOGGER.warning("No Navimow i210 devices found on this account")

    # ── 4. MQTT credentials ──────────────────────────────────────────────────
    try:
        mqtt_info = await api.async_get_mqtt_user_info()
    except MowerAPIError as err:
        raise ConfigEntryNotReady(f"MQTT info failed: {err}") from err

    mqtt_host = mqtt_info.get("mqttHost") or entry.data.get("mqtt_broker", MQTT_BROKER)
    mqtt_url  = mqtt_info.get("mqttUrl")
    mqtt_user = mqtt_info.get("userName")  or entry.data.get("mqtt_username", MQTT_USERNAME)
    mqtt_pass = mqtt_info.get("pwdInfo")   or entry.data.get("mqtt_password", MQTT_PASSWORD)
    mqtt_port: int = entry.data.get("mqtt_port", MQTT_PORT)
    ws_path: str | None = None
    auth_headers: dict[str, str] | None = None

    if mqtt_url:
        parsed = urlparse(mqtt_url)
        if parsed.scheme in ("ws", "wss") and parsed.hostname:
            mqtt_host = parsed.hostname
            mqtt_port = parsed.port or 443
            ws_path = parsed.path or "/"
            if parsed.query:
                ws_path = f"{ws_path}?{parsed.query}"
        auth_headers = {"Authorization": f"Bearer {access_token}"}

    _LOGGER.info(
        "Navimow i210 MQTT: broker=%s port=%s user=%s wss=%s",
        mqtt_host, mqtt_port, _mask(mqtt_user), ws_path is not None,
    )

    # ── 5. NavimowSDK ────────────────────────────────────────────────────────
    _unload_flag:        list[bool]         = [False]
    _mqtt_refresh_lock:  asyncio.Lock       = asyncio.Lock()

    def _build_sdk() -> NavimowSDK:
        sdk = NavimowSDK(
            broker=mqtt_host,
            port=mqtt_port,
            username=mqtt_user,
            password=mqtt_pass,
            ws_path=ws_path,
            auth_headers=auth_headers,
            loop=hass.loop,
            records=devices,
            keepalive_seconds=2400,
            reconnect_min_delay=1,
            reconnect_max_delay=60,
        )
        sdk.connect()
        return sdk

    sdk: NavimowSDK = await hass.async_add_executor_job(_build_sdk)

    # ── 6. Coordinators ──────────────────────────────────────────────────────
    coordinators: dict[str, NavimowI210Coordinator] = {}
    for device in devices:
        coord = NavimowI210Coordinator(
            hass=hass,
            sdk=sdk,
            api=api,
            device=device,
            oauth_session=oauth_session,
        )
        await coord.async_setup()
        await coord.async_config_entry_first_refresh()
        coordinators[device.id] = coord

    # ── 7. MQTT hooks ────────────────────────────────────────────────────────
    _attach_mqtt_hooks(
        hass=hass,
        sdk=sdk,
        api=api,
        oauth_session=oauth_session,
        coordinators=coordinators,
        access_token=access_token,
        lock=_mqtt_refresh_lock,
        unload_flag=_unload_flag,
    )

    # ── 8. Services + platforms ──────────────────────────────────────────────
    async_setup_services(hass, api, coordinators)

    hass.data[DOMAIN][entry.entry_id] = {
        "sdk":          sdk,
        "api":          api,
        "devices":      devices,
        "coordinators": coordinators,
        "unload_flag":  _unload_flag,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


# ── MQTT hook wiring ──────────────────────────────────────────────────────────

def _attach_mqtt_hooks(
    hass: HomeAssistant,
    sdk: Any,
    api: Any,
    oauth_session: Any,
    coordinators: dict,
    access_token: str,
    lock: asyncio.Lock,
    unload_flag: list[bool],
) -> None:
    mqtt = sdk._mqtt
    original_on_message = mqtt.on_message

    async def _on_ready() -> None:
        _LOGGER.info("Navimow i210 MQTT ready – subscribing channels")
        for device_id in list(coordinators):
            for ch in ("state", "event", "attributes", "location"):
                topic = f"/downlink/vehicle/{device_id}/realtimeDate/{ch}"
                rc, mid = mqtt.client.subscribe(topic)
                _LOGGER.debug("Subscribed %s rc=%s mid=%s", topic, rc, mid)

    async def _on_disconnected() -> None:
        if unload_flag[0] or lock.locked():
            return
        async with lock:
            if unload_flag[0]:
                return
            await _refresh_mqtt_credentials(sdk, api, oauth_session, hass)

    async def _on_message(topic: str, payload: bytes, device_id: str) -> None:
        text = (payload or b"").decode("utf-8", errors="replace")
        try:
            import json as _json
            parsed = _json.loads(text)
            items = parsed if isinstance(parsed, list) else [parsed]
            coord = coordinators.get(device_id)
            if coord:
                for item in items:
                    if isinstance(item, dict):
                        item.setdefault("device_id", device_id)
                        coord.handle_raw_mqtt(topic, item, device_id)
        except Exception:
            pass
        if original_on_message:
            await original_on_message(topic, payload, device_id)

    mqtt.on_ready        = _on_ready
    mqtt.on_disconnected = _on_disconnected
    mqtt.on_message      = _on_message

    def _on_subscribe(_c, _u, mid, granted_qos, *a, **kw):
        _LOGGER.debug("MQTT subscribed: mid=%s qos=%s", mid, granted_qos)

    mqtt.client.on_subscribe = _on_subscribe

    if mqtt.is_connected:
        hass.async_create_task(_on_ready())


async def _refresh_mqtt_credentials(
    sdk: Any, api: Any, oauth_session: Any, hass: HomeAssistant
) -> None:
    new_token: str | None = None
    new_auth: dict[str, str] | None = None
    try:
        if hasattr(oauth_session, "async_ensure_token_valid"):
            await oauth_session.async_ensure_token_valid()
            fresh = oauth_session.token
        elif hasattr(oauth_session, "async_get_valid_token"):
            fresh = await oauth_session.async_get_valid_token()
        else:
            fresh = oauth_session.token
        if fresh and fresh.get("access_token"):
            new_token = fresh["access_token"]
            api.set_token(new_token)
            new_auth = {"Authorization": f"Bearer {new_token}"}
    except Exception as err:
        _LOGGER.warning("Token refresh on MQTT disconnect failed: %s", err)

    try:
        info = await api.async_get_mqtt_user_info()
    except Exception as err:
        _LOGGER.warning("MQTT credential refresh failed: %s", err)
        return

    new_user = info.get("userName")
    new_pass = info.get("pwdInfo")

    def _do() -> None:
        sdk.update_mqtt_credentials(
            auth_headers=new_auth, username=new_user, password=new_pass
        )

    await hass.async_add_executor_job(_do)
    _LOGGER.info("Navimow i210 MQTT credentials refreshed")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        data.get("unload_flag", [False])[0] = True
        sdk = data.get("sdk")
        if sdk:
            try:
                sdk.disconnect()
            except Exception as err:
                _LOGGER.warning("MQTT disconnect error: %s", err)
    return unload_ok
