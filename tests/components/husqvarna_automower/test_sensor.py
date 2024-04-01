"""Tests for sensor platform."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from aioautomower.model import MowerModes
from aioautomower.utils import mower_list_to_dictionary_dataclass
from freezegun.api import FrozenDateTimeFactory
import pytest
from syrupy import SnapshotAssertion

from homeassistant.components.husqvarna_automower.const import DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration
from .const import TEST_MOWER_ID

from tests.common import (
    MockConfigEntry,
    async_fire_time_changed,
    load_json_value_fixture,
)


async def test_sensor_unknown_states(
    hass: HomeAssistant,
    mock_automower_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a sensor which returns unknown."""
    values = mower_list_to_dictionary_dataclass(
        load_json_value_fixture("mower.json", DOMAIN)
    )
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get("sensor.test_mower_1_mode")
    assert state is not None
    assert state.state == "main_area"

    values[TEST_MOWER_ID].mower.mode = MowerModes.UNKNOWN
    mock_automower_client.get_status.return_value = values
    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.test_mower_1_mode")
    assert state.state == "unknown"


async def test_cutting_blade_usage_time_sensor(
    hass: HomeAssistant,
    mock_automower_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test if this sensor is only added, if data is available."""

    await setup_integration(hass, mock_config_entry)
    state = hass.states.get("sensor.test_mower_1_cutting_blade_usage_time")
    assert state is not None
    assert state.state == "0.034"


@pytest.mark.parametrize(
    ("sensor_to_test"),
    [
        ("cutting_blade_usage_time"),
        ("number_of_charging_cycles"),
        ("number_of_collisions"),
        ("total_charging_time"),
        ("total_cutting_time"),
        ("total_running_time"),
        ("total_searching_time"),
        ("total_drive_distance"),
    ],
)
async def test_statistics_not_available(
    hass: HomeAssistant,
    mock_automower_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    sensor_to_test: str,
) -> None:
    """Test if this sensor is only added, if data is available."""

    values = mower_list_to_dictionary_dataclass(
        load_json_value_fixture("mower.json", DOMAIN)
    )

    delattr(values[TEST_MOWER_ID].statistics, sensor_to_test)
    mock_automower_client.get_status.return_value = values
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get(f"sensor.test_mower_1_{sensor_to_test}")
    assert state is None


async def test_error_sensor(
    hass: HomeAssistant,
    mock_automower_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test error sensor."""
    values = mower_list_to_dictionary_dataclass(
        load_json_value_fixture("mower.json", DOMAIN)
    )
    await setup_integration(hass, mock_config_entry)

    for state, expected_state in [
        (None, "no_error"),
        ("can_error", "can_error"),
    ]:
        values[TEST_MOWER_ID].mower.error_key = state
        mock_automower_client.get_status.return_value = values
        freezer.tick(timedelta(minutes=5))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        state = hass.states.get("sensor.test_mower_1_error")
        assert state.state == expected_state


async def test_sensor(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_automower_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test states of the sensors."""
    with patch(
        "homeassistant.components.husqvarna_automower.PLATFORMS",
        [Platform.SENSOR],
    ):
        await setup_integration(hass, mock_config_entry)
        entity_entries = er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )

        assert entity_entries
        for entity_entry in entity_entries:
            assert hass.states.get(entity_entry.entity_id) == snapshot(
                name=f"{entity_entry.entity_id}-state"
            )
            assert entity_entry == snapshot(name=f"{entity_entry.entity_id}-entry")
