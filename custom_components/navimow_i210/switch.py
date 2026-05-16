"""Switch platform for the Navimow i210 integration."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
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
class NavimowSwitchDescription(SwitchEntityDescription):
    value_fn: Callable[[I210Snapshot], bool | None]
    setting_key: str


SWITCHES: tuple[NavimowSwitchDescription, ...] = (
    NavimowSwitchDescription(
        key="schedule_enabled",
        name="Schedule",
        icon="mdi:calendar-clock",
        value_fn=lambda s: s.settings.plan_switch,
        setting_key="plan_switch",
    ),
    NavimowSwitchDescription(
        key="rain_sensor",
        name="Rain Sensor",
        icon="mdi:weather-rainy",
        value_fn=lambda s: s.settings.rain_sensor,
        setting_key="rain_sensor",
    ),
    NavimowSwitchDescription(
        key="edge_mowing",
        name="Edge Mowing",
        icon="mdi:border-all-variant",
        value_fn=lambda s: s.settings.edge_mowing,
        setting_key="edge_mowing",
    ),
    NavimowSwitchDescription(
        key="mowing_cycle",
        name="Mowing Cycle",
        icon="mdi:refresh",
        value_fn=lambda s: s.settings.mowing_cycle,
        setting_key="mowing_cycle",
    ),
    NavimowSwitchDescription(
        key="anti_theft",
        name="Anti-Theft",
        icon="mdi:shield-lock",
        value_fn=lambda s: s.settings.anti_theft,
        setting_key="anti_theft",
    ),
    NavimowSwitchDescription(
        key="dark_mode",
        name="Dark Mode",
        icon="mdi:brightness-3",
        value_fn=lambda s: s.settings.dark_mode,
        setting_key="dark_mode",
    ),
)

_ANTI_INTERFERENCE = NavimowSwitchDescription(
    key="anti_interference",
    name="Anti-Interference",
    icon="mdi:wifi-off",
    value_fn=lambda s: bool(s.settings.anti_interference)
    if s.settings.anti_interference is not None
    else None,
    setting_key="anti_interference",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coords: dict[str, NavimowI210Coordinator] = data["coordinators"]
    entities: list[NavimowI210SwitchEntity] = []
    for coord in coords.values():
        for desc in SWITCHES:
            entities.append(NavimowI210SwitchEntity(coord, desc))
        if coord.data and coord.data.settings.anti_interference is not None:
            entities.append(NavimowI210SwitchEntity(coord, _ANTI_INTERFERENCE))
    async_add_entities(entities)


class NavimowI210SwitchEntity(NavimowI210Entity, SwitchEntity):
    entity_description: NavimowSwitchDescription

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    async def _set(self, value: bool) -> None:
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
                                "value": value,
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

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._set(False)
