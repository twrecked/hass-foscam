# 🚀 hass-foscam v0.1.0-alpha.1 — Asynchronous Home Assistant Integration for Foscam IP Cameras

> ### ⚠️ Alpha Release & Community Testing Notice
> **hass-foscam is an async-first Home Assistant custom integration for Foscam IP cameras.**
>
> This release modernizes the integration to current Home Assistant architectural standards (HA 2024+/2026+), consumes the `pyfoscam` async library directly on the event loop, introduces full Home Assistant Device support, and provides saved SD-card clip streaming with seeking.
>
> If you encounter any bugs or display anomalies, please report them on [GitHub Issues](https://github.com/twrecked/hass-foscam/issues).

---

## 🌟 Highlights

### 1. Fully Asynchronous Coordinator & Entities
- **Zero Executor Hops:** Background telemetry polling (every 5s) and media discovery (every 60s) directly await `pyfoscam` coroutines natively on the event loop without `hass.async_add_executor_job()`.
- **Instant Snapshots & Streaming:** Live RTSP stream URL generation and still snapshot captures run asynchronously without blocking.

### 2. First-Class Home Assistant Device Registry
- **Full `DeviceInfo` Support:** Automatically registers a Home Assistant Device for your camera populated with real hardware telemetry:
  - **Manufacturer:** Foscam
  - **Model:** Auto-discovered from camera firmware (e.g. `FI9928P+V2`, `R2`, `G4P`, `FI9821W`)
  - **Firmware Version:** Auto-discovered
  - **Hardware Version:** Auto-discovered
  - **Configuration URL:** Direct link to the camera's local web portal (`http://<ip>:<port>`)
- **Modern Entity Naming (`_attr_has_entity_name = True`):** Child entities inherit the device name cleanly without redundant prefixes:
  - `camera.<name>`
  - `binary_sensor.<name>_motion`
  - `binary_sensor.<name>_sound`
  - `binary_sensor.<name>_io_alarm`
  - `sensor.<name>_captured_today`
  - `sensor.<name>_total_captures`
  - `sensor.<name>_last_capture`

### 3. Video Recording Library with Range-Request Seeking
- **HTTP 206 Partial Content Streaming:** Media endpoints (`/api/foscam_recording/{entity_id}`) use `aiohttp.web.FileResponse`, allowing video players in browsers and mobile apps to seek and scrub seamlessly without buffering entire files in memory.
- **WebSocket Catalog Command:** Custom `foscam_library` WebSocket endpoint returns structured recording metadata and thumbnails for custom frontend cards.

### 4. Automated Storage Retention
- **Daily Background Pruning:** Automatically unlinks downloaded recordings older than `retention_days` (default 30 days) to prevent local storage bloat on your Home Assistant disk.
- **Service `foscam.prune_recordings`:** Allows triggering manual or scheduled pruning automations via Home Assistant actions.

### 5. PTZ Services & Preset Discovery
- **Preset List Exposure:** Automatically fetches saved camera presets (`TopMost`, `BottomMost`, `scene01`, etc.) and exposes them in `camera.<name>`'s `preset_list` attribute.
- **Services:** `foscam.ptz` (directional movements with travel time) and `foscam.ptz_preset` (instant jump to preset point).

### 6. Config Flow Enhancements
- Visual configuration flow supports an optional **Name** field (auto-detects from the camera's internal `devName` if left blank).
- Automatic detection of camera RTSP ports.
