"""Binary sensor platform for the Navimow i210 integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import I210Snapshot, NavimowI210Coordinator
from .entity import NavimowI210Entity


@dataclass(frozen=True, kw_only=True)
class NavimowBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[I210Snapshot], bool | None]


BINARY_SENSORS: tuple[NavimowBinarySensorDescription, ...] = (
    NavimowBinarySensorDescription(
        key="charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda s: s.telemetry.state in ("docked", "charging"),
    ),
    NavimowBinarySensorDescription(
        key="battery_temperature_fault",
        name="Battery Temperature Fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:thermometer-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.telemetry.battery_temperature_fault,
    ),
    NavimowBinarySensorDescription(
        key="mqtt_connected",
        name="Cloud Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.telemetry.mqtt_connected,
    ),
    NavimowBinarySensorDescription(
        key="has_error",
        name="Has Error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle",
        value_fn=lambda s: len(s.errors) > 0,
    ),
    NavimowBinarySensorDescription(
        key="blade_replacement_needed",
        name="Blade Replacement Needed",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:fan-alert",
        value_fn=lambda s: s.maintenance.blade_replacement_needed,
    ),
    NavimowBinarySensorDescription(
        key="gps_valid",
        name="GPS Valid",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:crosshairs-gps",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.location.data_valid,
    ),
    NavimowBinarySensorDescription(
        key="schedule_active",
        name="Schedule Active",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:calendar-clock",
        value_fn=lambda s: s.schedule.schedule_enabled,
    ),
    NavimowBinarySensorDescription(
        key="firmware_update_available",
        name="Firmware Update Available",
        device_class=BinarySensorDeviceClass.UPDATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.firmware.update_available,
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
        NavimowI210BinarySensorEntity(coord, desc)
        for coord in coords.values()
        for desc in BINARY_SENSORS
    )


class NavimowI210BinarySensorEntity(NavimowI210Entity, BinarySensorEntity):
    entity_description: NavimowBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
