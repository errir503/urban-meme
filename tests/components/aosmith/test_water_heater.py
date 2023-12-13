"""Tests for the water heater platform of the A. O. Smith integration."""

from unittest.mock import MagicMock

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.aosmith.const import (
    AOSMITH_MODE_ELECTRIC,
    AOSMITH_MODE_HEAT_PUMP,
    AOSMITH_MODE_HYBRID,
    AOSMITH_MODE_VACATION,
)
from homeassistant.components.water_heater import (
    ATTR_AWAY_MODE,
    ATTR_OPERATION_MODE,
    ATTR_TEMPERATURE,
    DOMAIN as WATER_HEATER_DOMAIN,
    SERVICE_SET_AWAY_MODE,
    SERVICE_SET_OPERATION_MODE,
    SERVICE_SET_TEMPERATURE,
    STATE_ECO,
    STATE_ELECTRIC,
    STATE_HEAT_PUMP,
    WaterHeaterEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_SUPPORTED_FEATURES,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry


async def test_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test the setup of the water heater entity."""
    entry = entity_registry.async_get("water_heater.my_water_heater")
    assert entry
    assert entry.unique_id == "junctionId"

    state = hass.states.get("water_heater.my_water_heater")
    assert state
    assert state.attributes.get(ATTR_FRIENDLY_NAME) == "My water heater"


async def test_state(
    hass: HomeAssistant, init_integration: MockConfigEntry, snapshot: SnapshotAssertion
) -> None:
    """Test the state of the water heater entity."""
    state = hass.states.get("water_heater.my_water_heater")
    assert state == snapshot


@pytest.mark.parametrize(
    ("get_devices_fixture"),
    ["get_devices_no_vacation_mode"],
)
async def test_state_away_mode_unsupported(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test that away mode is not supported if the water heater does not support vacation mode."""
    state = hass.states.get("water_heater.my_water_heater")
    assert (
        state.attributes.get(ATTR_SUPPORTED_FEATURES)
        == WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )


@pytest.mark.parametrize(
    ("hass_mode", "aosmith_mode"),
    [
        (STATE_HEAT_PUMP, AOSMITH_MODE_HEAT_PUMP),
        (STATE_ECO, AOSMITH_MODE_HYBRID),
        (STATE_ELECTRIC, AOSMITH_MODE_ELECTRIC),
    ],
)
async def test_set_operation_mode(
    hass: HomeAssistant,
    mock_client: MagicMock,
    init_integration: MockConfigEntry,
    hass_mode: str,
    aosmith_mode: str,
) -> None:
    """Test setting the operation mode."""
    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_OPERATION_MODE,
        {
            ATTR_ENTITY_ID: "water_heater.my_water_heater",
            ATTR_OPERATION_MODE: hass_mode,
        },
    )
    await hass.async_block_till_done()

    mock_client.update_mode.assert_called_once_with("junctionId", aosmith_mode)


async def test_set_temperature(
    hass: HomeAssistant,
    mock_client: MagicMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test setting the target temperature."""
    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: "water_heater.my_water_heater", ATTR_TEMPERATURE: 120},
    )
    await hass.async_block_till_done()

    mock_client.update_setpoint.assert_called_once_with("junctionId", 120)


@pytest.mark.parametrize(
    ("hass_away_mode", "aosmith_mode"),
    [
        (True, AOSMITH_MODE_VACATION),
        (False, AOSMITH_MODE_HYBRID),
    ],
)
async def test_away_mode(
    hass: HomeAssistant,
    mock_client: MagicMock,
    init_integration: MockConfigEntry,
    hass_away_mode: bool,
    aosmith_mode: str,
) -> None:
    """Test turning away mode on/off."""
    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_AWAY_MODE,
        {
            ATTR_ENTITY_ID: "water_heater.my_water_heater",
            ATTR_AWAY_MODE: hass_away_mode,
        },
    )
    await hass.async_block_till_done()

    mock_client.update_mode.assert_called_once_with("junctionId", aosmith_mode)
