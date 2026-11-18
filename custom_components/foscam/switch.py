"""Switch platform for Foscam integration."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .updater import Updater


@dataclass(frozen=True)
class FoscamSwitchDescription:
    """Description of a Foscam switch entity."""

    key: str
    name: str
    capability: str
    icon: str
    state_key: str
    turn_on_fn: Callable[[Updater], Awaitable[None]]
    turn_off_fn: Callable[[Updater], Awaitable[None]]


SWITCH_DESCRIPTIONS: tuple[FoscamSwitchDescription, ...] = (
    FoscamSwitchDescription(
        key="sleep",
        name="Sleep mode",
        capability="sleep",
        icon="mdi:sleep",
        state_key="sleep",
        turn_on_fn=lambda u: u.async_set_sleep(True),
        turn_off_fn=lambda u: u.async_set_sleep(False),
    ),
    FoscamSwitchDescription(
        key="led",
        name="Status light",
        capability="led",
        icon="mdi:led-on",
        state_key="led",
        turn_on_fn=lambda u: u.async_set_led(True),
        turn_off_fn=lambda u: u.async_set_led(False),
    ),
    FoscamSwitchDescription(
        key="flip",
        name="Flip",
        capability="flip",
        icon="mdi:flip-vertical",
        state_key="flip",
        turn_on_fn=lambda u: u.async_set_flip(True),
        turn_off_fn=lambda u: u.async_set_flip(False),
    ),
    FoscamSwitchDescription(
        key="mirror",
        name="Mirror",
        capability="mirror",
        icon="mdi:flip-horizontal",
        state_key="mirror",
        turn_on_fn=lambda u: u.async_set_mirror(True),
        turn_off_fn=lambda u: u.async_set_mirror(False),
    ),
    FoscamSwitchDescription(
        key="ir",
        name="Infrared mode",
        capability="ir",
        icon="mdi:weather-night",
        state_key="ir_auto",
        turn_on_fn=lambda u: u.async_set_ir(True),
        turn_off_fn=lambda u: u.async_set_ir(False),
    ),
    FoscamSwitchDescription(
        key="mute",
        name="Volume muted",
        capability="mute",
        icon="mdi:volume-mute",
        state_key="mute",
        turn_on_fn=lambda u: u.async_set_mute(True),
        turn_off_fn=lambda u: u.async_set_mute(False),
    ),
    FoscamSwitchDescription(
        key="white_light",
        name="White light",
        capability="white_light",
        icon="mdi:lightbulb-spot",
        state_key="white_light",
        turn_on_fn=lambda u: u.async_set_white_light(True),
        turn_off_fn=lambda u: u.async_set_white_light(False),
    ),
    FoscamSwitchDescription(
        key="siren",
        name="Siren alarm",
        capability="siren",
        icon="mdi:alarm-light",
        state_key="siren",
        turn_on_fn=lambda u: u.async_set_siren(True),
        turn_off_fn=lambda u: u.async_set_siren(False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Foscam switch entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: Updater = data["coordinator"]

    entities = [
        HassFoscamSwitch(data, config_entry, desc)
        for desc in SWITCH_DESCRIPTIONS
        if coordinator.has_capability(desc.capability)
    ]
    if entities:
        async_add_entities(entities)


class HassFoscamSwitch(CoordinatorEntity[Updater], SwitchEntity):
    """An implementation of a Foscam switch entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        data: dict[str, Any],
        config_entry: ConfigEntry,
        description: FoscamSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(data["coordinator"])

        self.entity_description = description
        self._desc = description
        self._attr_name = description.name
        self._attr_unique_id = f"{description.key}_{config_entry.entry_id}"
        self._attr_icon = description.icon
        self._entry_id = config_entry.entry_id
        self._entry_title = config_entry.title
        LOGGER.info("Starting %s %s switch", config_entry.title, description.name)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information linking this switch to the camera."""
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
        """Return true if switch is on."""
        return bool(self.coordinator.data.get(self._desc.state_key, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn switch on."""
        await self._desc.turn_on_fn(self.coordinator)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn switch off."""
        await self._desc.turn_off_fn(self.coordinator)
