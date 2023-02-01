"""Configure pytest for D-Link tests."""

from collections.abc import Awaitable, Callable, Generator
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components import dhcp
from homeassistant.components.dlink.const import CONF_USE_LEGACY_PROTOCOL, DOMAIN
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

HOST = "1.2.3.4"
PASSWORD = "123456"
MAC = format_mac("AA:BB:CC:DD:EE:FF")
USERNAME = "admin"

CONF_DHCP_DATA = {
    CONF_USERNAME: USERNAME,
    CONF_PASSWORD: PASSWORD,
    CONF_USE_LEGACY_PROTOCOL: True,
}

CONF_DATA = CONF_DHCP_DATA | {CONF_HOST: HOST}

CONF_IMPORT_DATA = CONF_DATA | {CONF_NAME: "Smart Plug"}

CONF_DHCP_FLOW = dhcp.DhcpServiceInfo(
    ip=HOST,
    macaddress=MAC,
    hostname="dsp-w215",
)

CONF_DHCP_FLOW_NEW_IP = dhcp.DhcpServiceInfo(
    ip="5.6.7.8",
    macaddress=MAC,
    hostname="dsp-w215",
)

ComponentSetup = Callable[[], Awaitable[None]]


def create_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create fixture for adding config entry in Home Assistant."""
    entry = MockConfigEntry(domain=DOMAIN, data=CONF_DATA)
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add config entry in Home Assistant."""
    return create_entry(hass)


@pytest.fixture
def config_entry_with_uid(hass: HomeAssistant) -> MockConfigEntry:
    """Add config entry with unique ID in Home Assistant."""
    config_entry = create_entry(hass)
    config_entry.unique_id = "aa:bb:cc:dd:ee:ff"
    return config_entry


@pytest.fixture
def mocked_plug() -> MagicMock:
    """Create mocked plug device."""
    mocked_plug = MagicMock()
    mocked_plug.state = "OFF"
    mocked_plug.temperature = "33"
    mocked_plug.current_consumption = "50"
    mocked_plug.total_consumption = "1040"
    mocked_plug.authenticated = None
    mocked_plug.use_legacy_protocol = False
    mocked_plug.model_name = "DSP-W215"
    return mocked_plug


@pytest.fixture
def mocked_plug_legacy() -> MagicMock:
    """Create mocked legacy plug device."""
    mocked_plug = MagicMock()
    mocked_plug.state = "OFF"
    mocked_plug.temperature = "N/A"
    mocked_plug.current_consumption = "N/A"
    mocked_plug.total_consumption = "N/A"
    mocked_plug.authenticated = ("0123456789ABCDEF0123456789ABCDEF", "ABCDefGHiJ")
    mocked_plug.use_legacy_protocol = True
    mocked_plug.model_name = "DSP-W215"
    return mocked_plug


@pytest.fixture
def mocked_plug_legacy_no_auth(mocked_plug_legacy: MagicMock) -> MagicMock:
    """Create mocked legacy unauthenticated plug device."""
    mocked_plug_legacy = deepcopy(mocked_plug_legacy)
    mocked_plug_legacy.authenticated = None
    return mocked_plug_legacy


def patch_config_flow(mocked_plug: MagicMock):
    """Patch D-Link Smart Plug config flow."""
    return patch(
        "homeassistant.components.dlink.config_flow.SmartPlug",
        return_value=mocked_plug,
    )


def patch_setup(mocked_plug: MagicMock):
    """Patch D-Link Smart Plug object."""
    return patch(
        "homeassistant.components.dlink.SmartPlug",
        return_value=mocked_plug,
    )


async def mock_setup_integration(
    hass: HomeAssistant,
    mocked_plug: MagicMock,
) -> None:
    """Set up the D-Link integration in Home Assistant."""
    with patch_setup(mocked_plug):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    config_entry_with_uid: MockConfigEntry,
    mocked_plug: MagicMock,
) -> Generator[ComponentSetup, None, None]:
    """Set up the D-Link integration in Home Assistant."""

    async def func() -> None:
        await mock_setup_integration(hass, mocked_plug)

    return func


@pytest.fixture
async def setup_integration_legacy(
    hass: HomeAssistant,
    config_entry_with_uid: MockConfigEntry,
    mocked_plug_legacy: MagicMock,
) -> Generator[ComponentSetup, None, None]:
    """Set up the D-Link integration in Home Assistant with different data."""

    async def func() -> None:
        await mock_setup_integration(hass, mocked_plug_legacy)

    return func
