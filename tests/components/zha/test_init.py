"""Tests for ZHA integration init."""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from zigpy.config import CONF_DEVICE, CONF_DEVICE_PATH

from homeassistant.components.zha import async_setup_entry
from homeassistant.components.zha.core.const import (
    CONF_BAUDRATE,
    CONF_RADIO_TYPE,
    CONF_USB_PATH,
    DOMAIN,
)
from homeassistant.const import MAJOR_VERSION, MINOR_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

DATA_RADIO_TYPE = "deconz"
DATA_PORT_PATH = "/dev/serial/by-id/FTDI_USB__-__Serial_Cable_12345678-if00-port0"


@pytest.fixture(autouse=True)
def disable_platform_only():
    """Disable platforms to speed up tests."""
    with patch("homeassistant.components.zha.PLATFORMS", []):
        yield


@pytest.fixture
def config_entry_v1(hass):
    """Config entry version 1 fixture."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_RADIO_TYPE: DATA_RADIO_TYPE, CONF_USB_PATH: DATA_PORT_PATH},
        version=1,
    )


@pytest.mark.parametrize("config", ({}, {DOMAIN: {}}))
@patch("homeassistant.components.zha.async_setup_entry", AsyncMock(return_value=True))
async def test_migration_from_v1_no_baudrate(
    hass: HomeAssistant, config_entry_v1, config
) -> None:
    """Test migration of config entry from v1."""
    config_entry_v1.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, config)

    assert config_entry_v1.data[CONF_RADIO_TYPE] == DATA_RADIO_TYPE
    assert CONF_DEVICE in config_entry_v1.data
    assert config_entry_v1.data[CONF_DEVICE][CONF_DEVICE_PATH] == DATA_PORT_PATH
    assert CONF_BAUDRATE not in config_entry_v1.data[CONF_DEVICE]
    assert CONF_USB_PATH not in config_entry_v1.data
    assert config_entry_v1.version == 3


@patch("homeassistant.components.zha.async_setup_entry", AsyncMock(return_value=True))
async def test_migration_from_v1_with_baudrate(
    hass: HomeAssistant, config_entry_v1
) -> None:
    """Test migration of config entry from v1 with baudrate in config."""
    config_entry_v1.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {CONF_BAUDRATE: 115200}})

    assert config_entry_v1.data[CONF_RADIO_TYPE] == DATA_RADIO_TYPE
    assert CONF_DEVICE in config_entry_v1.data
    assert config_entry_v1.data[CONF_DEVICE][CONF_DEVICE_PATH] == DATA_PORT_PATH
    assert CONF_USB_PATH not in config_entry_v1.data
    assert CONF_BAUDRATE in config_entry_v1.data[CONF_DEVICE]
    assert config_entry_v1.data[CONF_DEVICE][CONF_BAUDRATE] == 115200
    assert config_entry_v1.version == 3


@patch("homeassistant.components.zha.async_setup_entry", AsyncMock(return_value=True))
async def test_migration_from_v1_wrong_baudrate(
    hass: HomeAssistant, config_entry_v1
) -> None:
    """Test migration of config entry from v1 with wrong baudrate."""
    config_entry_v1.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {CONF_BAUDRATE: 115222}})

    assert config_entry_v1.data[CONF_RADIO_TYPE] == DATA_RADIO_TYPE
    assert CONF_DEVICE in config_entry_v1.data
    assert config_entry_v1.data[CONF_DEVICE][CONF_DEVICE_PATH] == DATA_PORT_PATH
    assert CONF_USB_PATH not in config_entry_v1.data
    assert CONF_BAUDRATE not in config_entry_v1.data[CONF_DEVICE]
    assert config_entry_v1.version == 3


@pytest.mark.skipif(
    MAJOR_VERSION != 0 or (MAJOR_VERSION == 0 and MINOR_VERSION >= 112),
    reason="Not applicaable for this version",
)
@pytest.mark.parametrize(
    "zha_config",
    (
        {},
        {CONF_USB_PATH: "str"},
        {CONF_RADIO_TYPE: "ezsp"},
        {CONF_RADIO_TYPE: "ezsp", CONF_USB_PATH: "str"},
    ),
)
async def test_config_depreciation(hass: HomeAssistant, zha_config) -> None:
    """Test config option depreciation."""

    with patch(
        "homeassistant.components.zha.async_setup", return_value=True
    ) as setup_mock:
        assert await async_setup_component(hass, DOMAIN, {DOMAIN: zha_config})
        assert setup_mock.call_count == 1


@pytest.mark.parametrize(
    ("path", "cleaned_path"),
    [
        ("/dev/path1", "/dev/path1"),
        ("/dev/path1 ", "/dev/path1 "),
        ("socket://dev/path1 ", "socket://dev/path1"),
    ],
)
@patch("homeassistant.components.zha.setup_quirks", Mock(return_value=True))
@patch(
    "homeassistant.components.zha.websocket_api.async_load_api", Mock(return_value=True)
)
async def test_setup_with_v3_spaces_in_uri(
    hass: HomeAssistant, path: str, cleaned_path: str
) -> None:
    """Test migration of config entry from v3 with spaces after `socket://` URI."""
    config_entry_v3 = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_RADIO_TYPE: DATA_RADIO_TYPE,
            CONF_DEVICE: {CONF_DEVICE_PATH: path, CONF_BAUDRATE: 115200},
        },
        version=3,
    )
    config_entry_v3.add_to_hass(hass)

    with patch(
        "homeassistant.components.zha.ZHAGateway", return_value=AsyncMock()
    ) as mock_gateway:
        mock_gateway.return_value.coordinator_ieee = "mock_ieee"
        mock_gateway.return_value.radio_description = "mock_radio"

        assert await async_setup_entry(hass, config_entry_v3)
        hass.data[DOMAIN]["zha_gateway"] = mock_gateway.return_value

    assert config_entry_v3.data[CONF_RADIO_TYPE] == DATA_RADIO_TYPE
    assert config_entry_v3.data[CONF_DEVICE][CONF_DEVICE_PATH] == cleaned_path
    assert config_entry_v3.version == 3
