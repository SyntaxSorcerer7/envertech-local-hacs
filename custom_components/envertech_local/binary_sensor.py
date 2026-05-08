"""Binary sensor platform for Envertech EVT Local."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EnvertechConfigEntry
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import EnvertechCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnvertechConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Envertech binary sensors."""
    async_add_entities([EnvertechOnlineSensor(entry.runtime_data)])


class EnvertechOnlineSensor(
    CoordinatorEntity[EnvertechCoordinator], BinarySensorEntity
):
    """Binary sensor indicating whether the inverter is reachable."""

    _attr_has_entity_name = True
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: EnvertechCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial_hex}_online"
        self.entity_id = "binary_sensor.envertech_online"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial_hex)},
            name=f"Envertech {coordinator.serial_hex}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def is_on(self) -> bool:
        """Return True if the last coordinator update succeeded."""
        return self.coordinator.last_update_success
