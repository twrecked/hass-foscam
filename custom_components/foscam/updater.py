"""An implementation of a camera state and media updater using pyfoscam."""
from __future__ import annotations

import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from foscam.exceptions import FoscamError

from .const import LOGGER

if TYPE_CHECKING:
    from foscam import FoscamCamera

RECORDINGS_TIMEOUT = 60
CONTROLS_TIMEOUT = 60
RECENT_TIMEOUT = 30
PRUNE_INTERVAL = 86400  # Prune expired local downloads once per day


class Updater(DataUpdateCoordinator[dict[str, Any]]):
    """Camera state and recordings updater."""

    def __init__(
        self,
        hass: HomeAssistant,
        camera: FoscamCamera,
        polling_interval: int = 5,
        retention_days: int = 30,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name="FoscamUpdater",
            update_interval=timedelta(seconds=polling_interval),
        )

        self._camera = camera
        self._media = camera.media
        self.retention_days = retention_days

        # Runtime state
        self._state = "unknown"
        self._last_update = 0.0
        self._last_recordings_check = 0.0
        self._last_controls_check = 0.0
        self._last_prune = 0.0
        self._last_activity = 0.0
        self._dev_state: dict[str, Any] = {}
        self._presets: list[str] = []
        self._capabilities: dict[str, bool] = {}
        self._controls: dict[str, Any] = {}

    def has_capability(self, name: str) -> bool:
        """Return True if camera supports the specified feature."""
        return self._capabilities.get(name, False)

    def _update_state(self) -> None:
        """Calculate state machine transitions."""
        is_rec = self._dev_state.get("is_recording", False)
        is_motion = self._dev_state.get("motion_detected", False)

        if is_rec:
            state = "recording"
        elif is_motion:
            state = "motion"
        elif self._state != "idle":
            now = time.monotonic()
            if self._state != "recently active":
                state = "recently active"
                self._last_activity = now
            elif (self._last_activity + RECENT_TIMEOUT) > now:
                state = "recently active"
            else:
                self._last_activity = 0.0
                state = "idle"
        else:
            state = "idle"

        self._state = state

    async def _async_probe_capabilities(self) -> None:
        """Detect supported camera hardware capabilities on startup."""
        # 1. Sleep / privacy
        try:
            val = await self._camera.is_asleep()
            self._capabilities["sleep"] = True
            self._controls["sleep"] = val
        except (FoscamError, TimeoutError, OSError):
            self._capabilities["sleep"] = False

        # 2. Status LED
        try:
            val = await self._camera.get_led_state()
            self._capabilities["led"] = True
            self._controls["led"] = val
        except (FoscamError, TimeoutError, OSError):
            self._capabilities["led"] = False

        # 3. Flip & Mirror
        try:
            mf = await self._camera.get_flip_and_mirror()
            self._capabilities["flip"] = True
            self._capabilities["mirror"] = True
            self._controls["flip"] = mf.get("is_flip", False)
            self._controls["mirror"] = mf.get("is_mirror", False)
        except (FoscamError, TimeoutError, OSError):
            self._capabilities["flip"] = False
            self._capabilities["mirror"] = False

        # 4. Night Vision Infrared
        try:
            ir = await self._camera.get_infra_led_config()
            self._capabilities["ir"] = True
            self._controls["ir_auto"] = ir.get("auto", True)
        except (FoscamError, TimeoutError, OSError):
            self._capabilities["ir"] = False

        # 5. Volume & Mute
        try:
            vol = await self._camera.get_volume()
            self._capabilities["volume"] = True
            self._controls["volume"] = vol
        except (FoscamError, TimeoutError, OSError):
            self._capabilities["volume"] = False

        try:
            voice = await self._camera.get_voice_state()
            self._capabilities["mute"] = True
            self._controls["mute"] = not voice
        except (FoscamError, TimeoutError, OSError):
            self._capabilities["mute"] = False

        # 6. White light (model-dependent)
        try:
            wl = await self._camera.get_white_light_brightness()
            self._capabilities["white_light"] = True
            self._controls["white_light"] = wl.get("enable") == "1"
        except (FoscamError, TimeoutError, OSError):
            self._capabilities["white_light"] = False

        # 7. Siren (model-dependent)
        try:
            siren = await self._camera.get_siren_config()
            self._capabilities["siren"] = True
            self._controls["siren"] = siren.get("sirenEnable") == "1"
        except (FoscamError, TimeoutError, OSError):
            self._capabilities["siren"] = False

        LOGGER.debug(
            "Camera %s capabilities detected: %s",
            self._camera.host,
            [k for k, v in self._capabilities.items() if v],
        )

    async def _async_refresh_controls(self) -> None:
        """Periodically refresh states of supported hardware controls."""
        if self._capabilities.get("sleep"):
            try:
                self._controls["sleep"] = await self._camera.is_asleep()
            except (FoscamError, TimeoutError, OSError) as err:
                LOGGER.debug("Failed refreshing sleep state: %s", err)

        if self._capabilities.get("led"):
            try:
                self._controls["led"] = await self._camera.get_led_state()
            except (FoscamError, TimeoutError, OSError) as err:
                LOGGER.debug("Failed refreshing LED state: %s", err)

        if self._capabilities.get("flip") or self._capabilities.get("mirror"):
            try:
                mf = await self._camera.get_flip_and_mirror()
                self._controls["flip"] = mf.get("is_flip", False)
                self._controls["mirror"] = mf.get("is_mirror", False)
            except (FoscamError, TimeoutError, OSError) as err:
                LOGGER.debug("Failed refreshing flip/mirror: %s", err)

        if self._capabilities.get("ir"):
            try:
                ir = await self._camera.get_infra_led_config()
                self._controls["ir_auto"] = ir.get("auto", True)
            except (FoscamError, TimeoutError, OSError) as err:
                LOGGER.debug("Failed refreshing IR config: %s", err)

        if self._capabilities.get("volume"):
            try:
                self._controls["volume"] = await self._camera.get_volume()
            except (FoscamError, TimeoutError, OSError) as err:
                LOGGER.debug("Failed refreshing volume: %s", err)

        if self._capabilities.get("mute"):
            try:
                voice = await self._camera.get_voice_state()
                self._controls["mute"] = not voice
            except (FoscamError, TimeoutError, OSError) as err:
                LOGGER.debug("Failed refreshing voice state: %s", err)

        if self._capabilities.get("white_light"):
            try:
                wl = await self._camera.get_white_light_brightness()
                self._controls["white_light"] = wl.get("enable") == "1"
            except (FoscamError, TimeoutError, OSError) as err:
                LOGGER.debug("Failed refreshing white light: %s", err)

        if self._capabilities.get("siren"):
            try:
                siren = await self._camera.get_siren_config()
                self._controls["siren"] = siren.get("sirenEnable") == "1"
            except (FoscamError, TimeoutError, OSError) as err:
                LOGGER.debug("Failed refreshing siren: %s", err)

    def _build_data_dict(self) -> dict[str, Any]:
        """Construct full coordinator data dictionary."""
        last_dt = self._media.last_capture_at
        last_str = last_dt.strftime("%Y-%m-%dT%H:%M:%S") if last_dt else None

        return {
            "motion_status": self._dev_state.get("motion_enabled", False),
            "motion": self._dev_state.get("motion_detected", False),
            "sound_status": self._dev_state.get("sound_enabled", False),
            "sound": self._dev_state.get("sound_detected", False),
            "io_status": self._dev_state.get("io_enabled", False),
            "io": self._dev_state.get("io_detected", False),
            "recording": self._dev_state.get("is_recording", False),
            "recordings": self._media.recordings,
            "last": last_str,
            "captured_today": self._media.captured_today,
            "captured_total": self._media.captured_total,
            "state": self._state,
            "preset_list": self._presets,
            **self._controls,
        }

    async def async_set_sleep(self, enable: bool) -> None:
        """Toggle sleep / privacy mode."""
        if enable:
            await self._camera.sleep()
        else:
            await self._camera.wake_up()
        self._controls["sleep"] = enable
        self.async_set_updated_data(self._build_data_dict())

    async def async_set_led(self, enable: bool) -> None:
        """Toggle physical status LED."""
        await self._camera.set_led_state(enable)
        self._controls["led"] = enable
        self.async_set_updated_data(self._build_data_dict())

    async def async_set_flip(self, enable: bool) -> None:
        """Toggle vertical flip."""
        await self._camera.set_flip(enable)
        self._controls["flip"] = enable
        self.async_set_updated_data(self._build_data_dict())

    async def async_set_mirror(self, enable: bool) -> None:
        """Toggle horizontal mirror."""
        await self._camera.set_mirror(enable)
        self._controls["mirror"] = enable
        self.async_set_updated_data(self._build_data_dict())

    async def async_set_ir(self, enable: bool) -> None:
        """Toggle night vision infrared mode (Auto when True, Off when False)."""
        await self._camera.set_infra_led("auto" if enable else "off")
        self._controls["ir_auto"] = enable
        self.async_set_updated_data(self._build_data_dict())

    async def async_set_volume(self, volume: int) -> None:
        """Set speaker volume (0-100)."""
        await self._camera.set_volume(volume)
        self._controls["volume"] = volume
        self.async_set_updated_data(self._build_data_dict())

    async def async_set_mute(self, mute: bool) -> None:
        """Toggle audio mute."""
        await self._camera.set_voice_state(not mute)
        self._controls["mute"] = mute
        self.async_set_updated_data(self._build_data_dict())

    async def async_set_white_light(self, enable: bool) -> None:
        """Toggle white light / spotlight."""
        if enable:
            await self._camera.open_white_light()
        else:
            await self._camera.close_white_light()
        self._controls["white_light"] = enable
        self.async_set_updated_data(self._build_data_dict())

    async def async_set_siren(self, enable: bool) -> None:
        """Toggle siren alarm."""
        await self._camera.set_siren_config(enable)
        self._controls["siren"] = enable
        self.async_set_updated_data(self._build_data_dict())

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch camera status and sync recordings asynchronously."""
        now = time.monotonic()
        was_recording = self._dev_state.get("is_recording", False)

        # 1. Query live device telemetry
        try:
            self._dev_state = await self._camera.get_state()
            if not self._presets or self._last_update == 0.0:
                self._presets = await self._camera.get_ptz_presets()
        except (FoscamError, TimeoutError, OSError) as err:
            LOGGER.warning("Failed fetching camera state from %s: %s", self._camera.host, err)

        # 2. Probe or refresh control states
        if not self._capabilities:
            await self._async_probe_capabilities()
            self._last_controls_check = now
        elif (self._last_controls_check + CONTROLS_TIMEOUT) < now:
            await self._async_refresh_controls()
            self._last_controls_check = now

        self._update_state()

        # If recording just finished, force immediate media refresh
        if was_recording and not self._dev_state.get("is_recording", False):
            LOGGER.debug("Recording stopped, forcing media refresh")
            self._last_recordings_check = 0.0

        # 3. Refresh media catalog periodically (using persistent caching)
        if (self._last_recordings_check + RECORDINGS_TIMEOUT) < now:
            try:
                LOGGER.debug("Refreshing media library from camera")
                await self._media.refresh()
            except (FoscamError, TimeoutError, OSError) as err:
                LOGGER.warning("Failed scanning media on %s: %s", self._camera.host, err)
            self._last_recordings_check = now

        # 4. Fetch one pending clip per cycle after initial startup
        if self._last_update != 0.0:
            pending = [r for r in self._media.recordings if not r.is_downloaded]
            if pending:
                target = pending[0]
                try:
                    LOGGER.debug("Downloading recording: %s", target.clip_id)
                    await self._media.download_recording(target)
                except (FoscamError, TimeoutError, OSError) as err:
                    LOGGER.warning("Failed downloading recording %s: %s", target.clip_id, err)

        # 5. Prune expired local downloads daily
        if self._last_update != 0.0 and (self._last_prune + PRUNE_INTERVAL) < now:
            try:
                deleted, freed = await self._media.prune_local(days=self.retention_days)
                if deleted > 0:
                    LOGGER.info(
                        "Pruned %d expired local recordings (%d bytes freed) from %s",
                        deleted,
                        freed,
                        self._media.storage_dir,
                    )
            except (FoscamError, OSError) as err:
                LOGGER.debug("Local recordings prune failed on %s: %s", self._camera.host, err)
            self._last_prune = now

        self._last_update = now
        return self._build_data_dict()
