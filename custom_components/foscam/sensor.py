"""Sensor platform for Foscam integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .updater import Updater

SENSOR_TYPES = [
    ("last", "Last Capture", "mdi:run-fast"),
    ("captured_today", "Captured Today", "mdi:file-video"),
    ("captured_total", "Total Captures", "mdi:file-video"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a Foscam IP camera sensors from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]

    entries = [
        HassFoscamSensor(data, config_entry, state_key, display_name, icon)
        for state_key, display_name, icon in SENSOR_TYPES
    ]
    async_add_entities(entries)


class HassFoscamSensor(CoordinatorEntity[Updater], SensorEntity):
    """An implementation of a Foscam IP camera sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        data: dict[str, Any],
        config_entry: ConfigEntry,
        state_key: str,
        display_name: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(data["coordinator"])

        self._state_key = state_key
        self._attr_name = display_name
        self._attr_unique_id = f"{state_key}_{config_entry.entry_id}"
        self._attr_icon = icon
        self._entry_id = config_entry.entry_id
        self._entry_title = config_entry.title
        LOGGER.info("Starting %s %s", config_entry.title, display_name)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information linking this sensor to the camera."""
        camera = self.coordinator._camera
        info = camera._dev_info or {}
        mac = camera.mac_address or self._entry_id
        return DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=self._entry_title,
            manufacturer="Foscam",
            model=info.get("modelName", "IP Camera"),
            sw_version=info.get("firmwareVer"),
            hw_version=info.get("hardwareVer"),
            configuration_url=f"http://{camera.host}:{camera.port}",
        )

    @property
    def icon(self) -> str | None:
        """Icon to use in the frontend."""
        if self._state_key == "last":
            recordings = self.coordinator.data.get("recordings", [])
            if recordings:
                trigger = getattr(recordings[0], "trigger", "motion")
                if trigger == "motion":
                    return "mdi:run-fast"
                if trigger == "alarm":
                    return "mdi:bell-ring"
                if trigger == "schedule":
                    return "mdi:calendar-clock"
            return "mdi:run-fast"
        return self._attr_icon

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return attributes for sensor."""
        if self._state_key == "last":
            recordings = self.coordinator.data.get("recordings", [])
            if recordings:
                latest = recordings[0]
                return {
                    "clip_id": latest.clip_id,
                    "trigger": latest.trigger,
                    "duration": latest.duration,
                    "video_url": latest.content_url,
                    "thumbnail_url": latest.thumbnail_url,
                }
        return None

    @property
    def native_value(self) -> str | int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._state_key)
