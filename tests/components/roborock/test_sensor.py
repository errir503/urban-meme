"""Test Roborock Sensors."""

from roborock.const import (
    FILTER_REPLACE_TIME,
    MAIN_BRUSH_REPLACE_TIME,
    SENSOR_DIRTY_REPLACE_TIME,
    SIDE_BRUSH_REPLACE_TIME,
)

from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


async def test_sensors(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test sensors and check test values are correctly set."""
    assert len(hass.states.async_all("sensor")) == 28
    assert hass.states.get("sensor.roborock_s7_maxv_main_brush_time_left").state == str(
        MAIN_BRUSH_REPLACE_TIME - 74382
    )
    assert hass.states.get("sensor.roborock_s7_maxv_side_brush_time_left").state == str(
        SIDE_BRUSH_REPLACE_TIME - 74382
    )
    assert hass.states.get("sensor.roborock_s7_maxv_filter_time_left").state == str(
        FILTER_REPLACE_TIME - 74382
    )
    assert hass.states.get("sensor.roborock_s7_maxv_sensor_time_left").state == str(
        SENSOR_DIRTY_REPLACE_TIME - 74382
    )
    assert hass.states.get("sensor.roborock_s7_maxv_cleaning_time").state == "1176"
    assert (
        hass.states.get("sensor.roborock_s7_maxv_total_cleaning_time").state == "74382"
    )
    assert hass.states.get("sensor.roborock_s7_maxv_status").state == "charging"
    assert (
        hass.states.get("sensor.roborock_s7_maxv_total_cleaning_area").state == "1159.2"
    )
    assert hass.states.get("sensor.roborock_s7_maxv_cleaning_area").state == "21.0"
    assert hass.states.get("sensor.roborock_s7_maxv_vacuum_error").state == "none"
    assert hass.states.get("sensor.roborock_s7_maxv_battery").state == "100"
    assert hass.states.get("sensor.roborock_s7_maxv_dock_error").state == "ok"
    assert (
        hass.states.get("sensor.roborock_s7_maxv_last_clean_begin").state
        == "2023-01-01T03:22:10+00:00"
    )
    assert (
        hass.states.get("sensor.roborock_s7_maxv_last_clean_end").state
        == "2023-01-01T03:43:58+00:00"
    )
