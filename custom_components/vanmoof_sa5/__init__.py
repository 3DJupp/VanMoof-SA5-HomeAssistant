"""The VanMoof SA5 Home Assistant integration."""
from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from .api import async_bootstrap_client
from .const import DOMAIN, PLATFORMS, REMOVED_ENTITY_SUFFIXES
from .coordinator import VanMoofDataUpdateCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VanMoof SA5 from a config entry."""
    api = await async_bootstrap_client(hass, dict(entry.data))
    coordinator = VanMoofDataUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(platform) for platform in PLATFORMS]
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _async_remove_obsolete_entities(hass, entry)
    return True

def _async_remove_obsolete_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete registry entries of entities this integration no longer provides."""
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id.endswith(REMOVED_ENTITY_SUFFIXES):
            registry.async_remove(entity.entity_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, [Platform(platform) for platform in PLATFORMS]
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
