
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import (
    DOMAIN,
    LOGGER,
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add a Foscam IP camera from a config entry."""

    data = hass.data[DOMAIN][config_entry.entry_id]

    await data["coordinator"].async_config_entry_first_refresh()

    entries = [
            HassFoscamSensor(data, config_entry, "last", "mdi:fast-run"),
            HassFoscamSensor(data, config_entry, "captured_today", "mdi:file-video"),
            HassFoscamSensor(data, config_entry, "captured_total", "mdi:file-video")
    ]
    async_add_entities(entries)


class HassFoscamSensor(CoordinatorEntity, Entity):
    """An implementation of a Foscam IP camera."""

    def __init__(self, data, config_entry, state_name, icon):
        super().__init__(data["coordinator"])

        self._name = f"{state_name} {config_entry.title}"
        self._unique_id = f"{state_name}_{config_entry.entry_id}"
        self._state_name = state_name
        self._icon = icon
        LOGGER.info(f"starting {self._name}")

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data[self._state_name]

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def unique_id(self):
        """Return the entity unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of this camera binary sensor."""
        return self._name
