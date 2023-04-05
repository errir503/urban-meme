"""Test the Reolink init."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from reolink_aio.exceptions import ReolinkError

from homeassistant.components.reolink import const
from homeassistant.config import async_process_ha_core_config
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from tests.common import MockConfigEntry

pytestmark = pytest.mark.usefixtures("reolink_connect", "reolink_platforms")


@pytest.mark.parametrize(
    ("attr", "value", "expected"),
    [
        (
            "is_admin",
            False,
            ConfigEntryState.SETUP_ERROR,
        ),
        (
            "get_host_data",
            AsyncMock(side_effect=ReolinkError("Test error")),
            ConfigEntryState.SETUP_RETRY,
        ),
        (
            "get_host_data",
            AsyncMock(side_effect=ValueError("Test error")),
            ConfigEntryState.SETUP_ERROR,
        ),
        (
            "get_states",
            AsyncMock(side_effect=ReolinkError("Test error")),
            ConfigEntryState.SETUP_RETRY,
        ),
        (
            "supported",
            Mock(return_value=False),
            ConfigEntryState.LOADED,
        ),
        (
            "check_new_firmware",
            AsyncMock(side_effect=ReolinkError("Test error")),
            ConfigEntryState.LOADED,
        ),
    ],
)
async def test_failures_parametrized(
    hass: HomeAssistant,
    reolink_connect: MagicMock,
    reolink_ONVIF_wait: MagicMock,
    config_entry: MockConfigEntry,
    attr: str,
    value: Any,
    expected: ConfigEntryState,
) -> None:
    """Test outcomes when changing errors."""
    setattr(reolink_connect, attr, value)
    assert await hass.config_entries.async_setup(config_entry.entry_id) is (
        expected == ConfigEntryState.LOADED
    )
    await hass.async_block_till_done()

    assert config_entry.state == expected


async def test_entry_reloading(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    reolink_connect: MagicMock,
    reolink_ONVIF_wait: MagicMock,
) -> None:
    """Test the entry is reloaded correctly when settings change."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert reolink_connect.logout.call_count == 0
    assert config_entry.title == "test_reolink_name"

    hass.config_entries.async_update_entry(config_entry, title="New Name")
    await hass.async_block_till_done()

    assert reolink_connect.logout.call_count == 1
    assert config_entry.title == "New Name"


async def test_no_repair_issue(
    hass: HomeAssistant, config_entry: MockConfigEntry, reolink_ONVIF_wait: MagicMock
) -> None:
    """Test no repairs issue is raised when http local url is used."""
    await async_process_ha_core_config(
        hass, {"country": "GB", "internal_url": "http://test_homeassistant_address"}
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    issue_registry = ir.async_get(hass)
    assert (const.DOMAIN, "https_webhook") not in issue_registry.issues
    assert (const.DOMAIN, "webhook_url") not in issue_registry.issues
    assert (const.DOMAIN, "enable_port") not in issue_registry.issues
    assert (const.DOMAIN, "firmware_update") not in issue_registry.issues


async def test_https_repair_issue(
    hass: HomeAssistant, config_entry: MockConfigEntry, reolink_ONVIF_wait: MagicMock
) -> None:
    """Test repairs issue is raised when https local url is used."""
    await async_process_ha_core_config(
        hass, {"country": "GB", "internal_url": "https://test_homeassistant_address"}
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    issue_registry = ir.async_get(hass)
    assert (const.DOMAIN, "https_webhook") in issue_registry.issues


@pytest.mark.parametrize("protocol", ["rtsp", "rtmp"])
async def test_port_repair_issue(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    reolink_connect: MagicMock,
    reolink_ONVIF_wait: MagicMock,
    protocol: str,
) -> None:
    """Test repairs issue is raised when auto enable of ports fails."""
    reolink_connect.set_net_port = AsyncMock(side_effect=ReolinkError("Test error"))
    reolink_connect.onvif_enabled = False
    reolink_connect.rtsp_enabled = False
    reolink_connect.rtmp_enabled = False
    reolink_connect.protocol = protocol
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    issue_registry = ir.async_get(hass)
    assert (const.DOMAIN, "enable_port") in issue_registry.issues


async def test_webhook_repair_issue(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Test repairs issue is raised when the webhook url is unreachable."""
    with patch("homeassistant.components.reolink.host.FIRST_ONVIF_TIMEOUT", new=0):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    issue_registry = ir.async_get(hass)
    assert (const.DOMAIN, "webhook_url") in issue_registry.issues


async def test_firmware_repair_issue(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    reolink_connect: MagicMock,
    reolink_ONVIF_wait: MagicMock,
) -> None:
    """Test firmware issue is raised when too old firmware is used."""
    reolink_connect.sw_version_update_required = True
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    issue_registry = ir.async_get(hass)
    assert (const.DOMAIN, "firmware_update") in issue_registry.issues
