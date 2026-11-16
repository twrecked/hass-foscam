"""Sensor platform for Foscam integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
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
    """Add a Foscam IP camera sensors from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]

    entries = [
        HassFoscamSensor(data, config_entry, "last", "mdi:fast-run"),
        HassFoscamSensor(data, config_entry, "captured_today", "mdi:file-video"),
        HassFoscamSensor(data, config_entry, "captured_total", "mdi:file-video"),
    ]
    async_add_entities(entries)


class HassFoscamSensor(CoordinatorEntity[Updater], SensorEntity):
    """An implementation of a Foscam IP camera sensor."""

    def __init__(
        self,
        data: dict[str, Any],
        config_entry: ConfigEntry,
        state_name: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(data["coordinator"])

        self._name = f"{state_name} {config_entry.title}"
        self._unique_id = f"{state_name}_{config_entry.entry_id}"
        self._state_name = state_name
        self._attr_icon = icon
        LOGGER.info("Starting %s", self._name)

    @property
    def native_value(self) -> str | int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._state_name)

    @property
    def unique_id(self) -> str:
        """Return the entity unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of this camera sensor."""
        return self._name
