"""Select platform for the Navimow i210 integration."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from mower_sdk.errors import MowerAPIError

from .const import DOMAIN
from .coordinator import I210Snapshot, NavimowI210Coordinator
from .entity import NavimowI210Entity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class NavimowSelectDescription(SelectEntityDescription):
    current_option_fn: Callable[[I210Snapshot], str | None]
    setting_key: str


SELECTS: tuple[NavimowSelectDescription, ...] = (
    NavimowSelectDescription(
        key="work_mode",
        name="Work Mode",
        icon="mdi:speedometer",
        options=["standard", "fast", "silent"],
        current_option_fn=lambda s: s.settings.work_mode,
        setting_key="work_mode",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        NavimowI210SelectEntity(coord, desc)
        for coord in data["coordinators"].values()
        for desc in SELECTS
    )


class NavimowI210SelectEntity(NavimowI210Entity, SelectEntity):
    entity_description: NavimowSelectDescription

    @property
    def current_option(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.entity_description.current_option_fn(self.coordinator.data)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator._ensure_valid_token()
        try:
            await self.coordinator.api._async_request(
                "POST",
                "/openapi/smarthome/sendCommands",
                data={
                    "commands": [{
                        "devices": [{"id": self.coordinator.device.id}],
                        "execution": {
                            "command": "action.devices.commands.SetSetting",
                            "params": {
                                "key":   self.entity_description.setting_key,
                                "value": option,
                            },
                        },
                    }]
                },
            )
        except MowerAPIError as err:
            raise HomeAssistantError(f"Failed to set {self.entity_description.key}: {err}") from err
        await self.coordinator.async_request_refresh()
