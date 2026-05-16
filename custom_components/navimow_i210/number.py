"""Number platform for the Navimow i210 integration."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from mower_sdk.errors import MowerAPIError

from .const import DOMAIN
from .coordinator import I210Snapshot, NavimowI210Coordinator
from .entity import NavimowI210Entity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class NavimowNumberDescription(NumberEntityDescription):
    value_fn: Callable[[I210Snapshot], float | None]
    setting_key: str


NUMBERS: tuple[NavimowNumberDescription, ...] = (
    NavimowNumberDescription(
        key="cutting_height",
        name="Cutting Height",
        icon="mdi:grass",
        native_min_value=20,
        native_max_value=60,
        native_step=5,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        mode=NumberMode.SLIDER,
        value_fn=lambda s: float(s.settings.cutting_height),
        setting_key="cutting_height",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        NavimowI210NumberEntity(coord, desc)
        for coord in data["coordinators"].values()
        for desc in NUMBERS
    )


class NavimowI210NumberEntity(NavimowI210Entity, NumberEntity):
    entity_description: NavimowNumberDescription

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
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
                                "value": int(value),
                            },
                        },
                    }]
                },
            )
        except MowerAPIError as err:
            raise HomeAssistantError(
                f"Failed to set {self.entity_description.key}: {err}"
            ) from err
        await self.coordinator.async_request_refresh()
