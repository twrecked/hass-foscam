import time
import os
import threading
from datetime import datetime

from ftpretty import ftpretty

from .const import (
    LOGGER
)
from .media import (
    Recording
)

CHECK_TIMEOUT = 2
RECORDINGS_TIMEOUT = 60
TMP_AVI = "/config/foscam/in.avi"


class Updater:
    """An implementation of a camera state updater."""

    def __init__(self, hass, camera):
        self._hass = hass
        self._camera = camera
        self._last = 0
        self._last_recording = 0
        self._todays_count = 0
        self._last_capture_at = None
        self._lock = threading.Lock()

        # start up state
        self._state = {}
        self._recordings = []

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
        url_base = f"ftp://{self._camera.usr}:{self._camera.pwd}@{self._camera.host}:50021/IPCamera"

        recordings = []
        snapshots = {}
        for possible_dir in ftp.list("/IPCamera"):
            if mac in possible_dir:

                # Save out the snapshots.
                for date1 in ftp.list(f"/IPCamera/{possible_dir}/snap"):
                    for date2 in ftp.list(f"/IPCamera/{possible_dir}/snap/{date1}"):
                        for snapshot in ftp.list(f"/IPCamera/{possible_dir}/snap/{date1}/{date2}"):
                            if not snapshot.endswith("jpg"):
                                continue

                            date = self.get_datetime(snapshot)
                            snapshots[date] = f"/IPCamera/{possible_dir}/snap/{date1}/{date2}/{snapshot}"

                # Build recordings array.
                for date1 in ftp.list(f"/IPCamera/{possible_dir}/record"):
                    for date2 in ftp.list(f"/IPCamera/{possible_dir}/record/{date1}"):
                        for recording in ftp.list(f"/IPCamera/{possible_dir}/record/{date1}/{date2}"):
                            if not recording.endswith("avi"):
                                continue

                            date = self.get_datetime(recording)

                            # update counts
                            if date.strftime("%Y%m%d") == today:
                                self._todays_count += 1
                            if self._last_capture_at is None or self._last_capture_at < date:
                                self._last_capture_at = date

                            # find a thumbnail
                            snapshot = [k for k in sorted(snapshots.keys()) if k > date]
                            if snapshot:
                                snapshot = snapshots[snapshot[0]]

                            remote_recording = f"/IPCamera/{possible_dir}/record/{date1}/{date2}/{recording}"
                            recordings.append(Recording(date, remote_recording, snapshot))

        ftp.close()

        self._recordings = sorted(recordings, key=lambda x: x.created_at, reverse=True)

        return 0

    def fetch_recordings(self):

        for recording in self._recordings:
            if not os.path.exists(recording.content_url):
                self._camera.execute_command('startFtpServer')
                ftp = ftpretty(self._camera.host, self._camera.usr, self._camera.pwd, port=50021)

                LOGGER.debug(f"copying {recording.thumbnail_url}")
                ftp.get(recording.remote_thumbnail_url, recording.thumbnail_url)

                LOGGER.debug(f"creating {recording.content_url}")
                ftp.get(recording.remote_content_url, TMP_AVI)
                os.system(f"ffmpeg -i {TMP_AVI} {recording.content_url}")
                os.unlink(TMP_AVI)

                ftp.close()
                return

    def update_data(self):
        """Fetch data from camera endpoint
        """
        with self._lock:
            now = time.monotonic()

            # too soon?
            if self._last + CHECK_TIMEOUT > now:
                LOGGER.debug(f"too soon to update {self._last} -- {now}")
                return

            # save pre-update state
            motion_detected = self._state.get("motionDetectAlarm", "0") == "2"

            LOGGER.debug("update state")
            self.update_state()

            # check post-update state
            if motion_detected and self._state.get("motionDetectAlarm", "0") != "2":
                LOGGER.debug("force recording update")
                self._last_recording = 0

            # check recordings
            if (self._last_recording + RECORDINGS_TIMEOUT) < now:
                LOGGER.debug("update recordings")
                self.update_recordings()
                self._last_recording = now

            # grab one recording per go after initial setup
            if self._last != 0:
                self.fetch_recordings()

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
