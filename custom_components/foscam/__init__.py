"""The foscam component."""
from __future__ import annotations

import re
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
    CONF_RETENTION_DAYS,
    CONF_RTSP_PORT,
    DEFAULT_RETENTION_DAYS,
    DOMAIN,
    LOGGER,
    SERVICE_PRUNE_RECORDINGS,
    SERVICE_PTZ,
    SERVICE_PTZ_PRESET,
)
from .updater import Updater

PLATFORMS = ["camera", "binary_sensor", "sensor", "switch", "number"]


def get_camera_storage_dir(hass: HomeAssistant, entry: ConfigEntry) -> Path:
    """Resolve storage directory under /media/foscam/<camera-name>."""
    media_dirs = getattr(hass.config, "media_dirs", {}) or {}
    local_media = media_dirs.get("local")
    base_media_dir = Path(local_media) if local_media else Path("/media")

    camera_name = entry.title or entry.data.get(CONF_HOST, "camera")
    slug = re.sub(r"[^\w\s-]", "", camera_name.lower().strip())
    slug = re.sub(r"[-\s]+", "_", slug) or "camera"

    storage_dir = base_media_dir / "foscam" / slug
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create camera and coordinator."""
    storage_dir = get_camera_storage_dir(hass, entry)
    retention_days = entry.options.get(
        CONF_RETENTION_DAYS,
        entry.data.get(CONF_RETENTION_DAYS, DEFAULT_RETENTION_DAYS),
    )

    camera = FoscamCamera(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        rtsp_port=entry.data.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT),
        storage_dir=storage_dir,
        verbose=False,
    )
    camera.media.days_cutoff = retention_days

    coordinator = Updater(
        hass,
        camera,
        polling_interval=5,
        retention_days=retention_days,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "camera": camera,
        "coordinator": coordinator,
    }

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not data:
        return

    retention_days = entry.options.get(
        CONF_RETENTION_DAYS,
        entry.data.get(CONF_RETENTION_DAYS, DEFAULT_RETENTION_DAYS),
    )
    coordinator: Updater = data["coordinator"]
    camera: FoscamCamera = data["camera"]

    coordinator.retention_days = retention_days
    camera.media.days_cutoff = retention_days
    LOGGER.info("Updated %s retention days to %d", entry.title, retention_days)


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
