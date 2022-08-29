"""Tests for SpeedTest integration."""

from collections.abc import Awaitable
from datetime import timedelta
from typing import Callable
from unittest.mock import MagicMock

from aiohttp import ClientWebSocketResponse
import speedtest

from homeassistant.components.speedtestdotnet.const import (
    CONF_MANUAL,
    CONF_SERVER_ID,
    CONF_SERVER_NAME,
    DOMAIN,
    SPEED_TEST_SERVICE,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_SCAN_INTERVAL, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

from tests.common import MockConfigEntry, async_fire_time_changed
from tests.components.repairs import get_repairs


async def test_successful_config_entry(hass: HomeAssistant) -> None:
    """Test that SpeedTestDotNet is configured successfully."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            CONF_SERVER_NAME: "Country1 - Sponsor1 - Server1",
            CONF_SERVER_ID: "1",
            CONF_SCAN_INTERVAL: 30,
            CONF_MANUAL: False,
        },
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state == ConfigEntryState.LOADED
    assert hass.data[DOMAIN]
    assert hass.services.has_service(DOMAIN, SPEED_TEST_SERVICE)


async def test_setup_failed(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """Test SpeedTestDotNet failed due to an error."""

    entry = MockConfigEntry(
        domain=DOMAIN,
    )
    entry.add_to_hass(hass)

    mock_api.side_effect = speedtest.ConfigRetrievalError
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry(hass: HomeAssistant) -> None:
    """Test removing SpeedTestDotNet."""
    entry = MockConfigEntry(
        domain=DOMAIN,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert DOMAIN not in hass.data


async def test_server_not_found(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """Test configured server id is not found."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_MANUAL: False,
            CONF_SCAN_INTERVAL: 60,
        },
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN]

    mock_api.return_value.get_servers.side_effect = speedtest.NoMatchedServers
    async_fire_time_changed(
        hass,
        dt_util.utcnow() + timedelta(minutes=entry.options[CONF_SCAN_INTERVAL] + 1),
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.speedtest_ping")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_get_best_server_error(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """Test configured server id is not found."""

    entry = MockConfigEntry(
        domain=DOMAIN,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN]

    mock_api.return_value.get_best_server.side_effect = (
        speedtest.SpeedtestBestServerFailure(
            "Unable to connect to servers to test latency."
        )
    )
    await hass.data[DOMAIN].async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.speedtest_ping")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_deprecated_service_alert(
    hass: HomeAssistant,
    hass_ws_client: Callable[[HomeAssistant], Awaitable[ClientWebSocketResponse]],
) -> None:
    """Test that an issue is raised if deprecated services is called."""
    entry = MockConfigEntry(
        domain=DOMAIN,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        "speedtest",
        {},
        blocking=True,
    )
    await hass.async_block_till_done()
    issues = await get_repairs(hass, hass_ws_client)
    assert len(issues) == 1
    assert issues[0]["issue_id"] == "deprecated_service"
