"""Number platform for Foscam integration."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .updater import Updater


@dataclass(frozen=True, kw_only=True)
class FoscamNumberDescription(NumberEntityDescription):
    """Description of a Foscam number entity."""

    capability: str
    state_key: str
    set_value_fn: Callable[[Updater, int], Awaitable[None]]


NUMBER_DESCRIPTIONS: tuple[FoscamNumberDescription, ...] = (
    FoscamNumberDescription(
        key="volume",
        name="Device volume",
        capability="volume",
        icon="mdi:volume-high",
        state_key="volume",
        set_value_fn=lambda u, v: u.async_set_volume(v),
        native_min_value=0,
        native_max_value=100,
        native_step=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Foscam number entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: Updater = data["coordinator"]

    entities = [
        HassFoscamNumber(data, config_entry, desc)
        for desc in NUMBER_DESCRIPTIONS
        if coordinator.has_capability(desc.capability)
    ]
    if entities:
        async_add_entities(entities)


class HassFoscamNumber(CoordinatorEntity[Updater], NumberEntity):
    """An implementation of a Foscam number entity."""

    entity_description: FoscamNumberDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        data: dict[str, Any],
        config_entry: ConfigEntry,
        description: FoscamNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(data["coordinator"])

        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{description.key}_{config_entry.entry_id}"
        self._attr_icon = description.icon
        self._attr_translation_key = description.key
        self._entry_id = config_entry.entry_id
        self._entry_title = config_entry.title
        LOGGER.info("Starting %s %s number", config_entry.title, description.name)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information linking this entity to the camera."""
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
    def native_value(self) -> float:
        """Return current value."""
        return float(self.coordinator.data.get(self.entity_description.state_key, 0))

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self.entity_description.set_value_fn(self.coordinator, int(value))
