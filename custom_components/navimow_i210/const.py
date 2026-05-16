"""Constants for the Segway Navimow i210 integration (domain: navimow_i210).

Runs fully independent of:
  - segwaynavimow/NavimowHA      (domain: navimow)
  - andershagenhansen/navimow-ha-custom (domain: navimow_custom)
  - TMA84/Navimow-HA-Integration (domain: navimow)
"""
from __future__ import annotations
from typing import Final

DOMAIN: Final = "navimow_i210"

# ── OAuth2 / Cloud ────────────────────────────────────────────────────────────
OAUTH2_AUTHORIZE: Final = (
    "https://navimow-h5-fra.willand.com/smartHome/login?channel=homeassistant"
)
OAUTH2_TOKEN: Final = "https://navimow-fra.ninebot.com/openapi/oauth/getAccessToken"
CLIENT_ID:     Final = "homeassistant"
CLIENT_SECRET: Final = "57056e15-722e-42be-bbaa-b0cbfb208a52"

# ── Regional API base URLs ────────────────────────────────────────────────────
API_BASE_URL: Final = "https://navimow-fra.ninebot.com"
API_BASE_URLS: Final[dict[str, str]] = {
    "fra": "https://navimow-fra.ninebot.com",
    "ore": "https://navimow-ore.ninebot.com",
    "sg":  "https://navimow-sg.ninebot.com",
    "bj":  "https://navimow-bj.ninebot.com",
    "mos": "https://navimow-mos.ninebot.com",
}

# ── MQTT fallback ─────────────────────────────────────────────────────────────
MQTT_BROKER:   Final = "mqtt.navimow.com"
MQTT_PORT:     Final = 1883
MQTT_USERNAME: Final[str | None] = None
MQTT_PASSWORD: Final[str | None] = None

# ── Timing ────────────────────────────────────────────────────────────────────
# How long without an MQTT message before HTTP polling kicks in
MQTT_STALE_SECONDS:       Final = 120
# Minimum gap between HTTP fallback calls
HTTP_FALLBACK_MIN_INTERVAL: Final = 30

# ── Mower state → HA LawnMowerActivity mapping ───────────────────────────────
# Covers both SDK-normalised values and raw cloud-API values
MOWER_STATUS_TO_ACTIVITY: Final[dict[str, str]] = {
    # SDK canonical
    "idle":      "docked",
    "mowing":    "mowing",
    "paused":    "paused",
    "docked":    "docked",
    "charging":  "docked",
    "returning": "returning",
    "error":     "error",
    "unknown":   "error",
    # Cloud raw
    "WORK_MOWING":    "mowing",
    "WORK_RETURNING": "returning",
    "IDLE_CHARGING":  "docked",
    "IDLE_STANDBY":   "docked",
    "IDLE_PARKING":   "docked",
    "WORK_PAUSED":    "paused",
    "WORK_MAPPING":   "mowing",
    "FAULT":          "error",
}

# ── Vehicle error code dictionary (covers i105 / i108 / i210) ────────────────
VEHICLE_ERROR_CODES: Final[dict[int, str]] = {
    0:  "No error",
    1:  "Mower lifted",
    2:  "Mower stuck",
    3:  "Blade motor blocked",
    4:  "Blade motor overload",
    5:  "Left wheel motor blocked",
    6:  "Right wheel motor blocked",
    7:  "Left wheel motor overload",
    8:  "Right wheel motor overload",
    9:  "Left wheel motor stall",
    10: "Right wheel motor stall",
    11: "Boundary signal lost",
    12: "Boundary wire broken",
    13: "Charging station not found",
    14: "Charging contact error",
    15: "Charging voltage abnormal",
    16: "Charging current abnormal",
    17: "Battery critically low",
    18: "Battery temperature fault",
    19: "Battery overvoltage",
    20: "Battery undervoltage",
    21: "GPS signal lost",
    22: "GPS accuracy insufficient",
    23: "Mowing area not recognised",
    24: "Rain detected",
    25: "Slope too steep",
    26: "VisionFence signal lost",
    27: "VisionFence calibration required",
    28: "Map data corrupted",
    29: "Firmware update failed",
    30: "Communication error",
    31: "Motor controller fault",
    32: "IMU sensor fault",
    33: "Ultrasonic sensor fault",
    34: "Cliff sensor fault",
    35: "Perimeter wire break",
    36: "Obstacle at charging station",
    37: "Emergency stop triggered",
    38: "Cover open",
    39: "Battery not detected",
    40: "Software exception",
    100: "Charging station power fault",
    101: "Charging station communication error",
    102: "Charging station temperature fault",
    103: "Docking alignment error",
    104: "Charging station disconnected",
}


def get_error_message(code: int) -> str:
    """Return a human-readable error description for a given error code."""
    return VEHICLE_ERROR_CODES.get(code, f"Unknown error ({code})")


# ── HA platforms loaded by this integration ───────────────────────────────────
PLATFORMS: Final[list[str]] = [
    "binary_sensor",
    "button",
    "device_tracker",
    "lawn_mower",
    "number",
    "select",
    "sensor",
    "switch",
    "update",
]
