"""This platform provides support for sensor data from RainMachine."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import TEMP_CELSIUS, VOLUME_CUBIC_METERS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.dt import utcnow

from . import RainMachineEntity
from .const import (
    DATA_CONTROLLER,
    DATA_COORDINATOR,
    DATA_PROVISION_SETTINGS,
    DATA_RESTRICTIONS_UNIVERSAL,
    DATA_ZONES,
    DOMAIN,
    RUN_STATE_MAP,
    RunStates,
)
from .model import (
    RainMachineDescriptionMixinApiCategory,
    RainMachineDescriptionMixinUid,
)

DEFAULT_ZONE_COMPLETION_TIME_WOBBLE_TOLERANCE = timedelta(seconds=5)

TYPE_FLOW_SENSOR_CLICK_M3 = "flow_sensor_clicks_cubic_meter"
TYPE_FLOW_SENSOR_CONSUMED_LITERS = "flow_sensor_consumed_liters"
TYPE_FLOW_SENSOR_START_INDEX = "flow_sensor_start_index"
TYPE_FLOW_SENSOR_WATERING_CLICKS = "flow_sensor_watering_clicks"
TYPE_FREEZE_TEMP = "freeze_protect_temp"
TYPE_ZONE_RUN_COMPLETION_TIME = "zone_run_completion_time"


@dataclass
class RainMachineSensorDescriptionApiCategory(
    SensorEntityDescription, RainMachineDescriptionMixinApiCategory
):
    """Describe a RainMachine sensor."""


@dataclass
class RainMachineSensorDescriptionUid(
    SensorEntityDescription, RainMachineDescriptionMixinUid
):
    """Describe a RainMachine sensor."""


SENSOR_DESCRIPTIONS = (
    RainMachineSensorDescriptionApiCategory(
        key=TYPE_FLOW_SENSOR_CLICK_M3,
        name="Flow Sensor Clicks per Cubic Meter",
        icon="mdi:water-pump",
        native_unit_of_measurement=f"clicks/{VOLUME_CUBIC_METERS}",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        api_category=DATA_PROVISION_SETTINGS,
    ),
    RainMachineSensorDescriptionApiCategory(
        key=TYPE_FLOW_SENSOR_CONSUMED_LITERS,
        name="Flow Sensor Consumed Liters",
        icon="mdi:water-pump",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="liter",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL_INCREASING,
        api_category=DATA_PROVISION_SETTINGS,
    ),
    RainMachineSensorDescriptionApiCategory(
        key=TYPE_FLOW_SENSOR_START_INDEX,
        name="Flow Sensor Start Index",
        icon="mdi:water-pump",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="index",
        entity_registry_enabled_default=False,
        api_category=DATA_PROVISION_SETTINGS,
    ),
    RainMachineSensorDescriptionApiCategory(
        key=TYPE_FLOW_SENSOR_WATERING_CLICKS,
        name="Flow Sensor Clicks",
        icon="mdi:water-pump",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="clicks",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        api_category=DATA_PROVISION_SETTINGS,
    ),
    RainMachineSensorDescriptionApiCategory(
        key=TYPE_FREEZE_TEMP,
        name="Freeze Protect Temperature",
        icon="mdi:thermometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=TEMP_CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        api_category=DATA_RESTRICTIONS_UNIVERSAL,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up RainMachine sensors based on a config entry."""
    controller = hass.data[DOMAIN][entry.entry_id][DATA_CONTROLLER]
    coordinators = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    @callback
    def async_get_sensor_by_api_category(api_category: str) -> partial:
        """Generate the appropriate sensor object for an API category."""
        if api_category == DATA_PROVISION_SETTINGS:
            return partial(
                ProvisionSettingsSensor,
                entry,
                coordinators[DATA_PROVISION_SETTINGS],
            )

        return partial(
            UniversalRestrictionsSensor,
            entry,
            coordinators[DATA_RESTRICTIONS_UNIVERSAL],
        )

    sensors = [
        async_get_sensor_by_api_category(description.api_category)(
            controller, description
        )
        for description in SENSOR_DESCRIPTIONS
    ]

    zone_coordinator = coordinators[DATA_ZONES]
    for uid, zone in zone_coordinator.data.items():
        sensors.append(
            ZoneTimeRemainingSensor(
                entry,
                zone_coordinator,
                controller,
                RainMachineSensorDescriptionUid(
                    key=f"{TYPE_ZONE_RUN_COMPLETION_TIME}_{uid}",
                    name=f"{zone['name']} Run Completion Time",
                    device_class=SensorDeviceClass.TIMESTAMP,
                    entity_category=EntityCategory.DIAGNOSTIC,
                    uid=uid,
                ),
            )
        )

    async_add_entities(sensors)


class ProvisionSettingsSensor(RainMachineEntity, SensorEntity):
    """Define a sensor that handles provisioning data."""

    @callback
    def update_from_latest_data(self) -> None:
        """Update the state."""
        if self.entity_description.key == TYPE_FLOW_SENSOR_CLICK_M3:
            self._attr_native_value = self.coordinator.data["system"].get(
                "flowSensorClicksPerCubicMeter"
            )
        elif self.entity_description.key == TYPE_FLOW_SENSOR_CONSUMED_LITERS:
            clicks = self.coordinator.data["system"].get("flowSensorWateringClicks")
            clicks_per_m3 = self.coordinator.data["system"].get(
                "flowSensorClicksPerCubicMeter"
            )

            if clicks and clicks_per_m3:
                self._attr_native_value = (clicks * 1000) / clicks_per_m3
            else:
                self._attr_native_value = None
        elif self.entity_description.key == TYPE_FLOW_SENSOR_START_INDEX:
            self._attr_native_value = self.coordinator.data["system"].get(
                "flowSensorStartIndex"
            )
        elif self.entity_description.key == TYPE_FLOW_SENSOR_WATERING_CLICKS:
            self._attr_native_value = self.coordinator.data["system"].get(
                "flowSensorWateringClicks"
            )


class UniversalRestrictionsSensor(RainMachineEntity, SensorEntity):
    """Define a sensor that handles universal restrictions data."""

    @callback
    def update_from_latest_data(self) -> None:
        """Update the state."""
        if self.entity_description.key == TYPE_FREEZE_TEMP:
            self._attr_native_value = self.coordinator.data["freezeProtectTemp"]


class ZoneTimeRemainingSensor(RainMachineEntity, SensorEntity):
    """Define a sensor that shows the amount of time remaining for a zone."""

    entity_description: RainMachineSensorDescriptionUid

    @callback
    def update_from_latest_data(self) -> None:
        """Update the state."""
        data = self.coordinator.data[self.entity_description.uid]
        now = utcnow()

        if RUN_STATE_MAP.get(data["state"]) != RunStates.RUNNING:
            # If the zone isn't actively running, return immediately:
            return

        new_timestamp = now + timedelta(seconds=data["remaining"])

        if self._attr_native_value:
            assert isinstance(self._attr_native_value, datetime)
            if (
                new_timestamp - self._attr_native_value
            ) < DEFAULT_ZONE_COMPLETION_TIME_WOBBLE_TOLERANCE:
                # If the deviation between the previous and new timestamps is less than
                # a "wobble tolerance," don't spam the state machine:
                return

        self._attr_native_value = new_timestamp
