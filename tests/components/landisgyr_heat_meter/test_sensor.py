"""The tests for the Landis+Gyr Heat Meter sensor platform."""
from dataclasses import dataclass
import datetime
from unittest.mock import patch

import serial

from homeassistant.components.homeassistant import DOMAIN as HA_DOMAIN
from homeassistant.components.landisgyr_heat_meter.const import DOMAIN, POLLING_INTERVAL
from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ICON,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from tests.common import MockConfigEntry, async_fire_time_changed

API_HEAT_METER_SERVICE = (
    "homeassistant.components.landisgyr_heat_meter.ultraheat_api.HeatMeterService"
)


@dataclass
class MockHeatMeterResponse:
    """Mock for HeatMeterResponse."""

    heat_usage_gj: float
    volume_usage_m3: float
    heat_previous_year_gj: float
    device_number: str
    meter_date_time: datetime.datetime


@patch(API_HEAT_METER_SERVICE)
async def test_create_sensors(
    mock_heat_meter, hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test sensor."""
    entry_data = {
        "device": "/dev/USB0",
        "model": "LUGCUH50",
        "device_number": "123456789",
    }
    mock_entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=entry_data)

    mock_entry.add_to_hass(hass)

    mock_heat_meter_response = MockHeatMeterResponse(
        heat_usage_gj=123.0,
        volume_usage_m3=456.0,
        heat_previous_year_gj=111.0,
        device_number="devicenr_789",
        meter_date_time=dt_util.as_utc(datetime.datetime(2022, 5, 19, 19, 41, 17)),
    )

    mock_heat_meter().read.return_value = mock_heat_meter_response

    await hass.config_entries.async_setup(mock_entry.entry_id)
    await async_setup_component(hass, HA_DOMAIN, {})
    await hass.async_block_till_done()

    # check if 26 attributes have been created
    assert len(hass.states.async_all()) == 25

    state = hass.states.get("sensor.heat_meter_heat_usage_gj")
    assert state
    assert state.state == "123.0"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfEnergy.GIGA_JOULE
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.TOTAL
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENERGY

    state = hass.states.get("sensor.heat_meter_volume_usage")
    assert state
    assert state.state == "456.0"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfVolume.CUBIC_METERS
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.TOTAL

    state = hass.states.get("sensor.heat_meter_device_number")
    assert state
    assert state.state == "devicenr_789"
    assert state.attributes.get(ATTR_STATE_CLASS) is None
    entity_registry_entry = entity_registry.async_get("sensor.heat_meter_device_number")
    assert entity_registry_entry.entity_category == EntityCategory.DIAGNOSTIC

    state = hass.states.get("sensor.heat_meter_meter_date_time")
    assert state
    assert state.attributes.get(ATTR_ICON) == "mdi:clock-outline"
    assert state.attributes.get(ATTR_STATE_CLASS) is None
    entity_registry_entry = entity_registry.async_get(
        "sensor.heat_meter_meter_date_time"
    )
    assert entity_registry_entry.entity_category == EntityCategory.DIAGNOSTIC


@patch(API_HEAT_METER_SERVICE)
async def test_exception_on_polling(mock_heat_meter, hass: HomeAssistant) -> None:
    """Test sensor."""
    entry_data = {
        "device": "/dev/USB0",
        "model": "LUGCUH50",
        "device_number": "123456789",
    }
    mock_entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=entry_data)
    mock_entry.add_to_hass(hass)

    # First setup normally
    mock_heat_meter_response = MockHeatMeterResponse(
        heat_usage_gj=123.0,
        volume_usage_m3=456.0,
        heat_previous_year_gj=111.0,
        device_number="devicenr_789",
        meter_date_time=dt_util.as_utc(datetime.datetime(2022, 5, 19, 19, 41, 17)),
    )

    mock_heat_meter().read.return_value = mock_heat_meter_response

    await hass.config_entries.async_setup(mock_entry.entry_id)
    await async_setup_component(hass, HA_DOMAIN, {})
    await hass.async_block_till_done()

    # check if initial setup succeeded
    state = hass.states.get("sensor.heat_meter_heat_usage_gj")
    assert state
    assert state.state == "123.0"

    # Now 'disable' the connection and wait for polling and see if it fails
    mock_heat_meter().read.side_effect = serial.serialutil.SerialException
    async_fire_time_changed(hass, dt_util.utcnow() + POLLING_INTERVAL)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.heat_meter_heat_usage_gj")
    assert state.state == STATE_UNAVAILABLE

    # Now 'enable' and see if next poll succeeds
    mock_heat_meter_response = MockHeatMeterResponse(
        heat_usage_gj=124.0,
        volume_usage_m3=457.0,
        heat_previous_year_gj=112.0,
        device_number="devicenr_789",
        meter_date_time=dt_util.as_utc(datetime.datetime(2022, 5, 19, 20, 41, 17)),
    )

    mock_heat_meter().read.return_value = mock_heat_meter_response
    mock_heat_meter().read.side_effect = None
    async_fire_time_changed(hass, dt_util.utcnow() + POLLING_INTERVAL)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.heat_meter_heat_usage_gj")
    assert state
    assert state.state == "124.0"
