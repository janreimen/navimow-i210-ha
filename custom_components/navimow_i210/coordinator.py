"""DataUpdateCoordinator for the Segway Navimow i210 integration.

Architecture
============
Primary data source  →  NavimowSDK (MQTT cloud-push via navimow-sdk>=0.1.2)
                         • DeviceStateMessage  (state, battery, signal, position)
                         • DeviceAttributesMessage (extra cloud attributes)
                         • /realtimeDate/location  (postureX/Y/Theta → GPS via
                           HA home coords as origin – ported from andershagenhansen)

HTTP fallback        →  MowerAPI.async_get_device_status()
                         • kicks in when no MQTT message for MQTT_STALE_SECONDS
                         • provides full telemetry, settings, schedule, firmware,
                           errors, trail history (ported from TMA84)

Adaptive polling     →  10 s (active) / 30 s (default) / 60 s (idle/charging)
Backoff              →  exponential up to 5 min after consecutive HTTP errors
HA Events            →  navimow_i210_error / _alert / _mowing_complete / _maintenance
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from mower_sdk.api import MowerAPI
from mower_sdk.errors import MowerAPIError
from mower_sdk.models import (
    Device,
    DeviceAttributesMessage,
    DeviceStateMessage,
    DeviceStatus,
)
from mower_sdk.sdk import NavimowSDK

from .const import (
    DOMAIN,
    HTTP_FALLBACK_MIN_INTERVAL,
    MQTT_STALE_SECONDS,
    get_error_message,
)

_LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data-classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class I210Location:
    latitude: float | None = None
    longitude: float | None = None
    altitude: float = 0.0
    speed: float = 0.0
    hdop: float = 0.0
    satellites_in_use: int = 0
    satellites_in_view: int = 0
    data_valid: bool = False
    posture_x: float | None = None        # metres from VisionFence map origin
    posture_y: float | None = None
    posture_theta: float | None = None    # radians
    source: str = "none"                  # "mqtt_xy" | "mqtt_gps" | "http"


@dataclass
class I210Telemetry:
    state: str = "unknown"                # SDK-normalised ("mowing", "docked", …)
    raw_state: str = ""                   # cloud raw ("WORK_MOWING", …)
    battery: int = 0
    signal_strength: int = 0
    work_mode: str = "standard"
    task_state: str = "no_task"
    mowing_progress: int = 0
    current_mowing_area: float = 0.0
    total_mowing_area: float = 0.0
    total_mowing_time: float = 0.0
    blade_usage_time: float = 0.0
    blade_lifetime_hours: float = 200.0
    network_type: str = ""
    wifi_ssid: str | None = None
    mqtt_connected: bool = False
    battery_voltage: float = 0.0
    battery_temperature_fault: bool = False


@dataclass
class I210Settings:
    cutting_height: int = 40
    work_mode: str = "standard"
    rain_sensor: bool = False
    edge_mowing: bool = False
    mowing_cycle: bool = False
    anti_theft: bool = False
    dark_mode: bool = False
    anti_interference: bool | None = None
    plan_switch: bool = False


@dataclass
class I210Schedule:
    schedule_enabled: bool = False
    next_start: datetime | None = None
    next_end: datetime | None = None


@dataclass
class I210Maintenance:
    blade_usage_hours: float = 0.0
    blade_lifetime_hours: float = 200.0
    blade_remaining_life_pct: float = 100.0
    blade_replacement_needed: bool = False
    maintenance_status: str = "ok"


@dataclass
class I210Error:
    code: int = 0
    title: str = ""
    content: str = ""
    severity: int = 1
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


@dataclass
class I210TrailEntry:
    trail_id: str = ""
    date: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    duration: float = 0.0
    area: float = 0.0


@dataclass
class I210Firmware:
    installed_version: str = "unknown"
    latest_version: str | None = None
    update_available: bool = False
    release_notes: str | None = None
    bms: str = "unknown"
    gps: str = "unknown"
    bluetooth: str = "unknown"
    wifi: str = "unknown"
    blade_motor: str = "unknown"
    charging_station: str = "unknown"
    iot: str = "unknown"
    audio: str = "unknown"
    bump_sensor: str = "unknown"
    vision_fence: str | None = None


@dataclass
class I210Snapshot:
    """Full device snapshot pushed to all HA entities on every update."""
    device: Device
    telemetry: I210Telemetry = field(default_factory=I210Telemetry)
    location: I210Location = field(default_factory=I210Location)
    settings: I210Settings = field(default_factory=I210Settings)
    schedule: I210Schedule = field(default_factory=I210Schedule)
    maintenance: I210Maintenance = field(default_factory=I210Maintenance)
    firmware: I210Firmware = field(default_factory=I210Firmware)
    errors: list[I210Error] = field(default_factory=list)
    trail_history: list[I210TrailEntry] = field(default_factory=list)
    attributes_raw: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# MQTT helpers (ported from andershagenhansen/navimow-ha-custom)
# ─────────────────────────────────────────────────────────────────────────────

def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _extract_position(payload: dict[str, Any]) -> dict[str, float] | None:
    """Scan all known field names for lat / lng."""
    def _from_dict(d: dict) -> dict[str, float] | None:
        lat = _to_float(
            d.get("lat") or d.get("latitude") or d.get("Lat") or d.get("Latitude")
        )
        lng = _to_float(
            d.get("lng") or d.get("lon") or d.get("longitude")
            or d.get("Lng") or d.get("Lon") or d.get("Longitude")
        )
        return {"lat": lat, "lng": lng} if (lat is not None and lng is not None) else None

    result = _from_dict(payload)
    if result:
        return result
    for key in ("position", "location", "gps", "loc", "pos", "coords", "coordinate", "geo"):
        val = payload.get(key)
        if isinstance(val, dict):
            result = _from_dict(val)
            if result:
                return result
    for key in ("params", "value"):
        val = payload.get(key)
        if isinstance(val, dict):
            result = _extract_position(val)
            if result:
                return result
    return None


def _extract_local_coords(payload: dict[str, Any]) -> dict[str, float] | None:
    """Extract postureX/Y/Theta from a /realtimeDate/location payload item."""
    x = _to_float(payload.get("postureX"))
    y = _to_float(payload.get("postureY"))
    theta = _to_float(payload.get("postureTheta"))
    if x is None or y is None:
        return None
    return {"posture_x": x, "posture_y": y, "posture_theta": theta or 0.0}


def _xy_to_latlon(
    posture_x: float,
    posture_y: float,
    origin_lat: float,
    origin_lon: float,
) -> tuple[float, float]:
    """Convert local X/Y metres to GPS, using HA home coords as origin."""
    lat = origin_lat + (posture_y / 111_320.0)
    lon = origin_lon + (
        posture_x / (111_320.0 * math.cos(math.radians(origin_lat)))
    )
    return lat, lon


# ─────────────────────────────────────────────────────────────────────────────
# Coordinator
# ─────────────────────────────────────────────────────────────────────────────

class NavimowI210Coordinator(DataUpdateCoordinator[I210Snapshot]):
    """Per-device coordinator for the Navimow i210."""

    POLL_ACTIVE  = timedelta(seconds=10)
    POLL_DEFAULT = timedelta(seconds=30)
    POLL_IDLE    = timedelta(seconds=60)
    FIRMWARE_INTERVAL = timedelta(hours=1)
    TRAIL_INTERVAL    = timedelta(hours=1)
    MAX_FAILURES = 3
    BACKOFF_INIT = 30   # seconds
    BACKOFF_MAX  = 300

    _ACTIVE_STATES = frozenset({"mowing", "returning", "WORK_MOWING", "WORK_RETURNING", "WORK_MAPPING"})
    _IDLE_STATES   = frozenset({"docked", "charging", "idle", "IDLE_CHARGING", "IDLE_STANDBY", "IDLE_PARKING"})

    def __init__(
        self,
        hass: HomeAssistant,
        sdk: NavimowSDK,
        api: MowerAPI,
        device: Device,
        oauth_session: config_entry_oauth2_flow.OAuth2Session | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device.id}",
            update_interval=self.POLL_DEFAULT,
        )
        self.sdk = sdk
        self.api = api
        self.device = device
        self.oauth_session = oauth_session

        self._last_sdk_state: DeviceStateMessage | None = None
        self._last_sdk_attrs: DeviceAttributesMessage | None = None
        self._last_mqtt_ts:   float | None = None
        self._last_http_ts:   float | None = None
        self._mqtt_location:  I210Location | None = None
        self._failures: int = 0

        self._last_firmware_check: datetime | None = None
        self._last_firmware_data:  I210Firmware | None = None
        self._last_trail_fetch:    datetime | None = None
        self._last_trail_data:     list[I210TrailEntry] = []

        self._prev_state:      str | None = None
        self._prev_task_state: str | None = None

    # ── SDK callbacks ─────────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Register SDK callbacks (must be called from async context)."""
        self.sdk.on_state(self._on_sdk_state)
        self.sdk.on_attributes(self._on_sdk_attrs)

    def _on_sdk_state(self, msg: DeviceStateMessage) -> None:
        if msg.device_id != self.device.id:
            return
        _LOGGER.debug("SDK state: %s battery=%s state=%s", msg.device_id, msg.battery, msg.state)
        self._last_sdk_state = msg
        self._last_mqtt_ts = time.monotonic()
        self.hass.loop.call_soon_threadsafe(self._push_state_from_sdk, msg)

    def _on_sdk_attrs(self, msg: DeviceAttributesMessage) -> None:
        if msg.device_id != self.device.id:
            return
        self._last_sdk_attrs = msg
        self._last_mqtt_ts = time.monotonic()
        self.hass.loop.call_soon_threadsafe(self._push_attrs_from_sdk, msg)

    def _push_state_from_sdk(self, msg: DeviceStateMessage) -> None:
        if self.data is None:
            return
        snap = self.data
        metrics = msg.metrics or {}
        tel = I210Telemetry(
            state=msg.state,
            raw_state=metrics.get("raw_state", msg.state),
            battery=msg.battery or snap.telemetry.battery,
            signal_strength=msg.signal_strength or snap.telemetry.signal_strength,
            work_mode=snap.telemetry.work_mode,
            task_state=snap.telemetry.task_state,
            mowing_progress=snap.telemetry.mowing_progress,
            current_mowing_area=snap.telemetry.current_mowing_area,
            total_mowing_area=snap.telemetry.total_mowing_area,
            total_mowing_time=snap.telemetry.total_mowing_time,
            blade_usage_time=snap.telemetry.blade_usage_time,
            blade_lifetime_hours=snap.telemetry.blade_lifetime_hours,
            network_type=snap.telemetry.network_type,
            wifi_ssid=snap.telemetry.wifi_ssid,
            mqtt_connected=True,
            battery_voltage=snap.telemetry.battery_voltage,
            battery_temperature_fault=snap.telemetry.battery_temperature_fault,
        )
        loc = self._mqtt_location or snap.location
        if msg.position:
            loc = I210Location(
                latitude=msg.position.get("lat"),
                longitude=msg.position.get("lng"),
                data_valid=True,
                source="mqtt_gps",
            )
            self._mqtt_location = loc

        new_snap = I210Snapshot(
            device=snap.device, telemetry=tel, location=loc,
            settings=snap.settings, schedule=snap.schedule,
            maintenance=snap.maintenance, firmware=snap.firmware,
            errors=snap.errors, trail_history=snap.trail_history,
            attributes_raw=snap.attributes_raw,
        )
        self._detect_state_changes(new_snap)
        self.async_set_updated_data(new_snap)

    def _push_attrs_from_sdk(self, msg: DeviceAttributesMessage) -> None:
        if self.data is None:
            return
        snap = self.data
        self.async_set_updated_data(I210Snapshot(
            device=snap.device, telemetry=snap.telemetry, location=snap.location,
            settings=snap.settings, schedule=snap.schedule,
            maintenance=snap.maintenance, firmware=snap.firmware,
            errors=snap.errors, trail_history=snap.trail_history,
            attributes_raw=msg.attributes,
        ))

    # ── Raw MQTT hook (called from __init__ for /realtimeDate/location) ───────

    def handle_raw_mqtt(self, topic: str, payload: dict[str, Any], device_id: str) -> None:
        """Process a raw MQTT message for this device.
        Called via call_soon_threadsafe from the paho thread.
        """
        if device_id != self.device.id:
            return

        if topic.endswith("/realtimeDate/location"):
            items = payload if isinstance(payload, list) else [payload]
            for item in (i for i in items if isinstance(i, dict)):
                local = _extract_local_coords(item)
                if local:
                    lat, lon = _xy_to_latlon(
                        local["posture_x"], local["posture_y"],
                        self.hass.config.latitude, self.hass.config.longitude,
                    )
                    self._mqtt_location = I210Location(
                        latitude=lat, longitude=lon, data_valid=True,
                        posture_x=local["posture_x"],
                        posture_y=local["posture_y"],
                        posture_theta=local["posture_theta"],
                        source="mqtt_xy",
                    )
                    _LOGGER.debug(
                        "VisionFence: x=%.3f y=%.3f θ=%.3f → lat=%.7f lng=%.7f",
                        local["posture_x"], local["posture_y"],
                        local["posture_theta"], lat, lon,
                    )
                    self._push_location_update()
            return

        # Other channels: try to extract GPS
        pos = _extract_position(payload)
        if pos:
            self._mqtt_location = I210Location(
                latitude=pos["lat"], longitude=pos["lng"],
                data_valid=True, source="mqtt_gps",
            )
            self._push_location_update()

        self._last_mqtt_ts = time.monotonic()

    def _push_location_update(self) -> None:
        if self.data is None or self._mqtt_location is None:
            return
        snap = self.data
        self.async_set_updated_data(I210Snapshot(
            device=snap.device, telemetry=snap.telemetry,
            location=self._mqtt_location,
            settings=snap.settings, schedule=snap.schedule,
            maintenance=snap.maintenance, firmware=snap.firmware,
            errors=snap.errors, trail_history=snap.trail_history,
            attributes_raw=snap.attributes_raw,
        ))

    # ── Main polling loop (HTTP fallback) ─────────────────────────────────────

    async def _async_update_data(self) -> I210Snapshot:
        try:
            await self._ensure_valid_token()
        except ConfigEntryAuthFailed:
            raise

        now = time.monotonic()
        mqtt_stale = (
            self._last_mqtt_ts is None
            or (now - self._last_mqtt_ts) > MQTT_STALE_SECONDS
        )
        http_ok = (
            self._last_http_ts is None
            or (now - self._last_http_ts) > HTTP_FALLBACK_MIN_INTERVAL
        )

        if mqtt_stale and http_ok:
            try:
                snap = await self._fetch_full_http()
                self._failures = 0
                self._last_http_ts = now
                self._adjust_poll_interval(snap.telemetry.state)
                self._detect_state_changes(snap)
                return snap
            except MowerAPIError as err:
                self._failures += 1
                _LOGGER.warning(
                    "HTTP fallback error for %s (%d/%d): %s",
                    self.device.id, self._failures, self.MAX_FAILURES, err,
                )
                if self._failures >= self.MAX_FAILURES:
                    raise UpdateFailed(
                        f"Device {self.device.id} unreachable after "
                        f"{self._failures} attempts: {err}"
                    ) from err
                delay = min(self.BACKOFF_INIT * (2 ** (self._failures - 1)), self.BACKOFF_MAX)
                self.update_interval = timedelta(seconds=delay)
                raise UpdateFailed(f"API error for {self.device.id}: {err}") from err

        if self.data is not None:
            # MQTT still fresh – overlay live location if needed
            if self._mqtt_location and self.data.location.source != "mqtt_xy":
                snap = self.data
                return I210Snapshot(
                    device=snap.device, telemetry=snap.telemetry,
                    location=self._mqtt_location,
                    settings=snap.settings, schedule=snap.schedule,
                    maintenance=snap.maintenance, firmware=snap.firmware,
                    errors=snap.errors, trail_history=snap.trail_history,
                    attributes_raw=snap.attributes_raw,
                )
            return self.data

        # Very first call – force HTTP
        return await self._fetch_full_http()

    # ── Full HTTP fetch ───────────────────────────────────────────────────────

    async def _fetch_full_http(self) -> I210Snapshot:
        status: DeviceStatus = await self.api.async_get_device_status(self.device.id)
        raw = status.extra or {}

        tel = I210Telemetry(
            state=status.status.value,
            raw_state=raw.get("vehicleState", status.status.value),
            battery=status.battery,
            signal_strength=status.signal_strength or 0,
            work_mode=raw.get("work_mode", raw.get("workMode", "standard")),
            task_state=raw.get("task_state", raw.get("taskState", "no_task")),
            mowing_progress=int(raw.get("mowing_progress", raw.get("mowingProgress", 0))),
            current_mowing_area=float(raw.get("current_mowing_area", raw.get("currentMowingArea", 0.0))),
            total_mowing_area=float(raw.get("total_mowing_area", raw.get("totalMowingArea", 0.0))),
            total_mowing_time=float(raw.get("total_mowing_time", raw.get("totalMowingTime", 0.0))),
            blade_usage_time=float(raw.get("blade_usage_time", raw.get("bladeUsageTime", 0.0))),
            blade_lifetime_hours=float(raw.get("blade_lifetime_hours", raw.get("bladeLifetimeHours", 200.0))),
            network_type=str(raw.get("network_type", raw.get("networkType", ""))),
            wifi_ssid=raw.get("wifi_ssid", raw.get("wifiSsid")),
            mqtt_connected=bool(raw.get("mqtt_connected", raw.get("mqttConnected", False))),
            battery_voltage=float(raw.get("battery_voltage", raw.get("batteryVoltage", 0.0))),
            battery_temperature_fault=bool(
                raw.get("battery_temperature_fault", raw.get("batteryTemperatureFault", False))
            ),
        )

        # Location – prefer live MQTT coords
        loc = self._mqtt_location
        if loc is None:
            pos = status.position or raw.get("position") or {}
            lat = _to_float(pos.get("lat") or pos.get("latitude"))
            lng = _to_float(pos.get("lng") or pos.get("lon") or pos.get("longitude"))
            loc = I210Location(
                latitude=lat, longitude=lng,
                altitude=float(raw.get("altitude", 0.0)),
                speed=float(raw.get("speed", 0.0)),
                hdop=float(raw.get("hdop", 0.0)),
                satellites_in_use=int(raw.get("satellites_in_use", raw.get("satellitesInUse", 0))),
                satellites_in_view=int(raw.get("satellites_in_view", raw.get("satellitesInView", 0))),
                data_valid=bool(raw.get("gps_data_valid", lat is not None and lat != 0.0)),
                source="http",
            )

        s_raw = raw.get("settings", {}) or {}
        settings = I210Settings(
            cutting_height=int(s_raw.get("cutting_height", raw.get("cuttingHeight", 40))),
            work_mode=s_raw.get("work_mode", raw.get("workMode", "standard")),
            rain_sensor=bool(s_raw.get("rain_sensor", raw.get("rainSensor", False))),
            edge_mowing=bool(s_raw.get("edge_mowing", raw.get("edgeMowing", False))),
            mowing_cycle=bool(s_raw.get("mowing_cycle", raw.get("mowingCycle", False))),
            anti_theft=bool(s_raw.get("anti_theft", raw.get("antiTheft", False))),
            dark_mode=bool(s_raw.get("dark_mode", raw.get("darkMode", False))),
            anti_interference=raw.get("anti_interference", raw.get("antiInterference")),
            plan_switch=bool(s_raw.get("plan_switch", raw.get("planSwitch", False))),
        )

        sc_raw = raw.get("schedule", {}) or {}
        schedule = I210Schedule(
            schedule_enabled=bool(sc_raw.get("schedule_enabled", raw.get("scheduleEnabled", False))),
            next_start=self._parse_dt(sc_raw.get("next_start")),
            next_end=self._parse_dt(sc_raw.get("next_end")),
        )

        lifetime = tel.blade_lifetime_hours
        usage    = tel.blade_usage_time
        remaining_pct = max(0.0, (1.0 - usage / lifetime) * 100.0) if lifetime > 0 else 0.0
        maintenance = I210Maintenance(
            blade_usage_hours=usage,
            blade_lifetime_hours=lifetime,
            blade_remaining_life_pct=round(remaining_pct, 1),
            blade_replacement_needed=remaining_pct < 10.0,
            maintenance_status="blade_replacement_due" if remaining_pct < 10.0 else "ok",
        )

        firmware  = await self._fetch_firmware_throttled(raw)
        errors    = self._parse_errors(raw, status)
        trail     = await self._fetch_trail_throttled(tel.task_state)

        return I210Snapshot(
            device=self.device,
            telemetry=tel, location=loc, settings=settings,
            schedule=schedule, maintenance=maintenance,
            firmware=firmware, errors=errors, trail_history=trail,
            attributes_raw=self._last_sdk_attrs.attributes if self._last_sdk_attrs else {},
        )

    # ── Throttled sub-fetches ─────────────────────────────────────────────────

    async def _fetch_firmware_throttled(self, raw: dict[str, Any]) -> I210Firmware:
        now = datetime.now(tz=timezone.utc)
        if (
            self._last_firmware_data is None
            or self._last_firmware_check is None
            or (now - self._last_firmware_check) >= self.FIRMWARE_INTERVAL
        ):
            fw = raw.get("firmware", {}) or {}
            vr = fw.get("current_versions", {}) or {}
            self._last_firmware_data = I210Firmware(
                installed_version=vr.get("ecu", self.device.firmware_version or "unknown"),
                latest_version=fw.get("new_version"),
                update_available=bool(fw.get("update_available", False)),
                release_notes=fw.get("release_notes"),
                bms=vr.get("bms", "unknown"),
                gps=vr.get("gps", "unknown"),
                bluetooth=vr.get("bluetooth", "unknown"),
                wifi=vr.get("wifi", "unknown"),
                blade_motor=vr.get("blade_motor", "unknown"),
                charging_station=vr.get("charging_station", "unknown"),
                iot=vr.get("iot", "unknown"),
                audio=vr.get("audio", "unknown"),
                bump_sensor=vr.get("bump_sensor", "unknown"),
                vision_fence=vr.get("vision_fence"),
            )
            self._last_firmware_check = now
        return self._last_firmware_data  # type: ignore[return-value]

    async def _fetch_trail_throttled(self, task_state: str) -> list[I210TrailEntry]:
        now = datetime.now(tz=timezone.utc)
        task_just_done = (
            task_state == "completed"
            and self._prev_task_state is not None
            and self._prev_task_state != "completed"
        )
        if (
            not self._last_trail_data
            or self._last_trail_fetch is None
            or (now - self._last_trail_fetch) >= self.TRAIL_INTERVAL
            or task_just_done
        ):
            try:
                status = await self.api.async_get_device_status(self.device.id)
                trails_raw = (status.extra or {}).get("trails", [])
                if isinstance(trails_raw, list):
                    self._last_trail_data = [
                        I210TrailEntry(
                            trail_id=str(t.get("trail_id", "")),
                            date=self._parse_dt(t.get("date")) or datetime.now(tz=timezone.utc),
                            duration=float(t.get("duration", 0.0)),
                            area=float(t.get("area", 0.0)),
                        )
                        for t in trails_raw
                        if isinstance(t, dict)
                    ]
            except MowerAPIError as err:
                _LOGGER.debug("Trail fetch failed (using cache): %s", err)
            self._last_trail_fetch = now
        return self._last_trail_data

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_dt(v: Any) -> datetime | None:
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v))
        except ValueError:
            return None

    @staticmethod
    def _parse_errors(raw: dict[str, Any], status: DeviceStatus) -> list[I210Error]:
        errors: list[I210Error] = []
        for e in raw.get("errors", []):
            if not isinstance(e, dict):
                continue
            code = int(e.get("code", 0))
            ts_str = e.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(str(ts_str)) if ts_str else datetime.now(tz=timezone.utc)
            except ValueError:
                ts = datetime.now(tz=timezone.utc)
            errors.append(I210Error(
                code=code,
                title=str(e.get("title", get_error_message(code))),
                content=str(e.get("content", "")),
                severity=int(e.get("severity", 1)),
                timestamp=ts,
            ))
        if not errors and status.error_code and status.error_code.value != "none":
            errors.append(I210Error(
                code=0,
                title=str(status.error_code.value),
                content=status.error_message or "",
                severity=2,
            ))
        return errors

    def _adjust_poll_interval(self, state: str) -> None:
        if state in self._ACTIVE_STATES:
            new = self.POLL_ACTIVE
        elif state in self._IDLE_STATES:
            new = self.POLL_IDLE
        else:
            new = self.POLL_DEFAULT
        if self.update_interval != new:
            _LOGGER.debug(
                "Poll interval for %s changed %s→%s (state=%s)",
                self.device.id, self.update_interval, new, state,
            )
            self.update_interval = new

    def _detect_state_changes(self, snap: I210Snapshot) -> None:
        state      = snap.telemetry.state
        task_state = snap.telemetry.task_state

        # New error
        if snap.errors and self._prev_state != "error" and state == "error":
            for err in snap.errors:
                self.hass.bus.async_fire(f"{DOMAIN}_error", {
                    "device_id": self.device.id,
                    "code": err.code, "title": err.title,
                    "content": err.content, "severity": err.severity,
                })
                if err.code in (1, 2):
                    self.hass.bus.async_fire(f"{DOMAIN}_alert", {
                        "device_id": self.device.id,
                        "alert_type": "lifted" if err.code == 1 else "stuck",
                    })
                if err.severity >= 3:
                    self.hass.components.persistent_notification.async_create(
                        message=f"Navimow i210 {self.device.id}: {err.title}\n\n{err.content}",
                        title=f"Navimow i210 – Critical Error (code {err.code})",
                        notification_id=f"{DOMAIN}_error_{self.device.id}_{err.code}",
                    )

        # Mowing session completed
        if task_state == "completed" and self._prev_task_state not in (None, "completed"):
            self.hass.bus.async_fire(f"{DOMAIN}_mowing_complete", {
                "device_id": self.device.id,
                "area":  snap.telemetry.current_mowing_area,
                "total": snap.telemetry.total_mowing_time,
            })

        # Blade replacement
        if snap.maintenance.blade_replacement_needed and not (
            self.data and self.data.maintenance.blade_replacement_needed
        ):
            self.hass.bus.async_fire(f"{DOMAIN}_maintenance", {
                "device_id": self.device.id,
                "status": snap.maintenance.maintenance_status,
                "blade_remaining_pct": snap.maintenance.blade_remaining_life_pct,
            })

        self._prev_state      = state
        self._prev_task_state = task_state

    # ── Token refresh ─────────────────────────────────────────────────────────

    async def _ensure_valid_token(self) -> None:
        if not self.oauth_session:
            return
        try:
            if hasattr(self.oauth_session, "async_ensure_token_valid"):
                await self.oauth_session.async_ensure_token_valid()
                token = self.oauth_session.token
            elif hasattr(self.oauth_session, "async_get_valid_token"):
                token = await self.oauth_session.async_get_valid_token()
            else:
                token = self.oauth_session.token
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            cached = getattr(self.oauth_session, "token", None)
            if cached and cached.get("access_token"):
                self.api.set_token(cached["access_token"])
                return
            raise ConfigEntryAuthFailed(f"Token refresh failed: {err}") from err

        if not (token and token.get("access_token")):
            raise ConfigEntryAuthFailed("No access token available after refresh")
        self.api.set_token(token["access_token"])
