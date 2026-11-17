"""Binary sensor platform for Foscam integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .updater import Updater

SENSOR_TYPES = [
    ("motion", "Motion", BinarySensorDeviceClass.MOTION),
    ("sound", "Sound", BinarySensorDeviceClass.SOUND),
    ("io", "I/O Alarm", None),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a Foscam IP camera binary sensors from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]

    entries = [
        HassFoscamBinarySensor(
            data, config_entry, state_key, display_name, device_class
        )
        for state_key, display_name, device_class in SENSOR_TYPES
    ]
    async_add_entities(entries)


class HassFoscamBinarySensor(CoordinatorEntity[Updater], BinarySensorEntity):
    """An implementation of a Foscam IP camera binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        data: dict[str, Any],
        config_entry: ConfigEntry,
        state_key: str,
        display_name: str,
        device_class: BinarySensorDeviceClass | None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(data["coordinator"])

        self._state_key = state_key
        self._attr_name = display_name
        self._attr_unique_id = f"{state_key}_{config_entry.entry_id}"
        self._attr_device_class = device_class
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
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return bool(self.coordinator.data.get(self._state_key, False))
