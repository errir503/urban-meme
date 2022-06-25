"""Tests for Islamic Prayer Times init."""

from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time
from prayer_times_calculator.exceptions import InvalidResponseError
import pytest

from homeassistant import config_entries
from homeassistant.components import islamic_prayer_times

from . import (
    NEW_PRAYER_TIMES,
    NEW_PRAYER_TIMES_TIMESTAMPS,
    NOW,
    PRAYER_TIMES,
    PRAYER_TIMES_TIMESTAMPS,
)

from tests.common import MockConfigEntry, async_fire_time_changed


@pytest.fixture(autouse=True)
def set_utc(hass):
    """Set timezone to UTC."""
    hass.config.set_time_zone("UTC")


async def test_successful_config_entry(hass):
    """Test that Islamic Prayer Times is configured successfully."""

    entry = MockConfigEntry(
        domain=islamic_prayer_times.DOMAIN,
        data={},
    )
    entry.add_to_hass(hass)

    with patch(
        "prayer_times_calculator.PrayerTimesCalculator.fetch_prayer_times",
        return_value=PRAYER_TIMES,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is config_entries.ConfigEntryState.LOADED
        assert entry.options == {
            islamic_prayer_times.CONF_CALC_METHOD: islamic_prayer_times.DEFAULT_CALC_METHOD
        }


async def test_setup_failed(hass):
    """Test Islamic Prayer Times failed due to an error."""

    entry = MockConfigEntry(
        domain=islamic_prayer_times.DOMAIN,
        data={},
    )
    entry.add_to_hass(hass)

    # test request error raising ConfigEntryNotReady
    with patch(
        "prayer_times_calculator.PrayerTimesCalculator.fetch_prayer_times",
        side_effect=InvalidResponseError(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY


async def test_unload_entry(hass):
    """Test removing Islamic Prayer Times."""
    entry = MockConfigEntry(
        domain=islamic_prayer_times.DOMAIN,
        data={},
    )
    entry.add_to_hass(hass)

    with patch(
        "prayer_times_calculator.PrayerTimesCalculator.fetch_prayer_times",
        return_value=PRAYER_TIMES,
    ):
        await hass.config_entries.async_setup(entry.entry_id)

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is config_entries.ConfigEntryState.NOT_LOADED
        assert islamic_prayer_times.DOMAIN not in hass.data


async def test_islamic_prayer_times_timestamp_format(hass):
    """Test Islamic prayer times timestamp format."""
    entry = MockConfigEntry(domain=islamic_prayer_times.DOMAIN, data={})
    entry.add_to_hass(hass)

    with patch(
        "prayer_times_calculator.PrayerTimesCalculator.fetch_prayer_times",
        return_value=PRAYER_TIMES,
    ), freeze_time(NOW):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert (
            hass.data[islamic_prayer_times.DOMAIN].prayer_times_info
            == PRAYER_TIMES_TIMESTAMPS
        )


async def test_update(hass):
    """Test sensors are updated with new prayer times."""
    entry = MockConfigEntry(domain=islamic_prayer_times.DOMAIN, data={})
    entry.add_to_hass(hass)

    with patch(
        "prayer_times_calculator.PrayerTimesCalculator.fetch_prayer_times"
    ) as FetchPrayerTimes, freeze_time(NOW):
        FetchPrayerTimes.side_effect = [
            PRAYER_TIMES,
            PRAYER_TIMES,
            NEW_PRAYER_TIMES,
        ]

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        pt_data = hass.data[islamic_prayer_times.DOMAIN]
        assert pt_data.prayer_times_info == PRAYER_TIMES_TIMESTAMPS

        future = pt_data.prayer_times_info["Midnight"] + timedelta(days=1, minutes=1)

        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()
        assert (
            hass.data[islamic_prayer_times.DOMAIN].prayer_times_info
            == NEW_PRAYER_TIMES_TIMESTAMPS
        )
