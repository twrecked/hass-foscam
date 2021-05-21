import os
import subprocess

from .const import (
    LOGGER
)


class Recording:

    def __init__(self, date, recording, snapshot, size):
        self._date = date
        self._remote_recording = recording
        self._remote_snapshot = snapshot
        self._remote_size = size

        base = os.path.splitext(os.path.basename(recording))[0]
        self._recording = f"foscam/{base}.mp4"
        self._snapshot = f"foscam/{base}.jpg"

        self._duration = None
        LOGGER.debug(f"Recording({self._recording})")

    @property
    def created_at(self):
        """Returns date video was creaed."""
        return self._date

    def created_at_pretty(self, date_format=None):
        """Returns date video was taken formated with `last_date_format`"""
        if date_format:
            return self._date.strftime(date_format)
        return self._date().strftime("%Y-%m-%dT%H:%M:%S")

    @property
    def content_type(self):
        return "video/mp4"

    @property
    def content_url(self):
        return self._recording

    @property
    def duration(self):
        if self._duration is None:
            if os.path.exists(self._recording):
                result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                         "format=duration", "-of",
                                         "default=noprint_wrappers=1:nokey=1", self._recording],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
                self._duration = int(float(result.stdout))
                LOGGER.debug(f"duration of {self._remote_recording} is {self._duration}")
        if self._duration:
            return self._duration
        return 1

    @property
    def thumbnail_type(self):
        return "image/jpeg"

    @property
    def thumbnail_url(self):
        return self._snapshot

    @property
    def object_region(self):
        return None

    @property
    def object_type(self):
        return None

    @property
    def remote_content_url(self):
        return self._remote_recording

    @property
    def remote_thumbnail_url(self):
        return self._remote_snapshot

    @property
    def remote_size(self):
        return self._remote_size
