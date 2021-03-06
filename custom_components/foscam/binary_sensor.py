
from homeassistant.components.binary_sensor import BinarySensorEntity
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

    entries = [
        HassFoscamBinarySensor(data, config_entry, "motion", "motion"),
        HassFoscamBinarySensor(data, config_entry, "sound", "sound"),
        HassFoscamBinarySensor(data, config_entry, "io", None)
    ]
    async_add_entities(entries)


class HassFoscamBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """An implementation of a Foscam IP camera."""

    def __init__(self, data, config_entry, state_name, device_class):
        super().__init__(data["coordinator"])

        self._name = f"{state_name} {config_entry.title}"
        self._unique_id = f"{state_name}_{config_entry.entry_id}"
        self._state_name = state_name
        self._device_class = device_class
        LOGGER.info(f"starting {self._name}")

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.coordinator.data[self._state_name]

    @property
    def unique_id(self):
        """Return the entity unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of this camera binary sensor."""
        return self._name

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._device_class
