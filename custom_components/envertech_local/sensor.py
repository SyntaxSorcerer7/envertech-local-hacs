"""Sensor platform for Envertech EVT Local."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EnvertechConfigEntry
from .const import CONF_PRICE_PER_KWH, DEFAULT_PRICE_PER_KWH, DOMAIN, MANUFACTURER, MODEL
from .coordinator import EnvertechCoordinator
from .protocol import LiveData, MicroinverterData


@dataclass(frozen=True, kw_only=True)
class EnvertechChannelSensorDescription(SensorEntityDescription):
    """Describes a per-channel sensor."""

    value_fn: Callable[[MicroinverterData], float | None]


@dataclass(frozen=True, kw_only=True)
class EnvertechTotalSensorDescription(SensorEntityDescription):
    """Describes a total/device-level sensor."""

    value_fn: Callable[[LiveData], float | int | str | None]


CHANNEL_SENSORS: tuple[EnvertechChannelSensorDescription, ...] = (
    EnvertechChannelSensorDescription(
        key="dc_voltage",
        translation_key="dc_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ch: ch.dc_voltage,
    ),
    EnvertechChannelSensorDescription(
        key="ac_power",
        translation_key="ac_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ch: ch.ac_power,
    ),
    EnvertechChannelSensorDescription(
        key="total_energy",
        translation_key="total_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda ch: ch.total_energy,
    ),
    EnvertechChannelSensorDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ch: ch.temperature,
    ),
    EnvertechChannelSensorDescription(
        key="ac_voltage",
        translation_key="ac_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ch: ch.ac_voltage,
    ),
    EnvertechChannelSensorDescription(
        key="frequency",
        translation_key="frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ch: ch.frequency,
    ),
)

TOTAL_SENSORS: tuple[EnvertechTotalSensorDescription, ...] = (
    EnvertechTotalSensorDescription(
        key="total_ac_power",
        translation_key="total_ac_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: round(data.total_ac_power, 1),
    ),
    EnvertechTotalSensorDescription(
        key="total_energy_all",
        translation_key="total_energy_all",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: round(data.total_energy, 2),
    ),
    EnvertechTotalSensorDescription(
        key="firmware",
        translation_key="firmware",
        value_fn=lambda data: f"{data.firmware_main}.{data.firmware_sub}",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnvertechConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Envertech sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    # Per-channel sensors (MI 0–3)
    if coordinator.data and coordinator.data.channels:
        for idx, channel in enumerate(coordinator.data.channels):
            for description in CHANNEL_SENSORS:
                entities.append(
                    EnvertechChannelSensor(coordinator, description, idx, channel.uid)
                )

    # Total/device-level sensors
    for description in TOTAL_SENSORS:
        entities.append(EnvertechTotalSensor(coordinator, description))

    # Earnings sensor (depends on price option)
    entities.append(EnvertechEarningsSensor(coordinator, entry))

    async_add_entities(entities)


class EnvertechChannelSensor(
    CoordinatorEntity[EnvertechCoordinator], SensorEntity
):
    """Sensor for a single micro-inverter channel."""

    entity_description: EnvertechChannelSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EnvertechCoordinator,
        description: EnvertechChannelSensorDescription,
        channel_idx: int,
        uid: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._channel_idx = channel_idx
        self._uid = uid
        self._attr_unique_id = (
            f"{coordinator.serial_hex}_mi{channel_idx}_{description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.serial_hex}_mi{channel_idx}")},
            name=f"envertech-input-port-{channel_idx + 1}",
            manufacturer=MANUFACTURER,
            model=MODEL,
            via_device=(DOMAIN, coordinator.serial_hex),
        )

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        if (
            self.coordinator.data is None
            or self._channel_idx >= len(self.coordinator.data.channels)
        ):
            return None
        channel = self.coordinator.data.channels[self._channel_idx]
        return self.entity_description.value_fn(channel)


class EnvertechTotalSensor(
    CoordinatorEntity[EnvertechCoordinator], SensorEntity
):
    """Sensor for device-level totals."""

    entity_description: EnvertechTotalSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EnvertechCoordinator,
        description: EnvertechTotalSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial_hex}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial_hex)},
            name=f"Envertech {coordinator.serial_hex}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def native_value(self) -> float | int | str | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class EnvertechEarningsSensor(
    CoordinatorEntity[EnvertechCoordinator], SensorEntity
):
    """Sensor for total earnings based on energy produced and price per kWh."""

    _attr_has_entity_name = True
    _attr_translation_key = "earnings"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:currency-eur"

    def __init__(
        self,
        coordinator: EnvertechCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the earnings sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{coordinator.serial_hex}_earnings"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial_hex)},
            name=f"Envertech {coordinator.serial_hex}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def native_value(self) -> float | None:
        """Return total earnings in EUR."""
        if self.coordinator.data is None:
            return None
        price = self._entry.options.get(CONF_PRICE_PER_KWH, DEFAULT_PRICE_PER_KWH)
        total_kwh = self.coordinator.data.total_energy
        return round(total_kwh * price, 2)

    @property
    def extra_state_attributes(self) -> dict[str, float]:
        """Return price per kWh used for calculation."""
        return {
            "price_per_kwh": self._entry.options.get(
                CONF_PRICE_PER_KWH, DEFAULT_PRICE_PER_KWH
            )
        }
