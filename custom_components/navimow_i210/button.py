"""Button platform for the Navimow i210 integration."""
from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from mower_sdk.errors import MowerAPIError
from mower_sdk.models import MowerCommand

from .const import DOMAIN
from .coordinator import NavimowI210Coordinator
from .entity import NavimowI210Entity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class NavimowButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[NavimowI210Coordinator], Coroutine[Any, Any, None]]


async def _start(coord: NavimowI210Coordinator) -> None:
    await coord._ensure_valid_token()
    await coord.api.async_send_command(coord.device.id, MowerCommand.START)
    await coord.async_request_refresh()


async def _pause(coord: NavimowI210Coordinator) -> None:
    await coord._ensure_valid_token()
    await coord.api.async_send_command(coord.device.id, MowerCommand.PAUSE)
    await coord.async_request_refresh()


async def _dock(coord: NavimowI210Coordinator) -> None:
    await coord._ensure_valid_token()
    await coord.api.async_send_command(coord.device.id, MowerCommand.DOCK)
    await coord.async_request_refresh()


async def _resume(coord: NavimowI210Coordinator) -> None:
    await coord._ensure_valid_token()
    await coord.api.async_send_command(coord.device.id, MowerCommand.RESUME)
    await coord.async_request_refresh()


async def _reset_blade(coord: NavimowI210Coordinator) -> None:
    await coord._ensure_valid_token()
    await coord.api._async_request(
        "POST",
        "/openapi/smarthome/sendCommands",
        data={
            "commands": [{
                "devices": [{"id": coord.device.id}],
                "execution": {"command": "action.devices.commands.ResetBladeCounter"},
            }]
        },
    )
    await coord.async_request_refresh()


BUTTONS: tuple[NavimowButtonDescription, ...] = (
    NavimowButtonDescription(
        key="start_mowing",
        name="Start Mowing",
        icon="mdi:play",
        press_fn=_start,
    ),
    NavimowButtonDescription(
        key="pause_mowing",
        name="Pause",
        icon="mdi:pause",
        press_fn=_pause,
    ),
    NavimowButtonDescription(
        key="dock",
        name="Return to Dock",
        icon="mdi:home-import-outline",
        press_fn=_dock,
    ),
    NavimowButtonDescription(
        key="resume_mowing",
        name="Resume",
        icon="mdi:play-circle",
        press_fn=_resume,
    ),
    NavimowButtonDescription(
        key="reset_blade_counter",
        name="Reset Blade Counter",
        icon="mdi:counter",
        entity_category=EntityCategory.CONFIG,
        press_fn=_reset_blade,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        NavimowI210ButtonEntity(coord, desc)
        for coord in data["coordinators"].values()
        for desc in BUTTONS
    )


class NavimowI210ButtonEntity(NavimowI210Entity, ButtonEntity):
    entity_description: NavimowButtonDescription

    async def async_press(self) -> None:
        try:
            await self.entity_description.press_fn(self.coordinator)
        except MowerAPIError as err:
            raise HomeAssistantError(
                f"Button {self.entity_description.key} failed: {err}"
            ) from err
