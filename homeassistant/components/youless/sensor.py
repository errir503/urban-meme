"""The sensor entity for the Youless integration."""
from __future__ import annotations

from youless_api.youless_sensor import YoulessSensor

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    VOLUME_CUBIC_METERS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize the integration."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    device = entry.data[CONF_DEVICE]
    if (device := entry.data[CONF_DEVICE]) is None:
        device = entry.entry_id

    async_add_entities(
        [
            GasSensor(coordinator, device),
            EnergyMeterSensor(
                coordinator, device, "low", SensorStateClass.TOTAL_INCREASING
            ),
            EnergyMeterSensor(
                coordinator, device, "high", SensorStateClass.TOTAL_INCREASING
            ),
            EnergyMeterSensor(coordinator, device, "total", SensorStateClass.TOTAL),
            CurrentPowerSensor(coordinator, device),
            DeliveryMeterSensor(coordinator, device, "low"),
            DeliveryMeterSensor(coordinator, device, "high"),
            ExtraMeterSensor(coordinator, device, "total"),
            ExtraMeterPowerSensor(coordinator, device, "usage"),
        ]
    )


class YoulessBaseSensor(CoordinatorEntity, SensorEntity):
    """The base sensor for Youless."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device: str,
        device_group: str,
        friendly_name: str,
        sensor_id: str,
    ) -> None:
        """Create the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{device}_{sensor_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device}_{device_group}")},
            manufacturer="YouLess",
            model=self.coordinator.data.model,
            name=friendly_name,
        )

    @property
    def get_sensor(self) -> YoulessSensor | None:
        """Property to get the underlying sensor object."""
        return None

    @property
    def native_value(self) -> StateType:
        """Determine the state value, only if a sensor is initialized."""
        if self.get_sensor is None:
            return None

        return self.get_sensor.value

    @property
    def available(self) -> bool:
        """Return a flag to indicate the sensor not being available."""
        return super().available and self.get_sensor is not None


class GasSensor(YoulessBaseSensor):
    """The Youless gas sensor."""

    _attr_native_unit_of_measurement = VOLUME_CUBIC_METERS
    _attr_device_class = SensorDeviceClass.GAS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: DataUpdateCoordinator, device: str) -> None:
        """Instantiate a gas sensor."""
        super().__init__(coordinator, device, "gas", "Gas meter", "gas")
        self._attr_name = "Gas usage"
        self._attr_icon = "mdi:fire"

    @property
    def get_sensor(self) -> YoulessSensor | None:
        """Get the sensor for providing the value."""
        return self.coordinator.data.gas_meter


class CurrentPowerSensor(YoulessBaseSensor):
    """The current power usage sensor."""

    _attr_native_unit_of_measurement = POWER_WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DataUpdateCoordinator, device: str) -> None:
        """Instantiate the usage meter."""
        super().__init__(coordinator, device, "power", "Power usage", "usage")
        self._device = device
        self._attr_name = "Power Usage"

    @property
    def get_sensor(self) -> YoulessSensor | None:
        """Get the sensor for providing the value."""
        return self.coordinator.data.current_power_usage


class DeliveryMeterSensor(YoulessBaseSensor):
    """The Youless delivery meter value sensor."""

    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self, coordinator: DataUpdateCoordinator, device: str, dev_type: str
    ) -> None:
        """Instantiate a delivery meter sensor."""
        super().__init__(
            coordinator, device, "delivery", "Energy delivery", f"delivery_{dev_type}"
        )
        self._type = dev_type
        self._attr_name = f"Energy delivery {dev_type}"

    @property
    def get_sensor(self) -> YoulessSensor | None:
        """Get the sensor for providing the value."""
        if self.coordinator.data.delivery_meter is None:
            return None

        return getattr(self.coordinator.data.delivery_meter, f"_{self._type}", None)


class EnergyMeterSensor(YoulessBaseSensor):
    """The Youless low meter value sensor."""

    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device: str,
        dev_type: str,
        state_class: SensorStateClass,
    ) -> None:
        """Instantiate a energy meter sensor."""
        super().__init__(
            coordinator, device, "power", "Energy usage", f"power_{dev_type}"
        )
        self._device = device
        self._type = dev_type
        self._attr_name = f"Energy {dev_type}"
        self._attr_state_class = state_class

    @property
    def get_sensor(self) -> YoulessSensor | None:
        """Get the sensor for providing the value."""
        if self.coordinator.data.power_meter is None:
            return None

        return getattr(self.coordinator.data.power_meter, f"_{self._type}", None)


class ExtraMeterSensor(YoulessBaseSensor):
    """The Youless extra meter value sensor (s0)."""

    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self, coordinator: DataUpdateCoordinator, device: str, dev_type: str
    ) -> None:
        """Instantiate an extra meter sensor."""
        super().__init__(
            coordinator, device, "extra", "Extra meter", f"extra_{dev_type}"
        )
        self._type = dev_type
        self._attr_name = f"Extra {dev_type}"

    @property
    def get_sensor(self) -> YoulessSensor | None:
        """Get the sensor for providing the value."""
        if self.coordinator.data.extra_meter is None:
            return None

        return getattr(self.coordinator.data.extra_meter, f"_{self._type}", None)


class ExtraMeterPowerSensor(YoulessBaseSensor):
    """The Youless extra meter power value sensor (s0)."""

    _attr_native_unit_of_measurement = POWER_WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: DataUpdateCoordinator, device: str, dev_type: str
    ) -> None:
        """Instantiate an extra meter power sensor."""
        super().__init__(
            coordinator, device, "extra", "Extra meter", f"extra_{dev_type}"
        )
        self._type = dev_type
        self._attr_name = f"Extra {dev_type}"

    @property
    def get_sensor(self) -> YoulessSensor | None:
        """Get the sensor for providing the value."""
        if self.coordinator.data.extra_meter is None:
            return None

        return getattr(self.coordinator.data.extra_meter, f"_{self._type}", None)
