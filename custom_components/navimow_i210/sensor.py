"""Sensor platform for the Navimow i210 integration."""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import I210Snapshot, NavimowI210Coordinator
from .entity import NavimowI210Entity


@dataclass(frozen=True, kw_only=True)
class NavimowSensorDescription(SensorEntityDescription):
    value_fn: Callable[[I210Snapshot], Any]
    extra_attrs_fn: Callable[[I210Snapshot], dict[str, Any]] | None = None


SENSORS: tuple[NavimowSensorDescription, ...] = (
    # ── Battery ──────────────────────────────────────────────────────────────
    NavimowSensorDescription(
        key="battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.telemetry.battery,
    ),
    NavimowSensorDescription(
        key="battery_voltage",
        name="Battery Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.telemetry.battery_voltage or None,
    ),
    # ── Status ────────────────────────────────────────────────────────────────
    NavimowSensorDescription(
        key="mower_state",
        name="Mower State",
        icon="mdi:robot-mower",
        value_fn=lambda s: s.telemetry.state,
    ),
    NavimowSensorDescription(
        key="work_mode",
        name="Work Mode",
        icon="mdi:speedometer",
        value_fn=lambda s: s.telemetry.work_mode,
    ),
    NavimowSensorDescription(
        key="task_state",
        name="Task State",
        icon="mdi:clipboard-check",
        value_fn=lambda s: s.telemetry.task_state,
    ),
    NavimowSensorDescription(
        key="mowing_progress",
        name="Mowing Progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:progress-clock",
        value_fn=lambda s: s.telemetry.mowing_progress,
    ),
    NavimowSensorDescription(
        key="current_mowing_area",
        name="Current Mowing Area",
        native_unit_of_measurement="m²",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:grass",
        value_fn=lambda s: s.telemetry.current_mowing_area,
    ),
    NavimowSensorDescription(
        key="total_mowing_area",
        name="Total Mowing Area",
        native_unit_of_measurement="m²",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:map-marker-distance",
        value_fn=lambda s: s.telemetry.total_mowing_area,
    ),
    NavimowSensorDescription(
        key="total_mowing_time",
        name="Total Mowing Time",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda s: s.telemetry.total_mowing_time,
    ),
    # ── GPS ───────────────────────────────────────────────────────────────────
    NavimowSensorDescription(
        key="gps_latitude",
        name="GPS Latitude",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:latitude",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.location.latitude if s.location.data_valid else None,
    ),
    NavimowSensorDescription(
        key="gps_longitude",
        name="GPS Longitude",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:longitude",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.location.longitude if s.location.data_valid else None,
    ),
    NavimowSensorDescription(
        key="gps_altitude",
        name="GPS Altitude",
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DISTANCE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.location.altitude or None,
    ),
    NavimowSensorDescription(
        key="gps_speed",
        name="GPS Speed",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.SPEED,
        value_fn=lambda s: s.location.speed,
    ),
    NavimowSensorDescription(
        key="gps_hdop",
        name="GPS HDOP",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:crosshairs-gps",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.location.hdop or None,
    ),
    NavimowSensorDescription(
        key="satellites_in_use",
        name="Satellites In Use",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:satellite",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.location.satellites_in_use,
    ),
    NavimowSensorDescription(
        key="satellites_in_view",
        name="Satellites In View",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:satellite-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.location.satellites_in_view,
    ),
    # VisionFence local coords (from MQTT /realtimeDate/location)
    NavimowSensorDescription(
        key="posture_x",
        name="Posture X",
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:axis-x-arrow",
        value_fn=lambda s: round(s.location.posture_x, 3) if s.location.posture_x is not None else None,
    ),
    NavimowSensorDescription(
        key="posture_y",
        name="Posture Y",
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:axis-y-arrow",
        value_fn=lambda s: round(s.location.posture_y, 3) if s.location.posture_y is not None else None,
    ),
    NavimowSensorDescription(
        key="posture_theta",
        name="Heading",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:rotate-right",
        value_fn=lambda s: (
            round((s.location.posture_theta * 180.0 / math.pi) % 360, 1)
            if s.location.posture_theta is not None else None
        ),
    ),
    # ── Connectivity ─────────────────────────────────────────────────────────
    NavimowSensorDescription(
        key="network_type",
        name="Network Type",
        icon="mdi:network",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.telemetry.network_type or None,
    ),
    NavimowSensorDescription(
        key="signal_strength",
        name="Signal Strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.telemetry.signal_strength or None,
    ),
    NavimowSensorDescription(
        key="wifi_ssid",
        name="WiFi SSID",
        icon="mdi:wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.telemetry.wifi_ssid,
    ),
    # ── Maintenance ───────────────────────────────────────────────────────────
    NavimowSensorDescription(
        key="blade_usage_time",
        name="Blade Usage Time",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.DURATION,
        icon="mdi:fan",
        value_fn=lambda s: s.maintenance.blade_usage_hours,
    ),
    NavimowSensorDescription(
        key="blade_remaining_life",
        name="Blade Remaining Life",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan-alert",
        value_fn=lambda s: s.maintenance.blade_remaining_life_pct,
    ),
    NavimowSensorDescription(
        key="maintenance_status",
        name="Maintenance Status",
        icon="mdi:wrench",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.maintenance.maintenance_status,
    ),
    # ── Schedule ─────────────────────────────────────────────────────────────
    NavimowSensorDescription(
        key="next_schedule_start",
        name="Next Schedule Start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: s.schedule.next_start,
    ),
    NavimowSensorDescription(
        key="next_schedule_end",
        name="Next Schedule End",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: s.schedule.next_end,
    ),
    # ── Mowing history ───────────────────────────────────────────────────────
    NavimowSensorDescription(
        key="last_mowing_date",
        name="Last Mowing Date",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: s.trail_history[0].date if s.trail_history else None,
        extra_attrs_fn=lambda s: {
            "duration_hours": s.trail_history[0].duration,
            "area_m2":        s.trail_history[0].area,
            "history": [
                {"date": str(t.date), "duration": t.duration, "area": t.area}
                for t in s.trail_history[:7]
            ],
        } if s.trail_history else {},
    ),
    # ── Diagnostics ───────────────────────────────────────────────────────────
    NavimowSensorDescription(
        key="firmware_version",
        name="Firmware Version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.firmware.installed_version,
        extra_attrs_fn=lambda s: {
            "bms": s.firmware.bms, "gps": s.firmware.gps,
            "bluetooth": s.firmware.bluetooth, "wifi": s.firmware.wifi,
            "blade_motor": s.firmware.blade_motor,
            "charging_station": s.firmware.charging_station,
            "iot": s.firmware.iot, "audio": s.firmware.audio,
            "bump_sensor": s.firmware.bump_sensor,
            "vision_fence": s.firmware.vision_fence,
        },
    ),
    NavimowSensorDescription(
        key="device_model",
        name="Device Model",
        icon="mdi:robot-mower-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.device.model,
    ),
    NavimowSensorDescription(
        key="error_code",
        name="Error Code",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.errors[0].code if s.errors else 0,
        extra_attrs_fn=lambda s: {
            "message": s.errors[0].title,
            "content": s.errors[0].content,
        } if s.errors else {},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coords: dict[str, NavimowI210Coordinator] = data["coordinators"]
    async_add_entities(
        NavimowI210SensorEntity(coord, desc)
        for coord in coords.values()
        for desc in SENSORS
    )


class NavimowI210SensorEntity(NavimowI210Entity, SensorEntity):
    entity_description: NavimowSensorDescription

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.entity_description.extra_attrs_fn or not self.coordinator.data:
            return None
        return self.entity_description.extra_attrs_fn(self.coordinator.data)
