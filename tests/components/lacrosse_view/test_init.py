"""Test the LaCrosse View initialization."""
from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time
from lacrosse_view import HTTPError, LoginError

from homeassistant.components.lacrosse_view.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from . import MOCK_ENTRY_DATA, TEST_SENSOR

from tests.common import MockConfigEntry, async_fire_time_changed


async def test_unload_entry(hass: HomeAssistant) -> None:
    """Test the unload entry."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA)
    config_entry.add_to_hass(hass)

    with patch("lacrosse_view.LaCrosse.login", return_value=True), patch(
        "lacrosse_view.LaCrosse.get_sensors",
        return_value=[TEST_SENSOR],
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert hass.data[DOMAIN]

    entries = hass.config_entries.async_entries(DOMAIN)
    assert entries
    assert len(entries) == 1
    assert entries[0].state == ConfigEntryState.LOADED

    await hass.config_entries.async_unload(entries[0].entry_id)
    await hass.async_block_till_done()
    assert entries[0].state == ConfigEntryState.NOT_LOADED


async def test_login_error(hass: HomeAssistant) -> None:
    """Test login error."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA)
    config_entry.add_to_hass(hass)

    with patch("lacrosse_view.LaCrosse.login", side_effect=LoginError("Test")):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert entries
    assert len(entries) == 1
    assert entries[0].state == ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"


async def test_http_error(hass: HomeAssistant) -> None:
    """Test http error."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA)
    config_entry.add_to_hass(hass)

    with patch("lacrosse_view.LaCrosse.login", return_value=True), patch(
        "lacrosse_view.LaCrosse.get_sensors", side_effect=HTTPError
    ):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert entries
    assert len(entries) == 1
    assert entries[0].state == ConfigEntryState.SETUP_RETRY


async def test_new_token(hass: HomeAssistant) -> None:
    """Test new token."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA)
    config_entry.add_to_hass(hass)

    with patch("lacrosse_view.LaCrosse.login", return_value=True) as login, patch(
        "lacrosse_view.LaCrosse.get_sensors",
        return_value=[TEST_SENSOR],
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        login.assert_called_once()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert entries
    assert len(entries) == 1
    assert entries[0].state == ConfigEntryState.LOADED

    one_hour_after = datetime.utcnow() + timedelta(hours=1)

    with patch("lacrosse_view.LaCrosse.login", return_value=True) as login, patch(
        "lacrosse_view.LaCrosse.get_sensors",
        return_value=[TEST_SENSOR],
    ), freeze_time(one_hour_after):
        async_fire_time_changed(hass, one_hour_after)
        await hass.async_block_till_done()

        login.assert_called_once()


async def test_failed_token(hass: HomeAssistant) -> None:
    """Test if a reauth flow occurs when token refresh fails."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA)
    config_entry.add_to_hass(hass)

    with patch("lacrosse_view.LaCrosse.login", return_value=True) as login, patch(
        "lacrosse_view.LaCrosse.get_sensors",
        return_value=[TEST_SENSOR],
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        login.assert_called_once()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert entries
    assert len(entries) == 1
    assert entries[0].state == ConfigEntryState.LOADED

    one_hour_after = datetime.utcnow() + timedelta(hours=1)

    with patch(
        "lacrosse_view.LaCrosse.login", side_effect=LoginError("Test")
    ), freeze_time(one_hour_after):
        async_fire_time_changed(hass, one_hour_after)
        await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert entries
    assert len(entries) == 1
    assert entries[0].state == ConfigEntryState.LOADED

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
