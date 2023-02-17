"""Tests for rainbird sensor platform."""


import pytest

from homeassistant.components.rainbird import DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant

from .conftest import (
    ACK_ECHO,
    EMPTY_STATIONS_RESPONSE,
    HOST,
    PASSWORD,
    RAIN_DELAY_OFF,
    RAIN_SENSOR_OFF,
    SERIAL_RESPONSE,
    ZONE_3_ON_RESPONSE,
    ZONE_5_ON_RESPONSE,
    ZONE_OFF_RESPONSE,
    ComponentSetup,
    mock_response,
)

from tests.components.switch import common as switch_common
from tests.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse


@pytest.fixture
def platforms() -> list[str]:
    """Fixture to specify platforms to test."""
    return [Platform.SWITCH]


@pytest.mark.parametrize(
    "stations_response",
    [EMPTY_STATIONS_RESPONSE],
)
async def test_no_zones(
    hass: HomeAssistant,
    setup_integration: ComponentSetup,
) -> None:
    """Test case where listing stations returns no stations."""

    assert await setup_integration()

    zone = hass.states.get("switch.rain_bird_sprinkler_1")
    assert zone is None


@pytest.mark.parametrize(
    "zone_state_response",
    [ZONE_5_ON_RESPONSE],
)
async def test_zones(
    hass: HomeAssistant,
    setup_integration: ComponentSetup,
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Test switch platform with fake data that creates 7 zones with one enabled."""

    assert await setup_integration()

    zone = hass.states.get("switch.rain_bird_sprinkler_1")
    assert zone is not None
    assert zone.state == "off"
    assert zone.attributes == {
        "friendly_name": "Rain Bird Sprinkler 1",
        "zone": 1,
    }

    zone = hass.states.get("switch.rain_bird_sprinkler_2")
    assert zone is not None
    assert zone.state == "off"
    assert zone.attributes == {
        "friendly_name": "Rain Bird Sprinkler 2",
        "zone": 2,
    }

    zone = hass.states.get("switch.rain_bird_sprinkler_3")
    assert zone is not None
    assert zone.state == "off"

    zone = hass.states.get("switch.rain_bird_sprinkler_4")
    assert zone is not None
    assert zone.state == "off"

    zone = hass.states.get("switch.rain_bird_sprinkler_5")
    assert zone is not None
    assert zone.state == "on"

    zone = hass.states.get("switch.rain_bird_sprinkler_6")
    assert zone is not None
    assert zone.state == "off"

    zone = hass.states.get("switch.rain_bird_sprinkler_7")
    assert zone is not None
    assert zone.state == "off"

    assert not hass.states.get("switch.rain_bird_sprinkler_8")


async def test_switch_on(
    hass: HomeAssistant,
    setup_integration: ComponentSetup,
    aioclient_mock: AiohttpClientMocker,
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Test turning on irrigation switch."""

    assert await setup_integration()

    # Initially all zones are off. Pick zone3 as an arbitrary to assert
    # state, then update below as a switch.
    zone = hass.states.get("switch.rain_bird_sprinkler_3")
    assert zone is not None
    assert zone.state == "off"

    aioclient_mock.mock_calls.clear()
    responses.extend(
        [
            mock_response(ACK_ECHO),  # Switch on response
            # API responses when state is refreshed
            mock_response(ZONE_3_ON_RESPONSE),
            mock_response(RAIN_SENSOR_OFF),
            mock_response(RAIN_DELAY_OFF),
        ]
    )
    await switch_common.async_turn_on(hass, "switch.rain_bird_sprinkler_3")
    await hass.async_block_till_done()

    # Verify switch state is updated
    zone = hass.states.get("switch.rain_bird_sprinkler_3")
    assert zone is not None
    assert zone.state == "on"


@pytest.mark.parametrize(
    "zone_state_response",
    [ZONE_3_ON_RESPONSE],
)
async def test_switch_off(
    hass: HomeAssistant,
    setup_integration: ComponentSetup,
    aioclient_mock: AiohttpClientMocker,
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Test turning off irrigation switch."""

    assert await setup_integration()

    # Initially the test zone is on
    zone = hass.states.get("switch.rain_bird_sprinkler_3")
    assert zone is not None
    assert zone.state == "on"

    aioclient_mock.mock_calls.clear()
    responses.extend(
        [
            mock_response(ACK_ECHO),  # Switch off response
            mock_response(ZONE_OFF_RESPONSE),  # Updated zone state
            mock_response(RAIN_SENSOR_OFF),
            mock_response(RAIN_DELAY_OFF),
        ]
    )
    await switch_common.async_turn_off(hass, "switch.rain_bird_sprinkler_3")
    await hass.async_block_till_done()

    # Verify switch state is updated
    zone = hass.states.get("switch.rain_bird_sprinkler_3")
    assert zone is not None
    assert zone.state == "off"


async def test_irrigation_service(
    hass: HomeAssistant,
    setup_integration: ComponentSetup,
    aioclient_mock: AiohttpClientMocker,
    responses: list[AiohttpClientMockResponse],
    api_responses: list[str],
) -> None:
    """Test calling the irrigation service."""

    assert await setup_integration()

    zone = hass.states.get("switch.rain_bird_sprinkler_3")
    assert zone is not None
    assert zone.state == "off"

    aioclient_mock.mock_calls.clear()
    responses.extend(
        [
            mock_response(ACK_ECHO),
            # API responses when state is refreshed
            mock_response(ZONE_3_ON_RESPONSE),
            mock_response(RAIN_SENSOR_OFF),
            mock_response(RAIN_DELAY_OFF),
        ]
    )

    await hass.services.async_call(
        DOMAIN,
        "start_irrigation",
        {ATTR_ENTITY_ID: "switch.rain_bird_sprinkler_3", "duration": 30},
        blocking=True,
    )

    zone = hass.states.get("switch.rain_bird_sprinkler_3")
    assert zone is not None
    assert zone.state == "on"


@pytest.mark.parametrize(
    ("yaml_config", "config_entry_data"),
    [
        (
            {
                DOMAIN: {
                    "host": HOST,
                    "password": PASSWORD,
                    "trigger_time": 360,
                    "zones": {
                        1: {
                            "friendly_name": "Garden Sprinkler",
                        },
                        2: {
                            "friendly_name": "Back Yard",
                        },
                    },
                }
            },
            None,
        )
    ],
)
async def test_yaml_config(
    hass: HomeAssistant,
    setup_integration: ComponentSetup,
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Test switch platform with fake data that creates 7 zones with one enabled."""
    responses.insert(0, mock_response(SERIAL_RESPONSE))  # Extra import request
    assert await setup_integration()

    assert hass.states.get("switch.garden_sprinkler")
    assert not hass.states.get("switch.rain_bird_sprinkler_1")
    assert hass.states.get("switch.back_yard")
    assert not hass.states.get("switch.rain_bird_sprinkler_2")
    assert hass.states.get("switch.rain_bird_sprinkler_3")
