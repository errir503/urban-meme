# flake8: noqa pylint: skip-file
"""Tests for the TelldusLive config flow."""
import asyncio
from unittest.mock import Mock, patch

import pytest

from homeassistant import data_entry_flow
from homeassistant.components.tellduslive import (
    APPLICATION_NAME,
    DOMAIN,
    KEY_SCAN_INTERVAL,
    SCAN_INTERVAL,
    config_flow,
)
from homeassistant.config_entries import SOURCE_DISCOVERY
from homeassistant.const import CONF_HOST

from tests.common import MockConfigEntry, mock_coro


def init_config_flow(hass, side_effect=None):
    """Init a configuration flow."""
    flow = config_flow.FlowHandler()
    flow.hass = hass
    if side_effect:
        flow._get_auth_url = Mock(side_effect=side_effect)
    return flow


@pytest.fixture
def supports_local_api():
    """Set TelldusLive supports_local_api."""
    return True


@pytest.fixture
def authorize():
    """Set TelldusLive authorize."""
    return True


@pytest.fixture
def mock_tellduslive(supports_local_api, authorize):
    """Mock tellduslive."""
    with patch(
        "homeassistant.components.tellduslive.config_flow.Session"
    ) as Session, patch(
        "homeassistant.components.tellduslive.config_flow.supports_local_api"
    ) as tellduslive_supports_local_api:
        tellduslive_supports_local_api.return_value = supports_local_api
        Session().authorize.return_value = authorize
        Session().access_token = "token"
        Session().access_token_secret = "token_secret"
        Session().authorize_url = "https://example.com"
        yield Session, tellduslive_supports_local_api


async def test_abort_if_already_setup(hass):
    """Test we abort if TelldusLive is already setup."""
    flow = init_config_flow(hass)

    with patch.object(hass.config_entries, "async_entries", return_value=[{}]):
        result = await flow.async_step_user()
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_setup"

    with patch.object(hass.config_entries, "async_entries", return_value=[{}]):
        result = await flow.async_step_import(None)
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_setup"


async def test_full_flow_implementation(hass, mock_tellduslive):
    """Test registering an implementation and finishing flow works."""
    flow = init_config_flow(hass)
    flow.context = {"source": SOURCE_DISCOVERY}
    result = await flow.async_step_discovery(["localhost", "tellstick"])
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert len(flow._hosts) == 2

    result = await flow.async_step_user()
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await flow.async_step_user({"host": "localhost"})
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "auth"
    assert result["description_placeholders"] == {
        "auth_url": "https://example.com",
        "app_name": APPLICATION_NAME,
    }

    result = await flow.async_step_auth("")
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "localhost"
    assert result["data"]["host"] == "localhost"
    assert result["data"]["scan_interval"] == 60
    assert result["data"]["session"] == {"token": "token", "host": "localhost"}


async def test_step_import(hass, mock_tellduslive):
    """Test that we trigger auth when configuring from import."""
    flow = init_config_flow(hass)

    result = await flow.async_step_import({CONF_HOST: DOMAIN, KEY_SCAN_INTERVAL: 0})
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "auth"


async def test_step_import_add_host(hass, mock_tellduslive):
    """Test that we add host and trigger user when configuring from import."""
    flow = init_config_flow(hass)

    result = await flow.async_step_import(
        {CONF_HOST: "localhost", KEY_SCAN_INTERVAL: 0}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_step_import_no_config_file(hass, mock_tellduslive):
    """Test that we trigger user with no config_file configuring from import."""
    flow = init_config_flow(hass)

    result = await flow.async_step_import(
        {CONF_HOST: "localhost", KEY_SCAN_INTERVAL: 0}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_step_import_load_json_matching_host(hass, mock_tellduslive):
    """Test that we add host and trigger user when configuring from import."""
    flow = init_config_flow(hass)

    with patch(
        "homeassistant.components.tellduslive.config_flow.load_json",
        return_value={"tellduslive": {}},
    ), patch("os.path.isfile"):
        result = await flow.async_step_import(
            {CONF_HOST: "Cloud API", KEY_SCAN_INTERVAL: 0}
        )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_step_import_load_json(hass, mock_tellduslive):
    """Test that we create entry when configuring from import."""
    flow = init_config_flow(hass)

    with patch(
        "homeassistant.components.tellduslive.config_flow.load_json",
        return_value={"localhost": {}},
    ), patch("os.path.isfile"):
        result = await flow.async_step_import(
            {CONF_HOST: "localhost", KEY_SCAN_INTERVAL: SCAN_INTERVAL}
        )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "localhost"
    assert result["data"]["host"] == "localhost"
    assert result["data"]["scan_interval"] == 60
    assert result["data"]["session"] == {}


@pytest.mark.parametrize("supports_local_api", [False])
async def test_step_disco_no_local_api(hass, mock_tellduslive):
    """Test that we trigger when configuring from discovery, not supporting local api."""
    flow = init_config_flow(hass)
    flow.context = {"source": SOURCE_DISCOVERY}

    result = await flow.async_step_discovery(["localhost", "tellstick"])
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "auth"
    assert len(flow._hosts) == 1


async def test_step_auth(hass, mock_tellduslive):
    """Test that create cloud entity from auth."""
    flow = init_config_flow(hass)

    await flow.async_step_auth()
    result = await flow.async_step_auth(["localhost", "tellstick"])
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Cloud API"
    assert result["data"]["host"] == "Cloud API"
    assert result["data"]["scan_interval"] == 60
    assert result["data"]["session"] == {
        "token": "token",
        "token_secret": "token_secret",
    }


@pytest.mark.parametrize("authorize", [False])
async def test_wrong_auth_flow_implementation(hass, mock_tellduslive):
    """Test wrong auth."""
    flow = init_config_flow(hass)

    await flow.async_step_auth()
    result = await flow.async_step_auth("")
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "auth"
    assert result["errors"]["base"] == "invalid_auth"


async def test_not_pick_host_if_only_one(hass, mock_tellduslive):
    """Test not picking host if we have just one."""
    flow = init_config_flow(hass)

    result = await flow.async_step_user()
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "auth"


async def test_abort_if_timeout_generating_auth_url(hass, mock_tellduslive):
    """Test abort if generating authorize url timeout."""
    flow = init_config_flow(hass, side_effect=asyncio.TimeoutError)

    result = await flow.async_step_user()
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "authorize_url_timeout"


async def test_abort_no_auth_url(hass, mock_tellduslive):
    """Test abort if generating authorize url returns none."""
    flow = init_config_flow(hass)
    flow._get_auth_url = Mock(return_value=False)

    result = await flow.async_step_user()
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "unknown_authorize_url_generation"


async def test_abort_if_exception_generating_auth_url(hass, mock_tellduslive):
    """Test we abort if generating authorize url blows up."""
    flow = init_config_flow(hass, side_effect=ValueError)

    result = await flow.async_step_user()
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "unknown_authorize_url_generation"


async def test_discovery_already_configured(hass, mock_tellduslive):
    """Test abort if already configured fires from discovery."""
    MockConfigEntry(domain="tellduslive", data={"host": "some-host"}).add_to_hass(hass)
    flow = init_config_flow(hass)
    flow.context = {"source": SOURCE_DISCOVERY}

    with pytest.raises(data_entry_flow.AbortFlow):
        result = await flow.async_step_discovery(["some-host", ""])
