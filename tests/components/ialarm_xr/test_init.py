"""Test the Antifurto365 iAlarmXR init."""
import asyncio
from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from homeassistant.components.ialarm_xr.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.util.dt import utcnow

from tests.common import MockConfigEntry, async_fire_time_changed


@pytest.fixture(name="ialarmxr_api")
def ialarmxr_api_fixture():
    """Set up IAlarmXR API fixture."""
    with patch("homeassistant.components.ialarm_xr.IAlarmXR") as mock_ialarm_api:
        yield mock_ialarm_api


@pytest.fixture(name="mock_config_entry")
def mock_config_fixture():
    """Return a fake config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.10.20",
            CONF_PORT: 18034,
            CONF_USERNAME: "000ZZZ0Z00",
            CONF_PASSWORD: "00000000",
        },
        entry_id=str(uuid4()),
    )


async def test_setup_entry(hass, ialarmxr_api, mock_config_entry):
    """Test setup entry."""
    ialarmxr_api.return_value.get_mac = Mock(return_value="00:00:54:12:34:56")

    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    ialarmxr_api.return_value.get_mac.assert_called_once()
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_setup_not_ready(hass, ialarmxr_api, mock_config_entry):
    """Test setup failed because we can't connect to the alarm system."""
    ialarmxr_api.return_value.get_mac = Mock(side_effect=ConnectionError)

    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry(hass, ialarmxr_api, mock_config_entry):
    """Test being able to unload an entry."""
    ialarmxr_api.return_value.get_mac = Mock(return_value="00:00:54:12:34:56")

    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_not_ready_connection_error(hass, ialarmxr_api, mock_config_entry):
    """Test setup failed because we can't connect to the alarm system."""
    ialarmxr_api.return_value.get_status = Mock(side_effect=ConnectionError)

    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    future = utcnow() + timedelta(seconds=30)
    async_fire_time_changed(hass, future)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_not_ready_timeout(hass, ialarmxr_api, mock_config_entry):
    """Test setup failed because we can't connect to the alarm system."""
    ialarmxr_api.return_value.get_status = Mock(side_effect=asyncio.TimeoutError)

    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    future = utcnow() + timedelta(seconds=30)
    async_fire_time_changed(hass, future)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_and_then_fail_on_update(
    hass, ialarmxr_api, mock_config_entry
):
    """Test setup entry."""
    ialarmxr_api.return_value.get_mac = Mock(return_value="00:00:54:12:34:56")
    ialarmxr_api.return_value.get_status = Mock(value=ialarmxr_api.DISARMED)

    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    ialarmxr_api.return_value.get_mac.assert_called_once()
    ialarmxr_api.return_value.get_status.assert_called_once()
    assert mock_config_entry.state is ConfigEntryState.LOADED

    ialarmxr_api.return_value.get_status = Mock(side_effect=asyncio.TimeoutError)
    future = utcnow() + timedelta(seconds=60)
    async_fire_time_changed(hass, future)
    await hass.async_block_till_done()
    ialarmxr_api.return_value.get_status.assert_called_once()
    assert hass.states.get("alarm_control_panel.ialarm_xr").state == "unavailable"
