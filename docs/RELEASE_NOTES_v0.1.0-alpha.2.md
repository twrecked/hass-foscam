# 🚀 hass-foscam v0.1.0-alpha.2 — Sensor Icon Fix & Metadata Attributes

> ### ⚠️ Alpha Release Notice
> This pre-release fixes the last capture sensor icon display and enriches the sensor attributes.
>
> If you encounter any issues, please report them on [GitHub Issues](https://github.com/twrecked/hass-foscam/issues).

---

## 🌟 Highlights

### 1. Corrected Last Capture Sensor Icon
- Fixed a typo where `"mdi:fast-run"` was specified instead of the valid Material Design Icon **`"mdi:run-fast"`**, which previously caused Home Assistant to render a blank space for the sensor icon.

### 2. Dynamic Trigger Icons
- Added dynamic icon resolution based on the trigger of the most recent recording:
  - **Motion:** `mdi:run-fast`
  - **Alarm / IO:** `mdi:bell-ring`
  - **Schedule:** `mdi:calendar-clock`
  - **Default:** `mdi:run-fast`

### 3. Rich Metadata Attributes
- The `sensor.<camera>_last_capture` entity now exposes metadata attributes for the latest recorded clip:
  - `clip_id`: unique recording identifier
  - `trigger`: trigger cause (`motion`, `schedule`, `alarm`, etc.)
  - `duration`: duration of the clip in seconds
  - `video_url`: local MP4 video file path
  - `thumbnail_url`: local JPEG thumbnail path
