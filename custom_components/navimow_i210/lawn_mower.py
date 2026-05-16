"""Lawn Mower platform for the Navimow i210 integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from mower_sdk.errors import MowerAPIError
from mower_sdk.models import MowerCommand

from .const import DOMAIN, MOWER_STATUS_TO_ACTIVITY
from .coordinator import NavimowI210Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        NavimowI210LawnMower(coord)
        for coord in data["coordinators"].values()
    )


class NavimowI210LawnMower(CoordinatorEntity[NavimowI210Coordinator], LawnMowerEntity):
    """Navimow i210 as a HA LawnMower entity."""

    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.DOCK
    )

    def __init__(self, coordinator: NavimowI210Coordinator) -> None:
        super().__init__(coordinator)
        dev = coordinator.device
        self._attr_name = dev.name
        self._attr_unique_id = f"{DOMAIN}_{dev.id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev.id)},
            name=dev.name,
            manufacturer="Segway",
            model=dev.model or "Navimow i210",
            sw_version=coordinator.data.firmware.installed_version
            if coordinator.data else (dev.firmware_version or None),
            serial_number=dev.serial_number or dev.id,
            configuration_url="https://navimow.segway.com/",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None

    @property
    def activity(self) -> LawnMowerActivity | None:
        if not self.coordinator.data:
            return None
        state = self.coordinator.data.telemetry.state
        act = MOWER_STATUS_TO_ACTIVITY.get(state)
        return LawnMowerActivity(act) if act else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        t = self.coordinator.data.telemetry
        loc = self.coordinator.data.location
        attrs: dict[str, Any] = {
            "battery":             t.battery,
            "state":               t.state,
            "raw_state":           t.raw_state,
            "work_mode":           t.work_mode,
            "task_state":          t.task_state,
            "mowing_progress":     t.mowing_progress,
            "current_mowing_area": t.current_mowing_area,
            "total_mowing_area":   t.total_mowing_area,
            "total_mowing_time":   t.total_mowing_time,
            "signal_strength":     t.signal_strength,
            "mqtt_connected":      t.mqtt_connected,
            "location_source":     loc.source,
        }
        if self.coordinator.data.errors:
            attrs["errors"] = [
                {"code": e.code, "title": e.title}
                for e in self.coordinator.data.errors
            ]
        if loc.posture_x is not None:
            attrs["posture_x"] = loc.posture_x
            attrs["posture_y"] = loc.posture_y
        return attrs

    async def _cmd(self, command: MowerCommand, label: str) -> None:
        await self.coordinator._ensure_valid_token()
        try:
            await self.coordinator.api.async_send_command(
                self.coordinator.device.id, command
            )
        except MowerAPIError as err:
            _LOGGER.error("%s failed: %s", label, err)
            raise
        _LOGGER.debug("%s – device %s", label, self.coordinator.device.id)
        await self.coordinator.async_request_refresh()

    async def async_start_mowing(self) -> None:
        await self._cmd(MowerCommand.START, "Start mowing")

    async def async_pause(self) -> None:
        await self._cmd(MowerCommand.PAUSE, "Pause")

    async def async_dock(self) -> None:
        await self._cmd(MowerCommand.DOCK, "Dock")

    async def async_resume(self) -> None:
        await self._cmd(MowerCommand.RESUME, "Resume")
