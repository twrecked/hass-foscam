"""Binary sensor platform for Foscam integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .updater import Updater


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a Foscam IP camera from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]

    entries = [
        HassFoscamBinarySensor(data, config_entry, "motion", BinarySensorDeviceClass.MOTION),
        HassFoscamBinarySensor(data, config_entry, "sound", BinarySensorDeviceClass.SOUND),
        HassFoscamBinarySensor(data, config_entry, "io", None),
    ]
    async_add_entities(entries)


class HassFoscamBinarySensor(CoordinatorEntity[Updater], BinarySensorEntity):
    """An implementation of a Foscam IP camera binary sensor."""

    def __init__(
        self,
        data: dict[str, Any],
        config_entry: ConfigEntry,
        state_name: str,
        device_class: BinarySensorDeviceClass | None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(data["coordinator"])

        self._name = f"{state_name} {config_entry.title}"
        self._unique_id = f"{state_name}_{config_entry.entry_id}"
        self._state_name = state_name
        self._attr_device_class = device_class
        LOGGER.info("Starting %s", self._name)

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return bool(self.coordinator.data.get(self._state_name, False))

    @property
    def unique_id(self) -> str:
        """Return the entity unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of this camera binary sensor."""
        return self._name
