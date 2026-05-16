"""Services for the Navimow i210 integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from mower_sdk.api import MowerAPI
from mower_sdk.errors import MowerAPIError

from .const import DOMAIN
from .coordinator import NavimowI210Coordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_CANCEL_SCHEDULE = "cancel_schedule"
SERVICE_SCHEMA_CANCEL = vol.Schema(
    {vol.Required("device_id"): cv.string}
)


def async_setup_services(
    hass: HomeAssistant,
    api: MowerAPI,
    coordinators: dict[str, NavimowI210Coordinator],
) -> None:
    """Register services for Navimow i210."""

    async def _handle_cancel_schedule(call: ServiceCall) -> None:
        device_id = call.data["device_id"]
        coord = coordinators.get(device_id)
        if not coord:
            raise HomeAssistantError(f"Device {device_id} not found")
        try:
            await api._async_request(
                "POST",
                "/openapi/smarthome/sendCommands",
                data={
                    "commands": [{
                        "devices": [{"id": device_id}],
                        "execution": {"command": "action.devices.commands.CancelSchedule"},
                    }]
                },
            )
            await coord.async_request_refresh()
            _LOGGER.info("Schedule cancelled for device %s", device_id)
        except MowerAPIError as err:
            raise HomeAssistantError(f"Failed to cancel schedule: {err}") from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_SCHEDULE,
        _handle_cancel_schedule,
        schema=SERVICE_SCHEMA_CANCEL,
    )
