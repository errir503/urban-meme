"""Tests for the Withings component."""
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from syrupy import SnapshotAssertion

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import (
    load_activity_fixture,
    load_goals_fixture,
    load_measurements_fixture,
    setup_integration,
)

from tests.common import MockConfigEntry, async_fire_time_changed


@pytest.mark.freeze_time("2023-10-21")
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    withings: AsyncMock,
    polling_config_entry: MockConfigEntry,
) -> None:
    """Test all entities."""
    with patch("homeassistant.components.withings.PLATFORMS", [Platform.SENSOR]):
        await setup_integration(hass, polling_config_entry)
        entity_registry = er.async_get(hass)
        entity_entries = er.async_entries_for_config_entry(
            entity_registry, polling_config_entry.entry_id
        )

        assert entity_entries
        for entity_entry in entity_entries:
            assert hass.states.get(entity_entry.entity_id) == snapshot(
                name=entity_entry.entity_id
            )


async def test_update_failed(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    withings: AsyncMock,
    polling_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test all entities."""
    await setup_integration(hass, polling_config_entry, False)

    withings.get_measurement_since.side_effect = Exception
    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.henk_weight")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_update_updates_incrementally(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    withings: AsyncMock,
    polling_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test fetching new data updates since the last valid update."""
    await setup_integration(hass, polling_config_entry, False)

    async def _skip_10_minutes() -> None:
        freezer.tick(timedelta(minutes=10))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    assert withings.get_measurement_since.call_args_list == []
    await _skip_10_minutes()
    assert (
        str(withings.get_measurement_since.call_args_list[0].args[0])
        == "2019-08-01 12:00:00+00:00"
    )

    withings.get_measurement_since.return_value = load_measurements_fixture(
        "withings/measurements_1.json"
    )

    await _skip_10_minutes()
    assert (
        str(withings.get_measurement_since.call_args_list[1].args[0])
        == "2019-08-01 12:00:00+00:00"
    )

    await _skip_10_minutes()
    assert (
        str(withings.get_measurement_since.call_args_list[2].args[0])
        == "2021-04-16 20:30:55+00:00"
    )

    state = hass.states.get("sensor.henk_weight")
    assert state is not None
    assert state.state == "71"
    assert len(withings.get_measurement_in_period.call_args_list) == 1


async def test_update_new_measurement_creates_new_sensor(
    hass: HomeAssistant,
    withings: AsyncMock,
    polling_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test fetching a new measurement will add a new sensor."""
    withings.get_measurement_in_period.return_value = load_measurements_fixture(
        "withings/measurements_1.json"
    )
    await setup_integration(hass, polling_config_entry, False)

    assert hass.states.get("sensor.henk_fat_mass") is None

    withings.get_measurement_in_period.return_value = load_measurements_fixture()

    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.henk_fat_mass") is not None


async def test_update_new_goals_creates_new_sensor(
    hass: HomeAssistant,
    withings: AsyncMock,
    polling_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test fetching new goals will add a new sensor."""

    withings.get_goals.return_value = load_goals_fixture("withings/goals_1.json")

    await setup_integration(hass, polling_config_entry, False)

    assert hass.states.get("sensor.henk_step_goal") is None
    assert hass.states.get("sensor.henk_weight_goal") is not None

    withings.get_goals.return_value = load_goals_fixture()

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.henk_step_goal") is not None


async def test_activity_sensors_unknown_next_day(
    hass: HomeAssistant,
    withings: AsyncMock,
    polling_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test activity sensors will return unknown the next day."""
    freezer.move_to("2023-10-21")
    await setup_integration(hass, polling_config_entry, False)

    assert hass.states.get("sensor.henk_steps_today") is not None

    withings.get_activities_since.return_value = []

    freezer.tick(timedelta(days=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.henk_steps_today").state == STATE_UNKNOWN


async def test_activity_sensors_same_result_same_day(
    hass: HomeAssistant,
    withings: AsyncMock,
    polling_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test activity sensors will return the same result if old data is updated."""
    freezer.move_to("2023-10-21")
    await setup_integration(hass, polling_config_entry, False)

    assert hass.states.get("sensor.henk_steps_today").state == "1155"

    withings.get_activities_since.return_value = []

    freezer.tick(timedelta(hours=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.henk_steps_today").state == "1155"


async def test_activity_sensors_created_when_existed(
    hass: HomeAssistant,
    withings: AsyncMock,
    polling_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test activity sensors will be added if they existed before."""
    freezer.move_to("2023-10-21")
    await setup_integration(hass, polling_config_entry, False)

    assert hass.states.get("sensor.henk_steps_today") is not None
    assert hass.states.get("sensor.henk_steps_today").state != STATE_UNKNOWN

    withings.get_activities_in_period.return_value = []

    await hass.config_entries.async_reload(polling_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.henk_steps_today").state == STATE_UNKNOWN


async def test_activity_sensors_created_when_receive_activity_data(
    hass: HomeAssistant,
    withings: AsyncMock,
    polling_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test activity sensors will be added if we receive activity data."""
    freezer.move_to("2023-10-21")
    withings.get_activities_in_period.return_value = []
    await setup_integration(hass, polling_config_entry, False)

    assert hass.states.get("sensor.henk_steps_today") is None

    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.henk_steps_today") is None

    withings.get_activities_in_period.return_value = load_activity_fixture()

    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.henk_steps_today") is not None
