# 🚀 hass-foscam v0.1.0-alpha.4 — Media Storage and Recording Retention

## Per-camera media folders

New downloads go to `/media/foscam/<camera-name>` by default. If Home Assistant
has a different local media directory configured, the integration uses that
directory instead of `/media`. Camera names are normalized for folder names:
for example, `Back Garden` becomes `back_garden`.

Existing downloads in `/config/foscam` are not moved automatically. If you want
to keep them in the new location, move them into the corresponding camera folder.
Use camera names that normalize to distinct folder names so one camera’s cleanup
doesn’t affect another camera’s recordings.

## Configurable recording retention

Set **Recording retention (days)** in the camera entry’s options under
**Settings → Devices & Services → Foscam**. The setting accepts 1–365 days and
defaults to 30. It sets both how far back the integration looks for recordings
to download and the age limit for daily cleanup of local copies. Cleanup does
not delete recordings from the camera’s SD card.

The dependency remains pinned to `pyfoscam v0.1.0-alpha.2`.
