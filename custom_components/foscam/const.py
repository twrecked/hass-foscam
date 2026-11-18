"""Constants for Foscam component."""
import logging

LOGGER = logging.getLogger(__package__)

DOMAIN = "foscam"

CONF_RTSP_PORT = "rtsp_port"
CONF_STREAM = "stream"

SERVICE_PTZ = "ptz"
SERVICE_PTZ_PRESET = "ptz_preset"
SERVICE_PRUNE_RECORDINGS = "prune_recordings"

CONF_RETENTION_DAYS = "retention_days"
DEFAULT_RETENTION_DAYS = 30
