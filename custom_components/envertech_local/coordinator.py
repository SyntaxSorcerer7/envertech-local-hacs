"""Data update coordinator for Envertech EVT Local."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SERIAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .protocol import EnvertechConnection, LiveData

_LOGGER = logging.getLogger(__name__)


class EnvertechCoordinator(DataUpdateCoordinator[LiveData]):
    """Coordinator to manage fetching data from Envertech inverter."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.connection = EnvertechConnection(
            host=entry.data[CONF_HOST],
            serial=entry.data[CONF_SERIAL],
        )
        self._serial: int = entry.data[CONF_SERIAL]
        self._power_limit: int | None = None

    @property
    def serial_hex(self) -> str:
        """Return the serial number as hex string."""
        return f"{self._serial:08X}"

    @property
    def power_limit(self) -> int | None:
        """Return the last known power limit in watts."""
        return self._power_limit

    async def _async_update_data(self) -> LiveData:
        """Fetch live data from inverter."""
        try:
            return await self.connection.get_live_data()
        except ConnectionError as err:
            raise UpdateFailed(f"Error communicating with inverter: {err}") from err

    async def async_read_power_limit(self) -> int | None:
        """Read the current power limit."""
        result = await self.connection.get_power_limit()
        if result is not None:
            self._power_limit = result
        return self._power_limit

    async def async_set_power_limit(self, watts: int) -> bool:
        """Set a new power limit."""
        success = await self.connection.set_power_limit(watts)
        if success:
            self._power_limit = watts
        return success

    async def async_shutdown(self) -> None:
        """Disconnect on shutdown."""
        await self.connection.disconnect()
