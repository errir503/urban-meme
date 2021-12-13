"""Tests for the TotalConnect alarm control panel device."""
from datetime import timedelta
from unittest.mock import patch

import pytest

from homeassistant.components.alarm_control_panel import DOMAIN as ALARM_DOMAIN
from homeassistant.components.totalconnect import DOMAIN
from homeassistant.components.totalconnect.alarm_control_panel import (
    SERVICE_ALARM_ARM_AWAY_INSTANT,
    SERVICE_ALARM_ARM_HOME_INSTANT,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    SERVICE_ALARM_ARM_AWAY,
    SERVICE_ALARM_ARM_HOME,
    SERVICE_ALARM_ARM_NIGHT,
    SERVICE_ALARM_DISARM,
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_CUSTOM_BYPASS,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_ARMED_NIGHT,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMED,
    STATE_ALARM_DISARMING,
    STATE_ALARM_TRIGGERED,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt

from .common import (
    LOCATION_ID,
    RESPONSE_ARM_FAILURE,
    RESPONSE_ARM_SUCCESS,
    RESPONSE_ARMED_AWAY,
    RESPONSE_ARMED_CUSTOM,
    RESPONSE_ARMED_NIGHT,
    RESPONSE_ARMED_STAY,
    RESPONSE_ARMING,
    RESPONSE_DISARM_FAILURE,
    RESPONSE_DISARM_SUCCESS,
    RESPONSE_DISARMED,
    RESPONSE_DISARMING,
    RESPONSE_SUCCESS,
    RESPONSE_TRIGGERED_CARBON_MONOXIDE,
    RESPONSE_TRIGGERED_FIRE,
    RESPONSE_TRIGGERED_POLICE,
    RESPONSE_UNKNOWN,
    RESPONSE_USER_CODE_INVALID,
    TOTALCONNECT_REQUEST,
    setup_platform,
)

from tests.common import async_fire_time_changed

ENTITY_ID = "alarm_control_panel.test"
ENTITY_ID_2 = "alarm_control_panel.test_partition_2"
CODE = "-1"
DATA = {ATTR_ENTITY_ID: ENTITY_ID}
DELAY = timedelta(seconds=10)


async def test_attributes(hass: HomeAssistant) -> None:
    """Test the alarm control panel attributes are correct."""
    with patch(
        "homeassistant.components.totalconnect.TotalConnectClient.request",
        return_value=RESPONSE_DISARMED,
    ) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        state = hass.states.get(ENTITY_ID)
        assert state.state == STATE_ALARM_DISARMED
        mock_request.assert_called_once()
        assert state.attributes.get(ATTR_FRIENDLY_NAME) == "test"

        entity_registry = await hass.helpers.entity_registry.async_get_registry()
        entry = entity_registry.async_get(ENTITY_ID)
        # TotalConnect partition #1 alarm device unique_id is the location_id
        assert entry.unique_id == LOCATION_ID

        entry2 = entity_registry.async_get(ENTITY_ID_2)
        # TotalConnect partition #2 unique_id is the location_id + "_{partition_number}"
        assert entry2.unique_id == LOCATION_ID + "_2"
        assert mock_request.call_count == 1


async def test_arm_home_success(hass: HomeAssistant) -> None:
    """Test arm home method success."""
    responses = [RESPONSE_DISARMED, RESPONSE_ARM_SUCCESS, RESPONSE_ARMED_STAY]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert hass.states.get(ENTITY_ID_2).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        await hass.services.async_call(
            ALARM_DOMAIN, SERVICE_ALARM_ARM_HOME, DATA, blocking=True
        )
        assert mock_request.call_count == 2

        async_fire_time_changed(hass, dt.utcnow() + DELAY)
        await hass.async_block_till_done()
        assert mock_request.call_count == 3
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_HOME
        # second partition should not be armed
        assert hass.states.get(ENTITY_ID_2).state == STATE_ALARM_DISARMED


async def test_arm_home_failure(hass: HomeAssistant) -> None:
    """Test arm home method failure."""
    responses = [RESPONSE_DISARMED, RESPONSE_ARM_FAILURE]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        with pytest.raises(HomeAssistantError) as err:
            await hass.services.async_call(
                ALARM_DOMAIN, SERVICE_ALARM_ARM_HOME, DATA, blocking=True
            )
            await hass.async_block_till_done()
        assert f"{err.value}" == "TotalConnect failed to arm home test."
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 2


async def test_arm_home_instant_success(hass: HomeAssistant) -> None:
    """Test arm home instant method success."""
    responses = [RESPONSE_DISARMED, RESPONSE_ARM_SUCCESS, RESPONSE_ARMED_STAY]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert hass.states.get(ENTITY_ID_2).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        await hass.services.async_call(
            DOMAIN, SERVICE_ALARM_ARM_HOME_INSTANT, DATA, blocking=True
        )
        assert mock_request.call_count == 2

        async_fire_time_changed(hass, dt.utcnow() + DELAY)
        await hass.async_block_till_done()
        assert mock_request.call_count == 3
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_HOME


async def test_arm_home_instant_failure(hass: HomeAssistant) -> None:
    """Test arm home instant method failure."""
    responses = [RESPONSE_DISARMED, RESPONSE_ARM_FAILURE]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        with pytest.raises(HomeAssistantError) as err:
            await hass.services.async_call(
                DOMAIN, SERVICE_ALARM_ARM_HOME_INSTANT, DATA, blocking=True
            )
            await hass.async_block_till_done()
        assert f"{err.value}" == "TotalConnect failed to arm home instant test."
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 2


async def test_arm_away_instant_success(hass: HomeAssistant) -> None:
    """Test arm home instant method success."""
    responses = [RESPONSE_DISARMED, RESPONSE_ARM_SUCCESS, RESPONSE_ARMED_AWAY]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert hass.states.get(ENTITY_ID_2).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        await hass.services.async_call(
            DOMAIN, SERVICE_ALARM_ARM_AWAY_INSTANT, DATA, blocking=True
        )
        assert mock_request.call_count == 2

        async_fire_time_changed(hass, dt.utcnow() + DELAY)
        await hass.async_block_till_done()
        assert mock_request.call_count == 3
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_AWAY


async def test_arm_away_instant_failure(hass: HomeAssistant) -> None:
    """Test arm home instant method failure."""
    responses = [RESPONSE_DISARMED, RESPONSE_ARM_FAILURE]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        with pytest.raises(HomeAssistantError) as err:
            await hass.services.async_call(
                DOMAIN, SERVICE_ALARM_ARM_AWAY_INSTANT, DATA, blocking=True
            )
            await hass.async_block_till_done()
        assert f"{err.value}" == "TotalConnect failed to arm away instant test."
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 2


async def test_arm_home_invalid_usercode(hass: HomeAssistant) -> None:
    """Test arm home method with invalid usercode."""
    responses = [RESPONSE_DISARMED, RESPONSE_USER_CODE_INVALID]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        with pytest.raises(HomeAssistantError) as err:
            await hass.services.async_call(
                ALARM_DOMAIN, SERVICE_ALARM_ARM_HOME, DATA, blocking=True
            )
            await hass.async_block_till_done()
        assert f"{err.value}" == "TotalConnect failed to arm home test."
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 2


async def test_arm_away_success(hass: HomeAssistant) -> None:
    """Test arm away method success."""
    responses = [RESPONSE_DISARMED, RESPONSE_ARM_SUCCESS, RESPONSE_ARMED_AWAY]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        await hass.services.async_call(
            ALARM_DOMAIN, SERVICE_ALARM_ARM_AWAY, DATA, blocking=True
        )
        assert mock_request.call_count == 2

        async_fire_time_changed(hass, dt.utcnow() + DELAY)
        await hass.async_block_till_done()
        assert mock_request.call_count == 3
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_AWAY


async def test_arm_away_failure(hass: HomeAssistant) -> None:
    """Test arm away method failure."""
    responses = [RESPONSE_DISARMED, RESPONSE_ARM_FAILURE]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        with pytest.raises(HomeAssistantError) as err:
            await hass.services.async_call(
                ALARM_DOMAIN, SERVICE_ALARM_ARM_AWAY, DATA, blocking=True
            )
            await hass.async_block_till_done()
        assert f"{err.value}" == "TotalConnect failed to arm away test."
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 2


async def test_disarm_success(hass: HomeAssistant) -> None:
    """Test disarm method success."""
    responses = [RESPONSE_ARMED_AWAY, RESPONSE_DISARM_SUCCESS, RESPONSE_DISARMED]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_AWAY
        assert mock_request.call_count == 1

        await hass.services.async_call(
            ALARM_DOMAIN, SERVICE_ALARM_DISARM, DATA, blocking=True
        )
        assert mock_request.call_count == 2

        async_fire_time_changed(hass, dt.utcnow() + DELAY)
        await hass.async_block_till_done()
        assert mock_request.call_count == 3
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED


async def test_disarm_failure(hass: HomeAssistant) -> None:
    """Test disarm method failure."""
    responses = [RESPONSE_ARMED_AWAY, RESPONSE_DISARM_FAILURE]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_AWAY
        assert mock_request.call_count == 1

        with pytest.raises(HomeAssistantError) as err:
            await hass.services.async_call(
                ALARM_DOMAIN, SERVICE_ALARM_DISARM, DATA, blocking=True
            )
            await hass.async_block_till_done()
        assert f"{err.value}" == "TotalConnect failed to disarm test."
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_AWAY
        assert mock_request.call_count == 2


async def test_disarm_invalid_usercode(hass: HomeAssistant) -> None:
    """Test disarm method failure."""
    responses = [RESPONSE_ARMED_AWAY, RESPONSE_USER_CODE_INVALID]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_AWAY
        assert mock_request.call_count == 1

        with pytest.raises(HomeAssistantError) as err:
            await hass.services.async_call(
                ALARM_DOMAIN, SERVICE_ALARM_DISARM, DATA, blocking=True
            )
            await hass.async_block_till_done()
        assert f"{err.value}" == "TotalConnect failed to disarm test."
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_AWAY
        assert mock_request.call_count == 2


async def test_arm_night_success(hass: HomeAssistant) -> None:
    """Test arm night method success."""
    responses = [RESPONSE_DISARMED, RESPONSE_ARM_SUCCESS, RESPONSE_ARMED_NIGHT]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        await hass.services.async_call(
            ALARM_DOMAIN, SERVICE_ALARM_ARM_NIGHT, DATA, blocking=True
        )
        assert mock_request.call_count == 2

        async_fire_time_changed(hass, dt.utcnow() + DELAY)
        await hass.async_block_till_done()
        assert mock_request.call_count == 3
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_NIGHT


async def test_arm_night_failure(hass: HomeAssistant) -> None:
    """Test arm night method failure."""
    responses = [RESPONSE_DISARMED, RESPONSE_ARM_FAILURE]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        with pytest.raises(HomeAssistantError) as err:
            await hass.services.async_call(
                ALARM_DOMAIN, SERVICE_ALARM_ARM_NIGHT, DATA, blocking=True
            )
            await hass.async_block_till_done()
        assert f"{err.value}" == "TotalConnect failed to arm night test."
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 2


async def test_arming(hass: HomeAssistant) -> None:
    """Test arming."""
    responses = [RESPONSE_DISARMED, RESPONSE_SUCCESS, RESPONSE_ARMING]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMED
        assert mock_request.call_count == 1

        await hass.services.async_call(
            ALARM_DOMAIN, SERVICE_ALARM_ARM_NIGHT, DATA, blocking=True
        )
        assert mock_request.call_count == 2

        async_fire_time_changed(hass, dt.utcnow() + DELAY)
        await hass.async_block_till_done()
        assert mock_request.call_count == 3
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMING


async def test_disarming(hass: HomeAssistant) -> None:
    """Test disarming."""
    responses = [RESPONSE_ARMED_AWAY, RESPONSE_SUCCESS, RESPONSE_DISARMING]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_AWAY
        assert mock_request.call_count == 1

        await hass.services.async_call(
            ALARM_DOMAIN, SERVICE_ALARM_DISARM, DATA, blocking=True
        )
        assert mock_request.call_count == 2

        async_fire_time_changed(hass, dt.utcnow() + DELAY)
        await hass.async_block_till_done()
        assert mock_request.call_count == 3
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_DISARMING


async def test_triggered_fire(hass: HomeAssistant) -> None:
    """Test triggered by fire."""
    responses = [RESPONSE_TRIGGERED_FIRE]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        state = hass.states.get(ENTITY_ID)
        assert state.state == STATE_ALARM_TRIGGERED
        assert state.attributes.get("triggered_source") == "Fire/Smoke"
        assert mock_request.call_count == 1


async def test_triggered_police(hass: HomeAssistant) -> None:
    """Test triggered by police."""
    responses = [RESPONSE_TRIGGERED_POLICE]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        state = hass.states.get(ENTITY_ID)
        assert state.state == STATE_ALARM_TRIGGERED
        assert state.attributes.get("triggered_source") == "Police/Medical"
        assert mock_request.call_count == 1


async def test_triggered_carbon_monoxide(hass: HomeAssistant) -> None:
    """Test triggered by carbon monoxide."""
    responses = [RESPONSE_TRIGGERED_CARBON_MONOXIDE]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        state = hass.states.get(ENTITY_ID)
        assert state.state == STATE_ALARM_TRIGGERED
        assert state.attributes.get("triggered_source") == "Carbon Monoxide"
        assert mock_request.call_count == 1


async def test_armed_custom(hass: HomeAssistant) -> None:
    """Test armed custom."""
    responses = [RESPONSE_ARMED_CUSTOM]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_ALARM_ARMED_CUSTOM_BYPASS
        assert mock_request.call_count == 1


async def test_unknown(hass: HomeAssistant) -> None:
    """Test unknown arm status."""
    responses = [RESPONSE_UNKNOWN]
    with patch(TOTALCONNECT_REQUEST, side_effect=responses) as mock_request:
        await setup_platform(hass, ALARM_DOMAIN)
        assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
        assert mock_request.call_count == 1
