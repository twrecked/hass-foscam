"""An implementation of a camera state and media updater using pyfoscam."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import LOGGER

if TYPE_CHECKING:
    from foscam import FoscamCamera

RECORDINGS_TIMEOUT = 60
RECENT_TIMEOUT = 30


class Updater(DataUpdateCoordinator):
    """Camera state and recordings updater."""

    def __init__(self, hass, camera: FoscamCamera, polling_interval: int = 5) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name="FoscamUpdater",
            update_interval=timedelta(seconds=polling_interval),
        )

        self._camera = camera
        self._media = camera.media

        # Runtime state
        self._state = "unknown"
        self._last_update = 0.0
        self._last_recordings_check = 0.0
        self._last_activity = 0.0
        self._dev_state: dict[str, Any] = {}

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

    def update_data(self) -> dict[str, Any]:
        """Fetch camera status and sync recordings (runs in executor thread)."""
        now = time.monotonic()
        was_recording = self._dev_state.get("is_recording", False)

        # 1. Query live device telemetry
        try:
            self._dev_state = self._camera.get_state()
        except Exception as err:
            LOGGER.warning("Failed fetching camera state from %s: %s", self._camera.host, err)

        self._update_state()

        # If recording just finished, force immediate media refresh
        if was_recording and not self._dev_state.get("is_recording", False):
            LOGGER.debug("Recording stopped, forcing media refresh")
            self._last_recordings_check = 0.0

        # 2. Refresh media catalog periodically
        if (self._last_recordings_check + RECORDINGS_TIMEOUT) < now:
            try:
                LOGGER.debug("Refreshing media library from camera")
                self._media.refresh()
            except Exception as err:
                LOGGER.warning("Failed scanning media on %s: %s", self._camera.host, err)
            self._last_recordings_check = now

        # 3. Fetch one pending clip per cycle after initial startup
        if self._last_update != 0.0:
            pending = [r for r in self._media.recordings if not r.is_downloaded]
            if pending:
                target = pending[0]
                try:
                    LOGGER.debug("Downloading recording: %s", target.clip_id)
                    self._media.download_recording(target)
                except Exception as err:
                    LOGGER.warning("Failed downloading recording %s: %s", target.clip_id, err)

        self._last_update = now

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
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Execute update_data in HA executor."""
        return await self.hass.async_add_executor_job(self.update_data)
