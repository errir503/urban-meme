"""Support for deCONZ sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from pydeconz.interfaces.sensors import SensorResources
from pydeconz.models.event import EventType
from pydeconz.models.sensor import SensorBase as PydeconzSensorBase
from pydeconz.models.sensor.air_quality import AirQuality
from pydeconz.models.sensor.consumption import Consumption
from pydeconz.models.sensor.daylight import DAYLIGHT_STATUS, Daylight
from pydeconz.models.sensor.generic_status import GenericStatus
from pydeconz.models.sensor.humidity import Humidity
from pydeconz.models.sensor.light_level import LightLevel
from pydeconz.models.sensor.power import Power
from pydeconz.models.sensor.pressure import Pressure
from pydeconz.models.sensor.switch import Switch
from pydeconz.models.sensor.temperature import Temperature
from pydeconz.models.sensor.time import Time

from homeassistant.components.sensor import (
    DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    ATTR_VOLTAGE,
    ENERGY_KILO_WATT_HOUR,
    LIGHT_LUX,
    PERCENTAGE,
    POWER_WATT,
    PRESSURE_HPA,
    TEMP_CELSIUS,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.typing import StateType
import homeassistant.util.dt as dt_util

from .const import ATTR_DARK, ATTR_ON, DOMAIN as DECONZ_DOMAIN
from .deconz_device import DeconzDevice
from .gateway import DeconzGateway, get_gateway_from_config_entry

PROVIDES_EXTRA_ATTRIBUTES = (
    "battery",
    "consumption",
    "daylight_status",
    "humidity",
    "light_level",
    "power",
    "pressure",
    "status",
    "temperature",
)

ATTR_CURRENT = "current"
ATTR_POWER = "power"
ATTR_DAYLIGHT = "daylight"
ATTR_EVENT_ID = "event_id"


T = TypeVar(
    "T",
    AirQuality,
    Consumption,
    Daylight,
    GenericStatus,
    Humidity,
    LightLevel,
    Power,
    Pressure,
    Temperature,
    Time,
    PydeconzSensorBase,
)


@dataclass
class DeconzSensorDescriptionMixin(Generic[T]):
    """Required values when describing secondary sensor attributes."""

    update_key: str
    value_fn: Callable[[T], datetime | StateType]


@dataclass
class DeconzSensorDescription(SensorEntityDescription, DeconzSensorDescriptionMixin[T]):
    """Class describing deCONZ binary sensor entities."""

    instance_check: type[T] | None = None
    name_suffix: str = ""
    old_unique_id_suffix: str = ""


ENTITY_DESCRIPTIONS: tuple[DeconzSensorDescription, ...] = (
    DeconzSensorDescription[AirQuality](
        key="air_quality",
        update_key="airquality",
        value_fn=lambda device: device.air_quality,
        instance_check=AirQuality,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    DeconzSensorDescription[AirQuality](
        key="air_quality_ppb",
        update_key="airqualityppb",
        value_fn=lambda device: device.air_quality_ppb,
        instance_check=AirQuality,
        name_suffix="PPB",
        old_unique_id_suffix="ppb",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    DeconzSensorDescription[Consumption](
        key="consumption",
        update_key="consumption",
        value_fn=lambda device: device.scaled_consumption,
        instance_check=Consumption,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
    ),
    DeconzSensorDescription[Daylight](
        key="daylight_status",
        update_key="status",
        value_fn=lambda device: DAYLIGHT_STATUS[device.daylight_status],
        instance_check=Daylight,
        icon="mdi:white-balance-sunny",
        entity_registry_enabled_default=False,
    ),
    DeconzSensorDescription[GenericStatus](
        key="status",
        update_key="status",
        value_fn=lambda device: device.status,
        instance_check=GenericStatus,
    ),
    DeconzSensorDescription[Humidity](
        key="humidity",
        update_key="humidity",
        value_fn=lambda device: device.scaled_humidity,
        instance_check=Humidity,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    DeconzSensorDescription[LightLevel](
        key="light_level",
        update_key="lightlevel",
        value_fn=lambda device: device.scaled_light_level,
        instance_check=LightLevel,
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=LIGHT_LUX,
    ),
    DeconzSensorDescription[Power](
        key="power",
        update_key="power",
        value_fn=lambda device: device.power,
        instance_check=Power,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=POWER_WATT,
    ),
    DeconzSensorDescription[Pressure](
        key="pressure",
        update_key="pressure",
        value_fn=lambda device: device.pressure,
        instance_check=Pressure,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PRESSURE_HPA,
    ),
    DeconzSensorDescription[Temperature](
        key="temperature",
        update_key="temperature",
        value_fn=lambda device: device.scaled_temperature,
        instance_check=Temperature,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=TEMP_CELSIUS,
    ),
    DeconzSensorDescription[Time](
        key="last_set",
        update_key="lastset",
        value_fn=lambda device: dt_util.parse_datetime(device.last_set),
        instance_check=Time,
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    DeconzSensorDescription[SensorResources](
        key="battery",
        update_key="battery",
        value_fn=lambda device: device.battery,
        name_suffix="Battery",
        old_unique_id_suffix="battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    DeconzSensorDescription[SensorResources](
        key="internal_temperature",
        update_key="temperature",
        value_fn=lambda device: device.internal_temperature,
        name_suffix="Temperature",
        old_unique_id_suffix="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=TEMP_CELSIUS,
    ),
)


@callback
def async_update_unique_id(
    hass: HomeAssistant, unique_id: str, description: DeconzSensorDescription
) -> None:
    """Update unique ID to always have a suffix.

    Introduced with release 2022.9.
    """
    ent_reg = er.async_get(hass)

    new_unique_id = f"{unique_id}-{description.key}"
    if ent_reg.async_get_entity_id(DOMAIN, DECONZ_DOMAIN, new_unique_id):
        return

    if description.old_unique_id_suffix:
        unique_id = f'{unique_id.split("-", 1)[0]}-{description.old_unique_id_suffix}'

    if entity_id := ent_reg.async_get_entity_id(DOMAIN, DECONZ_DOMAIN, unique_id):
        ent_reg.async_update_entity(entity_id, new_unique_id=new_unique_id)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the deCONZ sensors."""
    gateway = get_gateway_from_config_entry(hass, config_entry)
    gateway.entities[DOMAIN] = set()

    known_device_entities: dict[str, set[str]] = {
        description.key: set()
        for description in ENTITY_DESCRIPTIONS
        if description.instance_check is None
    }

    @callback
    def async_add_sensor(_: EventType, sensor_id: str) -> None:
        """Add sensor from deCONZ."""
        sensor = gateway.api.sensors[sensor_id]
        entities: list[DeconzSensor] = []

        for description in ENTITY_DESCRIPTIONS:
            if description.instance_check and not isinstance(
                sensor, description.instance_check
            ):
                continue

            no_sensor_data = False
            if description.value_fn(sensor) is None:
                no_sensor_data = True

            if description.instance_check is None:
                if (
                    sensor.type.startswith("CLIP")
                    or (no_sensor_data and description.key != "battery")
                    or (
                        (unique_id := sensor.unique_id.rsplit("-", 1)[0])
                        in known_device_entities[description.key]
                    )
                ):
                    continue
                known_device_entities[description.key].add(unique_id)
                if no_sensor_data and description.key == "battery":
                    async_update_unique_id(hass, sensor.unique_id, description)
                    DeconzBatteryTracker(
                        sensor_id, gateway, description, async_add_entities
                    )
                    continue

            if no_sensor_data:
                continue

            async_update_unique_id(hass, sensor.unique_id, description)
            entities.append(DeconzSensor(sensor, gateway, description))

        async_add_entities(entities)

    gateway.register_platform_add_device_callback(
        async_add_sensor,
        gateway.api.sensors,
    )


class DeconzSensor(DeconzDevice[SensorResources], SensorEntity):
    """Representation of a deCONZ sensor."""

    TYPE = DOMAIN
    entity_description: DeconzSensorDescription

    def __init__(
        self,
        device: SensorResources,
        gateway: DeconzGateway,
        description: DeconzSensorDescription,
    ) -> None:
        """Initialize deCONZ sensor."""
        self.entity_description = description
        self.unique_id_suffix = description.key
        self._update_key = description.update_key
        if description.name_suffix:
            self._name_suffix = description.name_suffix
        super().__init__(device, gateway)

        if (
            self.entity_description.key in PROVIDES_EXTRA_ATTRIBUTES
            and self._update_keys is not None
        ):
            self._update_keys.update({"on", "state"})

    @property
    def native_value(self) -> StateType | datetime:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self._device)

    @property
    def extra_state_attributes(self) -> dict[str, bool | float | int | str | None]:
        """Return the state attributes of the sensor."""
        attr: dict[str, bool | float | int | str | None] = {}

        if self.entity_description.key not in PROVIDES_EXTRA_ATTRIBUTES:
            return attr

        if self._device.on is not None:
            attr[ATTR_ON] = self._device.on

        if self._device.internal_temperature is not None:
            attr[ATTR_TEMPERATURE] = self._device.internal_temperature

        if isinstance(self._device, Consumption):
            attr[ATTR_POWER] = self._device.power

        elif isinstance(self._device, Daylight):
            attr[ATTR_DAYLIGHT] = self._device.daylight

        elif isinstance(self._device, LightLevel):

            if self._device.dark is not None:
                attr[ATTR_DARK] = self._device.dark

            if self._device.daylight is not None:
                attr[ATTR_DAYLIGHT] = self._device.daylight

        elif isinstance(self._device, Power):
            attr[ATTR_CURRENT] = self._device.current
            attr[ATTR_VOLTAGE] = self._device.voltage

        elif isinstance(self._device, Switch):
            for event in self.gateway.events:
                if self._device == event.device:
                    attr[ATTR_EVENT_ID] = event.event_id

        return attr


class DeconzBatteryTracker:
    """Track sensors without a battery state and add entity when battery state exist."""

    def __init__(
        self,
        sensor_id: str,
        gateway: DeconzGateway,
        description: DeconzSensorDescription,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        """Set up tracker."""
        self.sensor = gateway.api.sensors[sensor_id]
        self.gateway = gateway
        self.description = description
        self.async_add_entities = async_add_entities
        self.unsubscribe = self.sensor.subscribe(self.async_update_callback)

    @callback
    def async_update_callback(self) -> None:
        """Update the device's state."""
        if self.description.update_key in self.sensor.changed_keys:
            self.unsubscribe()
            self.async_add_entities(
                [DeconzSensor(self.sensor, self.gateway, self.description)]
            )
