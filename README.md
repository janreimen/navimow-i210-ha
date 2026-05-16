# Segway Navimow i210 – Home Assistant Integration

**Domain:** `navimow_i210` ← Runs 100% independently of other Navimow integrations.

A complete, MQTT-first integration for the **Segway Navimow i210** (and compatible models) with full sensor coverage, adaptive polling, and real-time location tracking via cloud MQTT push.

## Features

### Core
- ✅ **MQTT-first architecture** – Real-time state updates via navimow-sdk
- ✅ **HTTP fallback** – Auto-switches to polling if MQTT stale (>120 seconds)
- ✅ **Adaptive polling** – 10s (mowing) / 30s (default) / 60s (idle)
- ✅ **OAuth2 authentication** – Secure cloud integration
- ✅ **Multi-device support** – One integration, unlimited mowers

### Sensors (45+)
- **Battery:** Level, voltage
- **Status:** State, work mode, task state, progress, area mowed, time mowed
- **GPS:** Latitude, longitude, altitude, speed, HDOP, satellite count
- **VisionFence locals:** postureX/Y/Theta (metres from map origin, via MQTT)
- **Connectivity:** Network type, signal strength, WiFi SSID, cloud connection
- **Maintenance:** Blade usage hours, remaining life %, status
- **Schedule:** Next start/end times
- **Firmware:** Installed version, component versions, update available
- **History:** Last mowing date + 7-day history

### Controls
- **Lawn Mower entity** – Start / Pause / Dock / Resume
- **Switches** – Schedule, rain sensor, edge mowing, mowing cycle, anti-theft, dark mode, anti-interference
- **Select** – Work mode (Standard / Fast / Silent)
- **Number** – Cutting height (20–60 mm, 5 mm steps)
- **Buttons** – Start, pause, dock, resume, reset blade counter
- **Device Tracker** – GPS position on HA map, heading as attribute

### Events
- `navimow_i210_error` – New error detected (code, title, content, severity)
- `navimow_i210_alert` – Critical alerts (lifted/stuck)
- `navimow_i210_mowing_complete` – Session finished (area, time)
- `navimow_i210_maintenance` – Maintenance needed (status, blade %)

## Installation

### HACS (Recommended)
1. Open **HACS → Integrations**
2. Click **⋮** → **Custom repositories**
3. Add: `https://github.com/YOUR_USERNAME/navimow-i210-ha` as Category **Integration**
4. Click **Install Segway Navimow i210**
5. Restart Home Assistant

### Manual
1. Download latest release
2. Extract to `config/custom_components/navimow_i210/`
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Integrations**
5. Click **Create integration** → search "Navimow i210"

## Configuration

1. **Create integration** via UI → redirects to Segway login
2. **Authorize** with your Navimow account
3. Integration discovers all paired devices automatically
4. All entities appear under your device

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Home Assistant                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │          navimow_i210 Integration                      │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │  OAuth2 Session (token refresh)                 │  │ │
│  │  │  ↓                                               │  │ │
│  │  │  NavimowSDK (MQTT cloud-push)                   │  │ │
│  │  │  ├─ on_state()      → battery, state, signal    │  │ │
│  │  │  ├─ on_attributes() → extra cloud fields        │  │ │
│  │  │  └─ /realtimeDate/location → postureX/Y/Theta  │  │ │
│  │  │  ↓                                               │  │ │
│  │  │  NavimowI210Coordinator (MQTT-first, HTTP-FB)   │  │ │
│  │  │  └─ Updates every 10/30/60s or on MQTT push     │  │ │
│  │  │                                                  │  │ │
│  │  │  MowerAPI.async_get_device_status() (fallback)  │  │ │
│  │  │  └─ Full telemetry if MQTT >120s stale         │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  │                                                         │ │
│  │  Platforms: sensor, binary_sensor, switch, select,     │ │
│  │             number, button, device_tracker, update,    │ │
│  │             lawn_mower                                │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         ↓
    Segway Cloud API
         ↓
    NavimowSDK MQTT broker (mqtt.navimow.com:443 wss)
         ↓
    Segway Navimow i210 (on your lawn)
```

## API Keys & Credentials

The integration uses the **same OAuth2 credentials** as all official Navimow integrations:
- **Client ID:** `homeassistant`
- **Client Secret:** (built-in)
- **Endpoints:** Cloud OAuth + MQTT broker auto-discovery

No manual API key configuration needed – just log in via the integration UI.

## MQTT Topics

Subscribed automatically:
- `/downlink/vehicle/{device_id}/realtimeDate/state`
- `/downlink/vehicle/{device_id}/realtimeDate/event`
- `/downlink/vehicle/{device_id}/realtimeDate/attributes`
- `/downlink/vehicle/{device_id}/realtimeDate/location`  ← VisionFence locals

## Troubleshooting

### No entities appear
- ✅ Check integration is installed and enabled
- ✅ Ensure Navimow account has paired devices
- ✅ Restart Home Assistant if just installed

### GPS is 0,0 / outdated
- ✅ Check mower has outdoor GPS signal
- ✅ Verify MQTT connection (cloud icon in integration)
- ✅ Check HA home location is set (Settings → System → Home location)
- ✅ HTTP fallback kicks in after 120s without MQTT

### Slow response times
- ✅ By design: MQTT updates come 1–2s after cloud push
- ✅ Polling only resumes if MQTT stale (>120s)
- ✅ Commands always wake device via HTTP regardless

## Parallel Integrations

This integration **does NOT conflict** with:
- `navimow` (official NavimowHA from Segway)
- `navimow_custom` (andershagenhansen/navimow-ha-custom)

All use the same cloud OAuth credentials but operate in separate domains. Only one should be active at a time for the same device to avoid duplicate entities.

## Development

**Ports from:**
- **andershagenhansen/navimow-ha-custom** – MQTT architecture, OAuth2 flow, local coordinate conversion
- **TMA84/Navimow-HA-Integration** – Full sensor/binary_sensor/switch/select/number/button/update platforms, adaptive polling, error code maps, HA events
- **segwaynavimow/NavimowHA** – MowerAPI integration, command format

**Architecture decisions:**
- `navimow_i210` domain ensures no conflicts
- MQTT-first with HTTP fallback (best of both integrations)
- Unified dataclasses (I210Snapshot) for all platforms
- One NavimowI210Coordinator per device
- SDK DeviceStateMessage parsed directly (minimal overhead)

## License

Apache 2.0 – See LICENSE file

## Support

- **Issues:** [GitHub Issues](https://github.com/YOUR_USERNAME/navimow-i210-ha/issues)
- **Discussions:** [GitHub Discussions](https://github.com/YOUR_USERNAME/navimow-i210-ha/discussions)
- **Original integration:** https://github.com/andershagenhansen/navimow-ha-custom

---

**Happy mowing! 🌱**
