"""The Envertech EVT Local integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import EnvertechCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT]

type EnvertechConfigEntry = ConfigEntry[EnvertechCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EnvertechConfigEntry) -> bool:
    """Set up Envertech EVT Local from a config entry."""
    coordinator = EnvertechCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: EnvertechConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: EnvertechCoordinator = entry.runtime_data
        await coordinator.async_shutdown()
    return unload_ok
