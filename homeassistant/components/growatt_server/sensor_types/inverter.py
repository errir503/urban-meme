"""Growatt Sensor definitions for the Inverter type."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)

from .sensor_entity_description import GrowattSensorEntityDescription

INVERTER_SENSOR_TYPES: tuple[GrowattSensorEntityDescription, ...] = (
    GrowattSensorEntityDescription(
        key="inverter_energy_today",
        translation_key="inverter_energy_today",
        api_key="powerToday",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_energy_total",
        translation_key="inverter_energy_total",
        api_key="powerTotal",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        precision=1,
        state_class=SensorStateClass.TOTAL,
    ),
    GrowattSensorEntityDescription(
        key="inverter_voltage_input_1",
        translation_key="inverter_voltage_input_1",
        api_key="vpv1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=2,
    ),
    GrowattSensorEntityDescription(
        key="inverter_amperage_input_1",
        translation_key="inverter_amperage_input_1",
        api_key="ipv1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_wattage_input_1",
        translation_key="inverter_wattage_input_1",
        api_key="ppv1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_voltage_input_2",
        translation_key="inverter_voltage_input_2",
        api_key="vpv2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_amperage_input_2",
        translation_key="inverter_amperage_input_2",
        api_key="ipv2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_wattage_input_2",
        translation_key="inverter_wattage_input_2",
        api_key="ppv2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_voltage_input_3",
        translation_key="inverter_voltage_input_3",
        api_key="vpv3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_amperage_input_3",
        translation_key="inverter_amperage_input_3",
        api_key="ipv3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_wattage_input_3",
        translation_key="inverter_wattage_input_3",
        api_key="ppv3",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_internal_wattage",
        translation_key="inverter_internal_wattage",
        api_key="ppv",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_reactive_voltage",
        translation_key="inverter_reactive_voltage",
        api_key="vacr",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_inverter_reactive_amperage",
        translation_key="inverter_reactive_amperage",
        api_key="iacr",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_frequency",
        translation_key="inverter_frequency",
        api_key="fac",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_current_wattage",
        translation_key="inverter_current_wattage",
        api_key="pac",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_current_reactive_wattage",
        translation_key="inverter_current_reactive_wattage",
        api_key="pacr",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_ipm_temperature",
        translation_key="inverter_ipm_temperature",
        api_key="ipmTemperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    GrowattSensorEntityDescription(
        key="inverter_temperature",
        translation_key="inverter_energy_today",
        api_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
)
