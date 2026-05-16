"""Device Tracker platform for the Navimow i210 integration."""
from __future__ import annotations

import math

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NavimowI210Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        NavimowI210Tracker(coord)
        for coord in data["coordinators"].values()
    )


class NavimowI210Tracker(CoordinatorEntity[NavimowI210Coordinator], TrackerEntity):
    """GPS tracker for the Navimow i210 mower.

    Location source priority:
      1. MQTT /realtimeDate/location  (postureX/Y → GPS via HA home as origin)
      2. MQTT DeviceStateMessage.position
      3. HTTP getVehicleStatus GPS fields
    """

    _attr_has_entity_name = True
    _attr_translation_key = "mower_location"

    def __init__(self, coordinator: NavimowI210Coordinator) -> None:
        super().__init__(coordinator)
        dev = coordinator.device
        self._attr_unique_id = f"{DOMAIN}_{dev.id}_tracker"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev.id)},
            name=dev.name,
            manufacturer="Segway",
            model=dev.model or "Navimow i210",
            sw_version=coordinator.data.firmware.installed_version
            if coordinator.data else (dev.firmware_version or None),
            serial_number=dev.serial_number or dev.id,
        )

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        if not self.coordinator.data:
            return None
        loc = self.coordinator.data.location
        return loc.latitude if loc.data_valid else None

    @property
    def longitude(self) -> float | None:
        if not self.coordinator.data:
            return None
        loc = self.coordinator.data.location
        return loc.longitude if loc.data_valid else None

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        loc = self.coordinator.data.location
        attrs: dict = {"location_source": loc.source}
        if loc.posture_x is not None:
            attrs["posture_x"] = round(loc.posture_x, 3)
            attrs["posture_y"] = round(loc.posture_y, 3)
        if loc.posture_theta is not None:
            attrs["heading_deg"] = round((loc.posture_theta * 180.0 / math.pi) % 360, 1)
        attrs.update({
            "altitude":           loc.altitude,
            "speed":              loc.speed,
            "hdop":               loc.hdop,
            "satellites_in_use":  loc.satellites_in_use,
            "satellites_in_view": loc.satellites_in_view,
            "gps_valid":          loc.data_valid,
        })
        return attrs

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None
