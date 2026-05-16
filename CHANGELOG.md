# Changelog

All notable changes to the Navimow i210 Home Assistant integration will be documented in this file.

## [2.0.0] – 2024-01-XX (Initial Release)

### Added
- **MQTT-first architecture** – Real-time updates via navimow-sdk cloud MQTT push
- **HTTP fallback** – Automatic switch to polling after 120 seconds without MQTT
- **Adaptive polling** – Smart intervals: 10s (mowing), 30s (default), 60s (idle)
- **45+ sensors** – Battery, GPS, state, settings, maintenance, schedule, firmware, history
- **Binary sensors** – Charging, errors, GPS validity, MQTT connection, blade replacement
- **Controls** – Lawn mower entity (start/pause/dock/resume), switches, selectors, numbers, buttons
- **Device Tracker** – GPS position on HA map with heading and local coordinates
- **Update entity** – Firmware update availability with release notes
- **Events** – `navimow_i210_error`, `_alert`, `_mowing_complete`, `_maintenance`
- **OAuth2 integration** – Secure cloud authentication with automatic token refresh
- **Multi-device support** – One integration handles unlimited paired mowers
- **Local coordinate conversion** – VisionFence postureX/Y/Theta → GPS (via HA home origin)
- **Error code mapping** – 40+ error codes with human-readable descriptions
- **Services** – `cancel_schedule` service for controlling automations

### Technical
- Ported MQTT architecture from andershagenhansen/navimow-ha-custom
- Ported full sensor/control coverage from TMA84/Navimow-HA-Integration
- Integrated MowerAPI from segwaynavimow/NavimowHA for HTTP fallback
- Unified dataclass architecture (I210Snapshot) for all platforms
- Exponential backoff for failed HTTP requests (up to 5 minutes)
- Per-device coordinator with independent state management

### Compatibility
- Runs independently: domain `navimow_i210` (no conflicts with `navimow` or `navimow_custom`)
- Requires: navimow-sdk >= 0.1.2
- Tested on: Home Assistant 2024.1+
- Models: Segway Navimow i105, i108, i210

## [1.0.0] – Unreleased
(This release started as a fork combining andershagenhansen + TMA84 integrations)
