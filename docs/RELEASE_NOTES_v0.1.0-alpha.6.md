# hass-foscam v0.1.0-alpha.6 — More reliable recording downloads

This release uses [pyfoscam v0.1.0-alpha.4](https://github.com/twrecked/pyfoscam/releases/tag/v0.1.0-alpha.4).

- Wait for the camera's recording size to settle, then verify the FTP transfer before converting the clip.
- Validate that an MP4 contains video before caching it. Earlier header-only copies can be retried if the original is still on the camera.
- Clean up temporary recording directories off the event loop to avoid Home Assistant's blocking `scandir()` warning.

MP4 conversion uses `ffmpeg` and requires `ffprobe` to validate the output.
