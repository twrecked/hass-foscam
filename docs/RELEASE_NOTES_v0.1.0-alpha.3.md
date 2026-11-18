# 🚀 hass-foscam v0.1.0-alpha.3 — Hardware Controls & Dynamic Capability Probing

> ### ⚠️ Alpha Release Notice
> This pre-release adds direct camera hardware control switches and a volume slider entity, backed by `pyfoscam v0.1.0-alpha.2`.
>
> If you encounter any issues, please report them on [GitHub Issues](https://github.com/twrecked/hass-foscam/issues).

---

## 🌟 Highlights

### 1. New Hardware Switches (`switch.py`)
Exposes native async Home Assistant switches for controlling camera settings in real time:
- **Sleep Mode (`switch.<camera>_sleep`):** Put the camera into sleep/privacy mode or wake it up.
- **Physical Status Light (`switch.<camera>_status_light`):** Enable or disable the camera's physical status LEDs.
- **Orientation Controls (`switch.<camera>_flip` & `switch.<camera>_mirror`):** Toggle vertical flip and horizontal mirror on the camera sensor.
- **Infrared Night Vision (`switch.<camera>_infrared_mode`):** Toggle IR night vision between Auto and Forced Off.
- **Volume Mute (`switch.<camera>_volume_muted`):** Mute or unmute camera speaker voice output.
- **White Light / Spotlight (`switch.<camera>_white_light`):** Toggle white spotlight (available on supported spotlight models).
- **Siren Alarm (`switch.<camera>_siren_alarm`):** Trigger or silence the built-in siren (available on supported siren models).

### 2. Speaker Volume Slider (`number.py`)
Exposes a native volume slider entity:
- **`number.<camera>_device_volume`:** Direct control of camera speaker volume (`0`–`100%`, step `1`).

### 3. Dynamic Capability Probing & Entity Hiding
- On startup, `updater.py` probes each control endpoint against the camera hardware.
- Only features confirmed supported by the device are registered as Home Assistant entities.
- Unsupported endpoints (such as spotlights or sirens on standard indoor/PTZ cameras) are automatically omitted and hidden from dashboards.

### 4. Robust Entity Registration
- Subclasses standard `SwitchEntityDescription` and `NumberEntityDescription` for compatibility with Home Assistant entity registry standards.
- Employs standard translation keys to ensure clean, human-readable entity IDs.

### 5. Dependency Update
- Pinned `pyfoscam` requirement to `v0.1.0-alpha.2`.
