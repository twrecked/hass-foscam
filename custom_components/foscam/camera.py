"""This component provides basic support for Foscam IP cameras."""
import asyncio

from aiohttp import web
from contextlib import suppress
import async_timeout
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.camera import (
    PLATFORM_SCHEMA,
    SUPPORT_STREAM,
    Camera,
    CameraView
)
from homeassistant.components.camera.const import (
    CAMERA_IMAGE_TIMEOUT,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

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

MOVEMENT_ATTRS = {
    DIR_UP: "ptz_move_up",
    DIR_DOWN: "ptz_move_down",
    DIR_LEFT: "ptz_move_left",
    DIR_RIGHT: "ptz_move_right",
    DIR_TOPLEFT: "ptz_move_top_left",
    DIR_TOPRIGHT: "ptz_move_top_right",
    DIR_BOTTOMLEFT: "ptz_move_bottom_left",
    DIR_BOTTOMRIGHT: "ptz_move_bottom_right",
}

DEFAULT_TRAVELTIME = 0.125

ATTR_MOVEMENT = "movement"
ATTR_TRAVELTIME = "travel_time"
ATTR_PRESET_NAME = "preset_name"

PTZ_GOTO_PRESET_COMMAND = "ptz_goto_preset"

WS_TYPE_LIBRARY = "foscam_library"
SCHEMA_WS_LIBRARY = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {
        vol.Required("type"): WS_TYPE_LIBRARY,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("at_most"): cv.positive_int,
    }
)

RECORDING_URL = "/api/foscam_recording/{0}?index={1}&token={2}"
RECORDING_THUMBNAIL_URL = "/api/foscam_snapshot/{0}?index={1}&token={2}"


async def async_setup(hass, config):
    LOGGER.info("here1!!!")
    #eWebsockets

async def async_setup_platform(hass, config, _async_add_entities, _discovery_info=None):
    """Set up a Foscam IP Camera."""
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
    LOGGER.info("here2!!!")

    component = hass.data["camera"]
    hass.http.register_view(HassFoscamCameraImageView(component))
    hass.http.register_view(HassFoscamCameraRecordingView(component))
    hass.components.websocket_api.async_register_command(
        WS_TYPE_LIBRARY, websocket_library, SCHEMA_WS_LIBRARY
    )

    """Add a Foscam IP camera from a config entry."""
    platform = entity_platform.current_platform.get()
    platform.async_register_entity_service(
        SERVICE_PTZ,
        {
            vol.Required(ATTR_MOVEMENT): vol.In(
                [
                    DIR_UP,
                    DIR_DOWN,
                    DIR_LEFT,
                    DIR_RIGHT,
                    DIR_TOPLEFT,
                    DIR_TOPRIGHT,
                    DIR_BOTTOMLEFT,
                    DIR_BOTTOMRIGHT,
                ]
            ),
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

    LOGGER.info("first start")
    await data["coordinator"].async_config_entry_first_refresh()
    LOGGER.info("first end")

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
        self._stream = config_entry.data[CONF_STREAM]
        self._unique_id = config_entry.entry_id
        self._rtsp_port = config_entry.data[CONF_RTSP_PORT]

        LOGGER.info(f"starting {self._name}")

    @property
    def unique_id(self):
        """Return the entity unique ID."""
        return self._unique_id

    def camera_image(self):
        """Return a still image response from the camera."""
        # Send the request to snap a picture and return raw jpg data
        # Handle exception if host is not reachable or url failed
        result, response = self._foscam_session.snap_picture_2()
        if result != 0:
            return None

        return response

    def recording_image(self, index):
        """Return a still image response from the camera."""
        try:
            with open(self.coordinator.data["recordings"][index].thumbnail_url, mode='rb') as file:
                return file.read()
        except:
            return None

    async def async_recording_image(self, index):
        """Return bytes of recording image."""
        return await self.hass.async_add_executor_job(self.recording_image, index)

    def recording(self, index):
        """Return video response from the camera."""
        filename = self.coordinator.data["recordings"][index].content_url
        LOGGER.debug(f"trying {filename}")
        try:
            with open(self.coordinator.data["recordings"][index].content_url, mode='rb') as file:
                return file.read()
        except:
            return None

    async def async_recording(self, index):
        """Return bytes of recording."""
        return await self.hass.async_add_executor_job(self.recording, index)

    @property
    def supported_features(self):
        """Return supported features."""
        if self._rtsp_port:
            return SUPPORT_STREAM

        return None

    async def stream_source(self):
        """Return the stream source."""
        if self._rtsp_port:
            return f"rtsp://{self._username}:{self._password}@{self._foscam_session.host}:{self._rtsp_port}/video{self._stream}"
        return None

    @property
    def motion_detection_enabled(self):
        """Camera Motion Detection Status."""
        return self.coordinator.data["motion_status"]

    def enable_motion_detection(self):
        """Enable motion detection in camera."""
        try:
            ret = self._foscam_session.enable_motion_detection()

            if ret != 0:
                if ret == -3:
                    LOGGER.info(
                        "Can't set motion detection status, camera %s configured with non-admin user",
                        self._name,
                    )
                return

        except TypeError:
            LOGGER.debug(
                "Failed enabling motion detection on '%s'. Is it supported by the device?",
                self._name,
            )

    async def async_enable_motion_detection(self):
        """Call the job and enable motion detection."""
        await self.hass.async_add_executor_job(self.enable_motion_detection)
        await self.coordinator.async_request_refresh()

    def disable_motion_detection(self):
        """Disable motion detection."""
        try:
            ret = self._foscam_session.disable_motion_detection()

            if ret != 0:
                if ret == -3:
                    LOGGER.info(
                        "Can't set motion detection status, camera %s configured with non-admin user",
                        self._name,
                    )
                return

        except TypeError:
            LOGGER.debug(
                "Failed disabling motion detection on '%s'. Is it supported by the device?",
                self._name,
            )

    async def async_disable_motion_detection(self):
        """Call the job and disable motion detection."""
        await self.hass.async_add_executor_job(self.disable_motion_detection)
        await self.coordinator.async_request_refresh()

    async def async_perform_ptz(self, movement, travel_time):
        """Perform a PTZ action on the camera."""
        LOGGER.debug("PTZ action '%s' on %s", movement, self._name)

        movement_function = getattr(self._foscam_session, MOVEMENT_ATTRS[movement])

        ret, _ = await self.hass.async_add_executor_job(movement_function)

        if ret != 0:
            LOGGER.error("Error moving %s '%s': %s", movement, self._name, ret)
            return

        await asyncio.sleep(travel_time)

        ret, _ = await self.hass.async_add_executor_job(
            self._foscam_session.ptz_stop_run
        )

        if ret != 0:
            LOGGER.error("Error stopping movement on '%s': %s", self._name, ret)
            return

    async def async_perform_ptz_preset(self, preset_name):
        """Perform a PTZ preset action on the camera."""
        LOGGER.debug("PTZ preset '%s' on %s", preset_name, self._name)

        preset_function = getattr(self._foscam_session, PTZ_GOTO_PRESET_COMMAND)

        ret, _ = await self.hass.async_add_executor_job(preset_function, preset_name)

        if ret != 0:
            LOGGER.error(
                "Error moving to preset %s on '%s': %s", preset_name, self._name, ret
            )
            return

    @property
    def name(self):
        """Return the name of this camera."""
        return self._name

    def last_n_videos(self, at_most):
        """Return video response from the camera."""
        return self.coordinator.data["recordings"][:at_most]

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            "token2": self.access_tokens[-1],
            "last_recording": RECORDING_URL.format(self.entity_id, 0, self.access_tokens[-1]),
            "last_thumbnail": RECORDING_THUMBNAIL_URL.format(self.entity_id, 0, self.access_tokens[-1]),
            "last_recording1": RECORDING_URL.format(self.entity_id, 1, self.access_tokens[-1]),
            "last_thumbnail1": RECORDING_THUMBNAIL_URL.format(self.entity_id, 1, self.access_tokens[-1]),
        }
        return attrs


class HassFoscamCameraImageView(CameraView):
    """Camera view to serve an image."""

    url = "/api/foscam_snapshot/{entity_id}"
    name = "api:foscam:image"

    async def handle(self, request: web.Request, camera: HassFoscamCamera) -> web.Response:
        """Serve camera image."""
        with suppress(asyncio.CancelledError, asyncio.TimeoutError):
            index = int(request.query.get("index", "0"))
            async with async_timeout.timeout(CAMERA_IMAGE_TIMEOUT):
                image = await camera.async_recording_image(index)

            if image:
                return web.Response(body=image, content_type=camera.content_type)

        raise web.HTTPInternalServerError()


class HassFoscamCameraRecordingView(CameraView):
    """Camera view to serve a recording."""

    url = "/api/foscam_recording/{entity_id}"
    name = "api:foscam:recording"

    async def handle(self, request: web.Request, camera: HassFoscamCamera) -> web.Response:
        """Serve camera image."""
        with suppress(asyncio.CancelledError, asyncio.TimeoutError):
            index = int(request.query.get("index", "0"))
            async with async_timeout.timeout(CAMERA_IMAGE_TIMEOUT):
                image = await camera.async_recording(index)

            if image:
                return web.Response(body=image, content_type="video/mp4")

        raise web.HTTPInternalServerError()


@websocket_api.async_response
async def websocket_library(hass, connection, msg):
    try:
        camera = hass.data["camera"].get_entity(msg["entity_id"])

        videos = []
        LOGGER.debug("library+" + str(msg["at_most"]))
        for v in camera.last_n_videos(msg["at_most"]):
            videos.append(
                {
                    "created_at": v.created_at,
                    "created_at_pretty": v.created_at_pretty(),
                    "duration": v.duration,
                    "url": v.video_url,
                    "url_type": v.content_type,
                    "thumbnail": v.thumbnail_url,
                    "thumbnail_type": "image/jpeg",
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
    except HomeAssistantError as error:
        connection.send_message(
            websocket_api.error_message(
                msg["id"],
                "library_ws",
                "Unable to fetch library ({})".format(str(error)),
            )
        )
        _LOGGER.warning("{} library websocket failed".format(msg["entity_id"]))

