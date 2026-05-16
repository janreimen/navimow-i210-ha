"""Update platform for the Navimow i210 integration."""
from __future__ import annotations

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NavimowI210Coordinator
from .entity import NavimowI210Entity

_DESCRIPTION = UpdateEntityDescription(
    key="firmware_update",
    name="Firmware Update",
    icon="mdi:package-up",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        NavimowI210UpdateEntity(coord)
        for coord in data["coordinators"].values()
    )


class NavimowI210UpdateEntity(NavimowI210Entity, UpdateEntity):
    """Reports firmware update availability."""

    _attr_supported_features = UpdateEntityFeature.RELEASE_NOTES

    def __init__(self, coordinator: NavimowI210Coordinator) -> None:
        super().__init__(coordinator, _DESCRIPTION)

    @property
    def installed_version(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.firmware.installed_version

    @property
    def latest_version(self) -> str | None:
        if not self.coordinator.data:
            return None
        fw = self.coordinator.data.firmware
        return fw.latest_version if fw.update_available else fw.installed_version

    async def async_release_notes(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.firmware.release_notes
