import time
import os
import threading
from datetime import (
    datetime,
    timedelta
)

from ftpretty import ftpretty

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)
from .const import (
    LOGGER
)
from .media import (
    Recording
)

CHECK_TIMEOUT = 2
RECORDINGS_TIMEOUT = 60
TMP_AVI = "/config/foscam/in.avi"
CUT_OFF_SECONDS = 10
RECENT_TIMEOUT = 30


class Updater(DataUpdateCoordinator):
    """An implementation of a camera state updater."""

    def __init__( self, hass, camera, polling_interval):
        """Initialize a Foscam camera data updater."""

        super().__init__(
            hass=hass,
            logger=LOGGER,
            name="FoscamUpdater",
            update_interval=timedelta(seconds=polling_interval),
        )

        self._camera = camera

        # start up state
        self._state = "unknown"
        self._last_update = 0
        self._last_recording = 0
        self._todays_count = 0
        self._last_capture_at = None
        self._last_activity = 0.0
        self._dev_state = {}
        self._recordings = []

    def get_datetime(self, filename):
        filename = os.path.splitext(os.path.basename(filename))[0]
        filename = filename.replace("-", "_", 1).split("_", 1)[1]
        return datetime.strptime(filename, "%Y%m%d_%H%M%S")

    def update_dev_state(self):
        ret, self._dev_state = self._camera.get_dev_state()
        return ret

    def update_state(self):
        state = "idle"

        # Doing something?
        if self._dev_state.get("recording", "0") == "1":
            state = "recording"
        elif self._dev_state["motionDetectAlarm"] == "2":
            state = "motion"

        # Not doing something.But were we?
        elif self._state != "idle":
            if self._state != "recently active":
                state = "recently active"
                self._last_activity = time.monotonic()
            elif (self._last_activity + RECENT_TIMEOUT) > time.monotonic():
                state = "recently active"
            else:
                self._last_activity = 0.0

        # Set the new state
        self._state = state

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

        today = datetime.now().date()
        todays_count = 0
        last_capture_at = None

        recordings = []
        snapshots = {}
        for possible_dir in ftp.list("/IPCamera"):
            if mac in possible_dir:

                # Save out the snapshots.
                for date1 in ftp.list(f"/IPCamera/{possible_dir}/snap"):
                    for date2 in ftp.list(f"/IPCamera/{possible_dir}/snap/{date1}"):
                        for snapshot in ftp.list(f"/IPCamera/{possible_dir}/snap/{date1}/{date2}", extra=True):
                            if not snapshot['name'].endswith("jpg"):
                                continue

                            name = f"/IPCamera/{possible_dir}/snap/{date1}/{date2}/{snapshot['name']}"
                            date = self.get_datetime(name)

                            snapshots[date] = name

                # Build recordings array.
                for date1 in ftp.list(f"/IPCamera/{possible_dir}/record"):
                    for date2 in ftp.list(f"/IPCamera/{possible_dir}/record/{date1}"):
                        for recording in ftp.list(f"/IPCamera/{possible_dir}/record/{date1}/{date2}", extra=True):
                            if not recording['name'].endswith("avi"):
                                continue

                            name = f"/IPCamera/{possible_dir}/record/{date1}/{date2}/{recording['name']}"
                            date = self.get_datetime(name)

                            # update counts
                            LOGGER.debug(f"t1={date.date()},t2={today}")
                            if date.date() == today:
                                todays_count += 1
                            if last_capture_at is None or last_capture_at < date:
                                last_capture_at = date

                            # find a thumbnail
                            snapshot = [k for k in sorted(snapshots.keys()) if k > date]
                            if snapshot:
                                snapshot = snapshots[snapshot[0]]

                            recordings.append(Recording(date, name, snapshot, recording['size']))

        ftp.close()

        self._recordings = sorted(recordings, key=lambda x: x.created_at, reverse=True)
        self._todays_count = todays_count
        if last_capture_at is not None:
            self._last_capture_at = last_capture_at.strftime("%Y-%m-%dT%H:%M:%S")
        return 0

    def fetch_recordings(self):
        LOGGER.debug("fetch recordings")
        ftp = None
        cut_off = datetime.now() - timedelta(seconds=CUT_OFF_SECONDS)

        for recording in self._recordings:
            if os.path.exists(recording.content_url):
                continue

            if not ftp:
                self._camera.execute_command('startFtpServer')
                ftp = ftpretty(self._camera.host, self._camera.usr, self._camera.pwd, port=50021)

            LOGGER.debug(f"checking {recording.content_url}/{recording.remote_size}")
            ls = ftp.list(recording.remote_content_url, extra=True)
            if not ls:
                LOGGER.debug(" file disappeared?")
                continue
            ls = ls[0]
            if ls['datetime'] > cut_off:
                LOGGER.debug(" too new")
                continue
            if ls['size'] == 0:
                LOGGER.debug(" nothing in it")
                continue
            if ls['size'] != recording.remote_size:
                LOGGER.debug(" size changed!")
                recording.update_remote_size(ls['size'])
                continue

            LOGGER.debug(f"copying {recording.thumbnail_url}")
            ftp.get(recording.remote_thumbnail_url, recording.thumbnail_url)

            LOGGER.debug(f"creating {recording.content_url}")
            ftp.get(recording.remote_content_url, TMP_AVI)
            rc = os.system(f"ffmpeg -i {TMP_AVI} {recording.content_url}")
            os.unlink(TMP_AVI)
            if rc != 0:
                LOGGER.warning(f"failed: ffmpeg -i {TMP_AVI} {recording.content_url}")
                os.unlink(recording.content_url)
            else:
                LOGGER.debug(f"finished {recording.content_url}")
            break

        if ftp is not None:
            ftp.close()

    def update_data(self):
        """Fetch data from camera endpoint
        """
        now = time.monotonic()

        # save pre-update state
        recording = self._dev_state.get("recording", "0") == "1"

        # update
        LOGGER.debug("update state")
        self.update_dev_state()
        self.update_state()

        # check post-update state
        if recording and self._dev_state.get("recording", "0") != "1":
            LOGGER.debug("recording stopped, forcing update")
            self._last_recording = 0

        # check recordings
        if (self._last_recording + RECORDINGS_TIMEOUT) < now:
            LOGGER.debug("update recordings")
            self.update_recordings()
            self._last_recording = now

        # grab one recording per go after initial setup
        if self._last_update != 0:
            self.fetch_recordings()

        self._last_update = now

    async def _async_update_data(self):
        await self.hass.async_add_executor_job(
            self.update_data
        )
        return {
            "motion_status": self._dev_state["motionDetectAlarm"] != "0",
            "motion": self._dev_state["motionDetectAlarm"] == "2",
            "sound_status": self._dev_state["soundAlarm"] == "0",
            "sound": self._dev_state["soundAlarm"] == "2",
            "io_status": self._dev_state["IOAlarm"] == "0",
            "io": self._dev_state["IOAlarm"] == "2",
            "recording": self._dev_state["record"] == "1",

            "recordings": self._recordings,
            "last": self._last_capture_at,
            "captured_today": self._todays_count,
            "captured_total": len(self._recordings),

            "state": self._state
        }
