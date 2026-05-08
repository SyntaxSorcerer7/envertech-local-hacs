"""Select platform for Envertech EVT Local power limit control."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EnvertechConfigEntry
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import EnvertechCoordinator
from .protocol import WATT_CODES_2000

_LOGGER = logging.getLogger(__name__)

POWER_LIMIT_OPTIONS = sorted(WATT_CODES_2000.keys())
POWER_LIMIT_OPTIONS_STR = [f"{w}W" for w in POWER_LIMIT_OPTIONS]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnvertechConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Envertech power limit select."""
    coordinator = entry.runtime_data
    async_add_entities([EnvertechPowerLimitSelect(coordinator)])


class EnvertechPowerLimitSelect(
    CoordinatorEntity[EnvertechCoordinator], SelectEntity
):
    """Select entity for inverter power limit."""

    _attr_has_entity_name = True
    _attr_translation_key = "power_limit"
    _attr_icon = "mdi:flash"

    def __init__(self, coordinator: EnvertechCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial_hex}_power_limit"
        self._attr_options = POWER_LIMIT_OPTIONS_STR
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial_hex)},
            name=f"Envertech {coordinator.serial_hex}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def current_option(self) -> str | None:
        """Return the current power limit."""
        if self.coordinator.power_limit is not None:
            return f"{self.coordinator.power_limit}W"
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the power limit."""
        watts = int(option.rstrip("W"))
        success = await self.coordinator.async_set_power_limit(watts)
        if success:
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set power limit to %s", option)

    async def async_added_to_hass(self) -> None:
        """Read current power limit when added."""
        await super().async_added_to_hass()
        await self.coordinator.async_read_power_limit()
        self.async_write_ha_state()
