"""Sensor platform for Envertech EVT Local."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
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
from homeassistant.helpers.event import async_track_time_change
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

    # Daily sensors (auto-reset at midnight, no manual helper needed)
    entities.append(EnvertechDailyEnergySensor(coordinator, entry))
    entities.append(EnvertechDailyEarningsSensor(coordinator, entry))

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
        self.entity_id = (
            f"sensor.envertech_input_port_{channel_idx + 1}_{description.key}"
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
        self.entity_id = f"sensor.envertech_{description.key}"
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
        self.entity_id = "sensor.envertech_earnings"
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


class EnvertechDailyEnergySensor(
    CoordinatorEntity[EnvertechCoordinator], RestoreSensor
):
    """Sensor for energy produced today. Resets automatically at midnight.

    On HA restart mid-day the baseline is reconstructed from the last
    persisted daily value so the counter continues correctly.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "daily_energy"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:weather-sunny"
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: EnvertechCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._midnight_baseline: float | None = None
        self._attr_unique_id = f"{coordinator.serial_hex}_daily_energy"
        self.entity_id = "sensor.envertech_daily_energy"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial_hex)},
            name=f"Envertech {coordinator.serial_hex}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_added_to_hass(self) -> None:
        """Restore baseline on HA restart and register midnight reset."""
        await super().async_added_to_hass()

        if (last_data := await self.async_get_last_sensor_data()) is not None:
            try:
                last_daily = float(last_data.native_value)  # type: ignore[arg-type]
                if self.coordinator.data is not None:
                    self._midnight_baseline = (
                        self.coordinator.data.total_energy - last_daily
                    )
            except (TypeError, ValueError):
                pass

        if self._midnight_baseline is None and self.coordinator.data is not None:
            self._midnight_baseline = self.coordinator.data.total_energy

        async_track_time_change(
            self.hass, self._async_midnight_reset, hour=0, minute=0, second=0
        )

    async def _async_midnight_reset(self, _now: Any) -> None:
        """Set new baseline at midnight."""
        if self.coordinator.data is not None:
            self._midnight_baseline = self.coordinator.data.total_energy
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return kWh produced since midnight."""
        if self.coordinator.data is None or self._midnight_baseline is None:
            return 0.0
        return round(
            max(0.0, self.coordinator.data.total_energy - self._midnight_baseline), 3
        )


class EnvertechDailyEarningsSensor(
    CoordinatorEntity[EnvertechCoordinator], RestoreSensor
):
    """Sensor for earnings today (EUR). Resets automatically at midnight."""

    _attr_has_entity_name = True
    _attr_translation_key = "daily_earnings"
    _attr_native_unit_of_measurement = "EUR"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash-plus"
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: EnvertechCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._midnight_baseline: float | None = None
        self._attr_unique_id = f"{coordinator.serial_hex}_daily_earnings"
        self.entity_id = "sensor.envertech_daily_earnings"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial_hex)},
            name=f"Envertech {coordinator.serial_hex}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    def _price(self) -> float:
        return float(
            self._entry.options.get(CONF_PRICE_PER_KWH, DEFAULT_PRICE_PER_KWH)
        )

    async def async_added_to_hass(self) -> None:
        """Restore baseline on HA restart and register midnight reset."""
        await super().async_added_to_hass()

        if (last_data := await self.async_get_last_sensor_data()) is not None:
            try:
                last_earnings = float(last_data.native_value)  # type: ignore[arg-type]
                price = self._price()
                if self.coordinator.data is not None and price > 0:
                    last_daily_kwh = last_earnings / price
                    self._midnight_baseline = (
                        self.coordinator.data.total_energy - last_daily_kwh
                    )
            except (TypeError, ValueError, ZeroDivisionError):
                pass

        if self._midnight_baseline is None and self.coordinator.data is not None:
            self._midnight_baseline = self.coordinator.data.total_energy

        async_track_time_change(
            self.hass, self._async_midnight_reset, hour=0, minute=0, second=0
        )

    async def _async_midnight_reset(self, _now: Any) -> None:
        """Set new baseline at midnight."""
        if self.coordinator.data is not None:
            self._midnight_baseline = self.coordinator.data.total_energy
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return earnings since midnight in EUR."""
        if self.coordinator.data is None or self._midnight_baseline is None:
            return 0.0
        daily_kwh = max(
            0.0, self.coordinator.data.total_energy - self._midnight_baseline
        )
        return round(daily_kwh * self._price(), 2)

