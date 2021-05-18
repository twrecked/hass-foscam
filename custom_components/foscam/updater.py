import time
import os
import threading
from datetime import datetime

from ftpretty import ftpretty

from .const import (
    LOGGER
)

CACHE_CHECK = 2
RECORDINGS_TIMEOUT = 60


class Updater:
    """An implementation of a camera state updater."""

    def __init__(self, hass, camera):
        self._hass = hass
        self._camera = camera
        self._last = 0
        self._state = {}
        self._recordings = {}
        self._todays_count = 0
        self._last_capture_at = None
        self._lock = threading.Lock()

    def get_datetime(self, filename):
        filename = os.path.splitext(filename)[0]
        filename = filename.split("_", 1)[1]
        if "-" in filename:
            return datetime.strptime(filename, "%Y%m%d-%H%M%S")
        else:
            return datetime.strptime(filename, "%Y%m%d_%H%M%S")

    def update_state(self):
        ret, self._state = self._camera.get_dev_state()
        return ret

    def update_recordings(self):
        res, devinfo = self._camera.get_dev_info()
        if res is not 0:
            LOGGER.error("failed to read device info")
            return -1
        mac = devinfo.get("mac", None)
        if mac is None:
            LOGGER.error("failed to read device mac")
            return -1

        self._camera.execute_command('startFtpServer')
        ftp = ftpretty(self._camera.host, self._camera.usr, self._camera.pwd, port=50021)

        self._todays_count = 0
        self._last_capture_at = None

        today = datetime.now().strftime("%Y%m%d")

        recordings = []
        for possible_dir in ftp.list("/IPCamera"):
            if mac in possible_dir:
                for date in ftp.list(f"/IPCamera/{possible_dir}/record"):
                    for date2 in ftp.list(f"/IPCamera/{possible_dir}/record/{date}"):
                        for recording in ftp.list(f"/IPCamera/{possible_dir}/record/{date}/{date2}"):
                            if not recording.endswith("avi"):
                                continue

                            recording_date = self.get_datetime(recording)
                            if recording_date.strftime("%Y%m%d") == today:
                                self._todays_count += 1
                            if self._last_capture_at is None or self._last_capture_at < recording_date:
                                self._last_capture_at = recording_date

                            recordings.append({
                                "type": "avi",
                                "date": recording_date,
                                "base": os.path.splitext(recording)[0],
                                "path": f"/IPCamera/{possible_dir}/record/{date}/{date2}/{recording}",
                                "url": f"ftp://{self._camera.usr}:{self._camera.pwd}@{self._camera.host}:50021"
                                        f"/IPCamera/{possible_dir}/record/{date}/{date2}/{recording}"
                            })

        self._recordings = sorted(recordings, key=lambda x: x["base"])
        return 0

    def update_data(self):
        """Fetch data from camera endpoint
        """
        with self._lock:
            now = time.monotonic()
            if self._last + CACHE_CHECK > now:
                LOGGER.debug("using cache")
                return

            LOGGER.debug("update state")
            self.update_state()

            if (self._last + RECORDINGS_TIMEOUT) < now:
                LOGGER.debug("update recordings")
                self.update_recordings()

            self._last = now

    async def async_update_data(self):
        await self._hass.async_add_executor_job(
            self.update_data
        )
        data = {
            "motion_status": self._state["motionDetectAlarm"] != "0",
            "motion_detected": self._state["motionDetectAlarm"] == "2",
            "sound_status": self._state["soundAlarm"] == "0",
            "sound_detected": self._state["soundAlarm"] == "2",
            "io_status": self._state["IOAlarm"] == "0",
            "io_detected": self._state["IOAlarm"] == "2",

            "recordings": self._recordings,
            "last_capture": self._last_capture_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "captured_today": self._todays_count,
            "captured_total": len(self._recordings)
        }
        return data