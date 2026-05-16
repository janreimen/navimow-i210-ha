"""Shared base entity for the Navimow i210 integration."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NavimowI210Coordinator


class NavimowI210Entity(CoordinatorEntity[NavimowI210Coordinator]):
    """Base entity – provides device_info and unique_id for every platform."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NavimowI210Coordinator,
        description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        dev = coordinator.device
        self._attr_unique_id = f"{DOMAIN}_{dev.id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev.id)},
            name=dev.name,
            manufacturer="Segway",
            model=dev.model or "Navimow i210",
            sw_version=coordinator.data.firmware.installed_version
            if coordinator.data
            else (dev.firmware_version or None),
            serial_number=dev.serial_number or dev.id,
            configuration_url="https://navimow.segway.com/",
        )
