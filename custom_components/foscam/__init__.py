"""The foscam component."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_registry import async_migrate_entries

from foscam import FoscamCamera
from foscam.exceptions import FoscamError

from .config_flow import DEFAULT_RTSP_PORT
from .const import (
    CONF_RTSP_PORT,
    DOMAIN,
    LOGGER,
    SERVICE_PRUNE_RECORDINGS,
    SERVICE_PTZ,
    SERVICE_PTZ_PRESET,
)
from .updater import Updater

PLATFORMS = ["camera", "binary_sensor", "sensor", "switch", "number"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create camera and coordinator.

    Everything comes through a single camera entity.
    """
    storage_dir = Path(hass.config.config_dir) / "foscam"

    camera = FoscamCamera(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        rtsp_port=entry.data.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT),
        storage_dir=storage_dir,
        verbose=False,
    )

    coordinator = Updater(
        hass,
        camera,
        5,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "camera": camera,
        "coordinator": coordinator,
    }

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, {})
        camera: FoscamCamera | None = data.get("camera")
        if camera:
            await camera.close()

        if not hass.data[DOMAIN]:
            hass.services.async_remove(domain=DOMAIN, service=SERVICE_PTZ)
            hass.services.async_remove(domain=DOMAIN, service=SERVICE_PTZ_PRESET)
            hass.services.async_remove(domain=DOMAIN, service=SERVICE_PRUNE_RECORDINGS)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        # Change unique id
        @callback
        def update_unique_id(entry: Any) -> dict[str, str]:
            return {"new_unique_id": config_entry.entry_id}

        await async_migrate_entries(hass, config_entry.entry_id, update_unique_id)

        # Get RTSP port from the camera or use fallback
        camera = FoscamCamera(
            host=config_entry.data[CONF_HOST],
            port=config_entry.data[CONF_PORT],
            username=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
            verbose=False,
        )

        try:
            info = await camera.get_info()
            rtsp_port = info.get("rtspPort") or DEFAULT_RTSP_PORT
        except (FoscamError, TimeoutError, OSError):
            rtsp_port = DEFAULT_RTSP_PORT
        finally:
            await camera.close()

        hass.config_entries.async_update_entry(
            config_entry,
            unique_id=None,
            data={**config_entry.data, CONF_RTSP_PORT: rtsp_port},
            version=2,
        )

    LOGGER.info("Migration to version %s successful", config_entry.version)
    return True
