"""Tests for the WLED number platform."""
import json
from unittest.mock import MagicMock

import pytest
from wled import Device as WLEDDevice, WLEDConnectionError, WLEDError

from homeassistant.components.number import ATTR_MAX, ATTR_MIN, DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number.const import (
    ATTR_STEP,
    ATTR_VALUE,
    SERVICE_SET_VALUE,
)
from homeassistant.components.wled.const import SCAN_INTERVAL
from homeassistant.const import ATTR_ENTITY_ID, ATTR_ICON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util

from tests.common import MockConfigEntry, async_fire_time_changed, load_fixture


async def test_speed_state(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the creation and values of the WLED numbers."""
    entity_registry = er.async_get(hass)

    # First segment of the strip
    state = hass.states.get("number.wled_rgb_light_segment_1_speed")
    assert state
    assert state.attributes.get(ATTR_ICON) == "mdi:speedometer"
    assert state.attributes.get(ATTR_MAX) == 255
    assert state.attributes.get(ATTR_MIN) == 0
    assert state.attributes.get(ATTR_STEP) == 1
    assert state.state == "16"

    entry = entity_registry.async_get("number.wled_rgb_light_segment_1_speed")
    assert entry
    assert entry.unique_id == "aabbccddeeff_speed_1"


async def test_speed_segment_change_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_wled: MagicMock,
) -> None:
    """Test the value change of the WLED segments."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.wled_rgb_light_segment_1_speed",
            ATTR_VALUE: 42,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert mock_wled.segment.call_count == 1
    mock_wled.segment.assert_called_with(
        segment_id=1,
        speed=42,
    )


@pytest.mark.parametrize("mock_wled", ["wled/rgb_single_segment.json"], indirect=True)
async def test_speed_dynamically_handle_segments(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_wled: MagicMock,
) -> None:
    """Test if a new/deleted segment is dynamically added/removed."""
    segment0 = hass.states.get("number.wled_rgb_light_speed")
    segment1 = hass.states.get("number.wled_rgb_light_segment_1_speed")
    assert segment0
    assert segment0.state == "32"
    assert not segment1

    # Test adding a segment dynamically...
    return_value = mock_wled.update.return_value
    mock_wled.update.return_value = WLEDDevice(
        json.loads(load_fixture("wled/rgb.json"))
    )

    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    segment0 = hass.states.get("number.wled_rgb_light_speed")
    segment1 = hass.states.get("number.wled_rgb_light_segment_1_speed")
    assert segment0
    assert segment0.state == "32"
    assert segment1
    assert segment1.state == "16"

    # Test remove segment again...
    mock_wled.update.return_value = return_value
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    segment0 = hass.states.get("number.wled_rgb_light_speed")
    segment1 = hass.states.get("number.wled_rgb_light_segment_1_speed")
    assert segment0
    assert segment0.state == "32"
    assert segment1
    assert segment1.state == STATE_UNAVAILABLE


async def test_speed_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_wled: MagicMock,
) -> None:
    """Test error handling of the WLED numbers."""
    mock_wled.segment.side_effect = WLEDError

    with pytest.raises(HomeAssistantError, match="Invalid response from WLED API"):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.wled_rgb_light_segment_1_speed",
                ATTR_VALUE: 42,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("number.wled_rgb_light_segment_1_speed")
    assert state
    assert state.state == "16"
    assert mock_wled.segment.call_count == 1
    mock_wled.segment.assert_called_with(segment_id=1, speed=42)


async def test_speed_connection_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_wled: MagicMock,
) -> None:
    """Test error handling of the WLED numbers."""
    mock_wled.segment.side_effect = WLEDConnectionError

    with pytest.raises(HomeAssistantError, match="Error communicating with WLED API"):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.wled_rgb_light_segment_1_speed",
                ATTR_VALUE: 42,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("number.wled_rgb_light_segment_1_speed")
    assert state
    assert state.state == STATE_UNAVAILABLE
    assert mock_wled.segment.call_count == 1
    mock_wled.segment.assert_called_with(segment_id=1, speed=42)


async def test_intensity_state(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the creation and values of the WLED numbers."""
    entity_registry = er.async_get(hass)

    # First segment of the strip
    state = hass.states.get("number.wled_rgb_light_segment_1_intensity")
    assert state
    assert state.attributes.get(ATTR_ICON) is None
    assert state.attributes.get(ATTR_MAX) == 255
    assert state.attributes.get(ATTR_MIN) == 0
    assert state.attributes.get(ATTR_STEP) == 1
    assert state.state == "64"

    entry = entity_registry.async_get("number.wled_rgb_light_segment_1_intensity")
    assert entry
    assert entry.unique_id == "aabbccddeeff_intensity_1"


async def test_intensity_segment_change_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_wled: MagicMock,
) -> None:
    """Test the value change of the WLED segments."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.wled_rgb_light_segment_1_intensity",
            ATTR_VALUE: 128,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert mock_wled.segment.call_count == 1
    mock_wled.segment.assert_called_with(
        segment_id=1,
        intensity=128,
    )


@pytest.mark.parametrize("mock_wled", ["wled/rgb_single_segment.json"], indirect=True)
async def test_intensity_dynamically_handle_segments(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_wled: MagicMock,
) -> None:
    """Test if a new/deleted segment is dynamically added/removed."""
    segment0 = hass.states.get("number.wled_rgb_light_intensity")
    segment1 = hass.states.get("number.wled_rgb_light_segment_1_intensity")
    assert segment0
    assert segment0.state == "128"
    assert not segment1

    # Test adding a segment dynamically...
    return_value = mock_wled.update.return_value
    mock_wled.update.return_value = WLEDDevice(
        json.loads(load_fixture("wled/rgb.json"))
    )

    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    segment0 = hass.states.get("number.wled_rgb_light_intensity")
    segment1 = hass.states.get("number.wled_rgb_light_segment_1_intensity")
    assert segment0
    assert segment0.state == "128"
    assert segment1
    assert segment1.state == "64"

    # Test remove segment again...
    mock_wled.update.return_value = return_value
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL)
    await hass.async_block_till_done()

    segment0 = hass.states.get("number.wled_rgb_light_intensity")
    segment1 = hass.states.get("number.wled_rgb_light_segment_1_intensity")
    assert segment0
    assert segment0.state == "128"
    assert segment1
    assert segment1.state == STATE_UNAVAILABLE


async def test_intensity_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_wled: MagicMock,
) -> None:
    """Test error handling of the WLED numbers."""
    mock_wled.segment.side_effect = WLEDError

    with pytest.raises(HomeAssistantError, match="Invalid response from WLED API"):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.wled_rgb_light_segment_1_intensity",
                ATTR_VALUE: 21,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("number.wled_rgb_light_segment_1_intensity")
    assert state
    assert state.state == "64"
    assert mock_wled.segment.call_count == 1
    mock_wled.segment.assert_called_with(segment_id=1, intensity=21)


async def test_intensity_connection_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_wled: MagicMock,
) -> None:
    """Test error handling of the WLED numbers."""
    mock_wled.segment.side_effect = WLEDConnectionError

    with pytest.raises(HomeAssistantError, match="Error communicating with WLED API"):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.wled_rgb_light_segment_1_intensity",
                ATTR_VALUE: 128,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("number.wled_rgb_light_segment_1_intensity")
    assert state
    assert state.state == STATE_UNAVAILABLE
    assert mock_wled.segment.call_count == 1
    mock_wled.segment.assert_called_with(segment_id=1, intensity=128)
