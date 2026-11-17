# hass-foscam

Custom integration for Foscam IP cameras in [Home Assistant](https://www.home-assistant.io/), providing camera streaming, motion/sound sensors, PTZ controls, saved recording library access with seeking, and automated retention management.

## Features
- **Native Async Architecture**: Non-blocking I/O using the modern `pyfoscam` async library.
- **PTZ Controls**: Pan, tilt, diagonal movements, and preset points (`foscam.ptz` and `foscam.ptz_preset` services).
- **Video Library & Range Request Streaming**: Browse SD card recordings on the camera and stream with HTTP 206 partial content support for smooth scrubbing/seeking.
- **Sensors**: Motion detection, audio detection, and I/O alarm binary sensors, plus daily and total capture count sensors.
- **Automated Retention**: Daily background pruning of expired local recording downloads (`foscam.prune_recordings`).
- **Persistent Caching**: Fast media catalog discovery with incremental scanning.

---

## Installation

### Method 1: Via HACS (Custom Repository) — Recommended
1. Open **HACS** in your Home Assistant sidebar.
2. Click the **three dots** in the top-right corner and select **Custom repositories**.
3. In the dialog:
   - **Repository**: `https://github.com/twrecked/hass-foscam`
   - **Type**: `Integration`
4. Click **Add**.
5. Find **Foscam Camera Support** in HACS and click **Download**.
6. Restart Home Assistant.

### Method 2: Manual Installation
1. Run the installation script pointing to your Home Assistant configuration directory:
   ```bash
   ./scripts/install go /path/to/homeassistant/config
   ```
   This copies `custom_components/foscam` into `<config>/custom_components/foscam`.
2. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, navigate to **Settings** -> **Devices & Services**.
2. Click **Add Integration** and search for **Foscam**.
3. Enter your camera IP address, port (default 88), username, password, and RTSP port (default 554).
