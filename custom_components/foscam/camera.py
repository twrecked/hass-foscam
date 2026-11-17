"""This component provides basic support for Foscam IP cameras."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.camera import (
    PLATFORM_SCHEMA,
    Camera,
    CameraEntityFeature,
    CameraView,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from foscam.exceptions import FoscamError

from .const import (
    CONF_RTSP_PORT,
    CONF_STREAM,
    DOMAIN,
    LOGGER,
    SERVICE_PRUNE_RECORDINGS,
    SERVICE_PTZ,
    SERVICE_PTZ_PRESET,
)
from .updater import Updater

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


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    _async_add_entities: AddEntitiesCallback,
    _discovery_info: DiscoveryInfoType | None = None,
) -> None:
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


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Foscam camera from config entry."""
    component = hass.data["camera"]
    hass.http.register_view(HassFoscamCameraImageView(component))
    hass.http.register_view(HassFoscamCameraRecordingView(component))
    websocket_api.async_register_command(
        hass, 
        WS_TYPE_LIBRARY, websocket_library, SCHEMA_WS_LIBRARY
    )

    platform = entity_platform.current_platform.get()
    if platform:
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

        platform.async_register_entity_service(
            SERVICE_PRUNE_RECORDINGS,
            {
                vol.Optional("days", default=30): cv.positive_int,
            },
            "async_prune_recordings",
        )

    data = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([HassFoscamCamera(data, config_entry)])


class HassFoscamCamera(CoordinatorEntity[Updater], Camera):
    """An implementation of a Foscam IP camera."""

    def __init__(self, data: dict[str, Any], config_entry: ConfigEntry) -> None:
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
        self._attr_has_entity_name = True
        self._attr_name = None

        self._image_source: str | None = None
        LOGGER.info("Starting Foscam camera %s", self._name)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this camera."""
        info = self._foscam_session._dev_info or {}
        mac = self._foscam_session.mac_address or self._unique_id
        return DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=self._name,
            manufacturer="Foscam",
            model=info.get("modelName", "IP Camera"),
            sw_version=info.get("firmwareVer"),
            hw_version=info.get("hardwareVer"),
            configuration_url=f"http://{self._foscam_session.host}:{self._foscam_session.port}",
        )

    @property
    def unique_id(self) -> str:
        """Return the entity unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of this camera."""
        return self._name

    @property
    def is_recording(self) -> bool:
        """Return true if the camera is recording."""
        return bool(self.coordinator.data.get("recording", False))

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image response from the camera asynchronously."""
        try:
            data = await self._foscam_session.get_snapshot()
            self._image_source = "capture/" + datetime.now().strftime("%m-%d %H:%M:%S")
            return data
        except (FoscamError, TimeoutError, OSError) as err:
            LOGGER.debug("Snapshot failed on %s: %s", self._name, err)
            return None

    def camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Synchronous camera image fallback."""
        return None

    @property
    def supported_features(self) -> CameraEntityFeature:
        """Return supported features."""
        if self._rtsp_port:
            return CameraEntityFeature.STREAM
        return CameraEntityFeature(0)

    async def stream_source(self) -> str | None:
        """Return the stream source."""
        if self._rtsp_port:
            return self._foscam_session.rtsp_url(stream=self._stream)
        return None

    @property
    def motion_detection_enabled(self) -> bool:
        """Camera Motion Detection Status."""
        return bool(self.coordinator.data.get("motion_status", False))

    async def async_enable_motion_detection(self) -> None:
        """Enable motion detection in camera."""
        try:
            await self._foscam_session.enable_motion_detection()
            await self.coordinator.async_request_refresh()
        except (FoscamError, TimeoutError, OSError) as err:
            LOGGER.warning("Failed enabling motion detection on %s: %s", self._name, err)

    async def async_disable_motion_detection(self) -> None:
        """Disable motion detection."""
        try:
            await self._foscam_session.disable_motion_detection()
            await self.coordinator.async_request_refresh()
        except (FoscamError, TimeoutError, OSError) as err:
            LOGGER.warning("Failed disabling motion detection on %s: %s", self._name, err)

    async def async_perform_ptz(self, movement: str, travel_time: float) -> None:
        """Perform a PTZ action on the camera."""
        LOGGER.debug("PTZ action '%s' on %s (travel_time=%.2f)", movement, self._name, travel_time)
        try:
            await self._foscam_session.ptz(movement, travel_time)
        except (FoscamError, TimeoutError, OSError) as err:
            LOGGER.error("Error moving %s '%s': %s", movement, self._name, err)

    async def async_perform_ptz_preset(self, preset_name: str) -> None:
        """Perform a PTZ preset action on the camera."""
        LOGGER.debug("PTZ preset '%s' on %s", preset_name, self._name)
        try:
            await self._foscam_session.ptz_preset(preset_name)
        except (FoscamError, TimeoutError, OSError) as err:
            LOGGER.error("Error moving to preset %s on '%s': %s", preset_name, self._name, err)

    async def async_prune_recordings(self, days: int = 30) -> None:
        """Prune local recordings older than retention days."""
        try:
            deleted, freed = await self._foscam_session.media.prune_local(days=days)
            LOGGER.info("Pruned %d recordings (%d bytes freed) on %s", deleted, freed, self._name)
        except (FoscamError, OSError) as err:
            LOGGER.warning("Failed pruning recordings on %s: %s", self._name, err)

    def last_n_videos(self, at_most: int) -> list[Any]:
        """Return video response from the camera."""
        return self.coordinator.data.get("recordings", [])[:at_most]

    @property
    def image_source(self) -> str | None:
        return self._image_source

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        recordings = self.coordinator.data.get("recordings", [])
        first_id = recordings[0].clip_id if recordings else "0"
        token = self.access_tokens[-1] if self.access_tokens else ""

        return {
            "last_video": RECORDING_URL.format(self.entity_id, first_id, token),
            "last_thumbnail": RECORDING_THUMBNAIL_URL.format(self.entity_id, first_id, token),
            "image_source": self.image_source,
            "state": self.coordinator.data.get("state", "idle"),
        }


class HassFoscamCameraImageView(CameraView):
    """Camera view to serve a recording thumbnail or live snapshot."""

    url = "/api/foscam_snapshot/{entity_id}"
    name = "api:foscam:image"

    async def handle(self, request: web.Request, camera: Camera) -> web.StreamResponse:
        """Serve thumbnail image."""
        if not isinstance(camera, HassFoscamCamera):
            raise web.HTTPBadRequest()

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

        except (FoscamError, TimeoutError, OSError) as err:
            LOGGER.debug("Error serving thumbnail for %s: %s", camera.entity_id, err)

        raise web.HTTPNotFound()


class HassFoscamCameraRecordingView(CameraView):
    """Camera view to serve a recording with range request streaming."""

    url = "/api/foscam_recording/{entity_id}"
    name = "api:foscam:recording"

    async def handle(self, request: web.Request, camera: Camera) -> web.StreamResponse:
        """Serve video file supporting HTTP range requests."""
        if not isinstance(camera, HassFoscamCamera):
            raise web.HTTPBadRequest()

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
                    except (FoscamError, TimeoutError, OSError) as err:
                        LOGGER.warning("On-demand download failed for %s: %s", rec.clip_id, err)
                        raise web.HTTPNotFound() from err

                video_path = rec.local_video_path if rec.is_downloaded else rec.local_raw_path
                if video_path.is_file():
                    content_type = "video/mp4" if rec.is_downloaded else "video/x-msvideo"
                    return web.FileResponse(path=video_path, headers={"Content-Type": content_type})

        except (FoscamError, TimeoutError, OSError) as err:
            LOGGER.debug("Error serving video for %s: %s", camera.entity_id, err)

        raise web.HTTPNotFound()


@websocket_api.async_response
async def websocket_library(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Websocket command returning library video catalog."""
    try:
        camera = hass.data["camera"].get_entity(msg["entity_id"])
        if not isinstance(camera, HassFoscamCamera):
            connection.send_message(
                websocket_api.error_message(
                    msg["id"], "not_found", "Entity is not a Foscam camera"
                )
            )
            return

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
    except (FoscamError, TimeoutError, OSError, KeyError) as error:
        connection.send_message(
            websocket_api.error_message(
                msg["id"],
                "library_ws",
                f"Unable to fetch library ({error})",
            )
        )
        LOGGER.warning("%s library websocket failed: %s", msg.get("entity_id"), error)
