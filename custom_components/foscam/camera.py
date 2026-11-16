"""This component provides basic support for Foscam IP cameras."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.camera import (
    PLATFORM_SCHEMA,
    Camera,
    CameraView,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

try:
    from homeassistant.components.camera import CameraEntityFeature
    STREAM_FEATURE = CameraEntityFeature.STREAM
except (ImportError, AttributeError):
    from homeassistant.components.camera import SUPPORT_STREAM
    STREAM_FEATURE = SUPPORT_STREAM

from .const import (
    CONF_RTSP_PORT,
    CONF_STREAM,
    DOMAIN,
    LOGGER,
    SERVICE_PTZ,
    SERVICE_PTZ_PRESET,
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required("ip"): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Optional(CONF_NAME, default="Foscam Camera"): cv.string,
        vol.Optional(CONF_PORT, default=88): cv.port,
        vol.Optional(CONF_RTSP_PORT): cv.port,
    }
)

DIR_UP = "up"
DIR_DOWN = "down"
DIR_LEFT = "left"
DIR_RIGHT = "right"
DIR_TOPLEFT = "top_left"
DIR_TOPRIGHT = "top_right"
DIR_BOTTOMLEFT = "bottom_left"
DIR_BOTTOMRIGHT = "bottom_right"

VALID_MOVEMENTS = [
    DIR_UP,
    DIR_DOWN,
    DIR_LEFT,
    DIR_RIGHT,
    DIR_TOPLEFT,
    DIR_TOPRIGHT,
    DIR_BOTTOMLEFT,
    DIR_BOTTOMRIGHT,
]

DEFAULT_TRAVELTIME = 0.125

ATTR_MOVEMENT = "movement"
ATTR_TRAVELTIME = "travel_time"
ATTR_PRESET_NAME = "preset_name"

WS_TYPE_LIBRARY = "foscam_library"
SCHEMA_WS_LIBRARY = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {
        vol.Required("type"): WS_TYPE_LIBRARY,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("at_most"): cv.positive_int,
    }
)

RECORDING_URL = "/api/foscam_recording/{0}?clip={1}&token={2}"
RECORDING_THUMBNAIL_URL = "/api/foscam_snapshot/{0}?clip={1}&token={2}"


async def async_setup_platform(hass, config, _async_add_entities, _discovery_info=None):
    """Set up a Foscam IP Camera (deprecated import)."""
    LOGGER.warning(
        "Loading foscam via platform config is deprecated, it will be automatically imported; Please remove it afterwards"
    )

    config_new = {
        CONF_NAME: config[CONF_NAME],
        CONF_HOST: config["ip"],
        CONF_PORT: config[CONF_PORT],
        CONF_USERNAME: config[CONF_USERNAME],
        CONF_PASSWORD: config[CONF_PASSWORD],
        CONF_STREAM: "Main",
        CONF_RTSP_PORT: config.get(CONF_RTSP_PORT, 554),
    }

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=config_new
        )
    )


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up Foscam camera from config entry."""
    component = hass.data["camera"]
    hass.http.register_view(HassFoscamCameraImageView(component))
    hass.http.register_view(HassFoscamCameraRecordingView(component))
    hass.components.websocket_api.async_register_command(
        WS_TYPE_LIBRARY, websocket_library, SCHEMA_WS_LIBRARY
    )

    platform = entity_platform.current_platform.get()
    platform.async_register_entity_service(
        SERVICE_PTZ,
        {
            vol.Required(ATTR_MOVEMENT): vol.In(VALID_MOVEMENTS),
            vol.Optional(ATTR_TRAVELTIME, default=DEFAULT_TRAVELTIME): cv.small_float,
        },
        "async_perform_ptz",
    )

    platform.async_register_entity_service(
        SERVICE_PTZ_PRESET,
        {
            vol.Required(ATTR_PRESET_NAME): cv.string,
        },
        "async_perform_ptz_preset",
    )

    data = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([HassFoscamCamera(data, config_entry)])


class HassFoscamCamera(CoordinatorEntity, Camera):
    """An implementation of a Foscam IP camera."""

    def __init__(self, data, config_entry):
        """Initialize a Foscam camera."""
        CoordinatorEntity.__init__(self, data["coordinator"])
        Camera.__init__(self)

        self._foscam_session = data["camera"]
        self._name = config_entry.title
        self._username = config_entry.data[CONF_USERNAME]
        self._password = config_entry.data[CONF_PASSWORD]
        self._stream = config_entry.data.get(CONF_STREAM, "Main")
        self._unique_id = config_entry.entry_id
        self._rtsp_port = config_entry.data.get(CONF_RTSP_PORT)

        self._image_source = None
        LOGGER.info("Starting Foscam camera %s", self._name)

    @property
    def unique_id(self):
        """Return the entity unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of this camera."""
        return self._name

    @property
    def state(self):
        """Return device state string."""
        return self.coordinator.data.get("state", "idle")

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image response from the camera asynchronously."""
        try:
            data = await self._foscam_session.get_snapshot()
            self._image_source = "capture/" + datetime.now().strftime("%m-%d %H:%M:%S")
            return data
        except Exception as err:
            LOGGER.debug("Snapshot failed on %s: %s", self._name, err)
            return None

    def camera_image(self, width=None, height=None):
        """Synchronous camera image fallback."""
        return None

    @property
    def supported_features(self):
        """Return supported features."""
        if self._rtsp_port:
            return STREAM_FEATURE
        return 0

    async def stream_source(self):
        """Return the stream source."""
        if self._rtsp_port:
            return self._foscam_session.rtsp_url(stream=self._stream)
        return None

    @property
    def motion_detection_enabled(self):
        """Camera Motion Detection Status."""
        return self.coordinator.data.get("motion_status", False)

    async def async_enable_motion_detection(self):
        """Enable motion detection in camera."""
        try:
            await self._foscam_session.enable_motion_detection()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            LOGGER.warning("Failed enabling motion detection on %s: %s", self._name, err)

    async def async_disable_motion_detection(self):
        """Disable motion detection."""
        try:
            await self._foscam_session.disable_motion_detection()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            LOGGER.warning("Failed disabling motion detection on %s: %s", self._name, err)

    async def async_perform_ptz(self, movement: str, travel_time: float):
        """Perform a PTZ action on the camera."""
        LOGGER.debug("PTZ action '%s' on %s (travel_time=%.2f)", movement, self._name, travel_time)
        try:
            await self._foscam_session.ptz(movement, travel_time)
        except Exception as err:
            LOGGER.error("Error moving %s '%s': %s", movement, self._name, err)

    async def async_perform_ptz_preset(self, preset_name: str):
        """Perform a PTZ preset action on the camera."""
        LOGGER.debug("PTZ preset '%s' on %s", preset_name, self._name)
        try:
            await self._foscam_session.ptz_preset(preset_name)
        except Exception as err:
            LOGGER.error("Error moving to preset %s on '%s': %s", preset_name, self._name, err)

    def last_n_videos(self, at_most: int):
        """Return video response from the camera."""
        return self.coordinator.data.get("recordings", [])[:at_most]

    @property
    def image_source(self):
        return self._image_source

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        recordings = self.coordinator.data.get("recordings", [])
        first_id = recordings[0].clip_id if recordings else "0"
        token = self.access_tokens[-1] if self.access_tokens else ""

        return {
            "last_video": RECORDING_URL.format(self.entity_id, first_id, token),
            "last_thumbnail": RECORDING_THUMBNAIL_URL.format(self.entity_id, first_id, token),
            "image_source": self.image_source,
            "state": self.state,
        }


class HassFoscamCameraImageView(CameraView):
    """Camera view to serve a recording thumbnail or live snapshot."""

    url = "/api/foscam_snapshot/{entity_id}"
    name = "api:foscam:image"

    async def handle(self, request: web.Request, camera: HassFoscamCamera) -> web.StreamResponse:
        """Serve thumbnail image."""
        try:
            clip_id = request.query.get("clip")
            rec = None
            recordings = camera.coordinator.data.get("recordings", [])

            if clip_id:
                rec = next((r for r in recordings if r.clip_id == clip_id), None)
            elif "index" in request.query:
                try:
                    index = int(request.query.get("index", "0"))
                    if 0 <= index < len(recordings):
                        rec = recordings[index]
                except (ValueError, TypeError):
                    pass

            if rec and rec.is_thumbnail_downloaded:
                return web.FileResponse(
                    path=rec.local_thumbnail_path, headers={"Content-Type": "image/jpeg"}
                )

            # Fallback to camera snapshot
            image = await camera.async_camera_image()
            if image:
                return web.Response(body=image, content_type="image/jpeg")

        except Exception as err:
            LOGGER.debug("Error serving thumbnail for %s: %s", camera.entity_id, err)

        raise web.HTTPNotFound()


class HassFoscamCameraRecordingView(CameraView):
    """Camera view to serve a recording with range request streaming."""

    url = "/api/foscam_recording/{entity_id}"
    name = "api:foscam:recording"

    async def handle(self, request: web.Request, camera: HassFoscamCamera) -> web.StreamResponse:
        """Serve video file supporting HTTP range requests."""
        try:
            clip_id = request.query.get("clip")
            rec = None
            recordings = camera.coordinator.data.get("recordings", [])

            if clip_id:
                rec = next((r for r in recordings if r.clip_id == clip_id), None)
            elif "index" in request.query:
                try:
                    index = int(request.query.get("index", "0"))
                    if 0 <= index < len(recordings):
                        rec = recordings[index]
                except (ValueError, TypeError):
                    pass

            if rec is None and recordings:
                rec = recordings[0]

            if rec:
                # Ensure local video file is downloaded
                if not rec.is_downloaded and not rec.is_raw_downloaded:
                    try:
                        await camera._foscam_session.media.download_recording(rec)
                    except Exception as err:
                        LOGGER.warning("On-demand download failed for %s: %s", rec.clip_id, err)
                        raise web.HTTPNotFound()

                video_path = rec.local_video_path if rec.is_downloaded else rec.local_raw_path
                if video_path.is_file():
                    content_type = "video/mp4" if rec.is_downloaded else "video/x-msvideo"
                    return web.FileResponse(path=video_path, headers={"Content-Type": content_type})

        except Exception as err:
            LOGGER.debug("Error serving video for %s: %s", camera.entity_id, err)

        raise web.HTTPNotFound()


@websocket_api.async_response
async def websocket_library(hass, connection, msg):
    """Websocket command returning library video catalog."""
    try:
        camera = hass.data["camera"].get_entity(msg["entity_id"])
        token = camera.access_tokens[-1] if camera.access_tokens else ""

        videos = []
        LOGGER.debug("foscam_library requested at_most=%s", msg.get("at_most"))
        for v in camera.last_n_videos(msg["at_most"]):
            videos.append(
                {
                    "created_at": v.created_at.isoformat()
                    if hasattr(v.created_at, "isoformat")
                    else str(v.created_at),
                    "created_at_pretty": v.created_at_pretty(),
                    "duration": v.duration,
                    "url": RECORDING_URL.format(msg["entity_id"], v.clip_id, token),
                    "url_type": v.content_type,
                    "thumbnail": RECORDING_THUMBNAIL_URL.format(msg["entity_id"], v.clip_id, token),
                    "thumbnail_type": v.thumbnail_type,
                    "object": v.object_type,
                    "object_region": v.object_region,
                    "trigger": v.object_type,
                    "trigger_region": v.object_region,
                }
            )

        connection.send_message(
            websocket_api.result_message(
                msg["id"],
                {
                    "videos": videos,
                },
            )
        )
    except Exception as error:
        connection.send_message(
            websocket_api.error_message(
                msg["id"],
                "library_ws",
                f"Unable to fetch library ({error})",
            )
        )
        LOGGER.warning("%s library websocket failed: %s", msg.get("entity_id"), error)
