"""Tests for Transmission config flow."""
from unittest.mock import patch

import pytest
from transmissionrpc.error import TransmissionError

from homeassistant import config_entries, data_entry_flow
from homeassistant.components import transmission
from homeassistant.components.transmission import config_flow
from homeassistant.components.transmission.const import DEFAULT_SCAN_INTERVAL
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)

from tests.common import MockConfigEntry

NAME = "Transmission"
HOST = "192.168.1.100"
USERNAME = "username"
PASSWORD = "password"
PORT = 9091
SCAN_INTERVAL = 10

MOCK_ENTRY = {
    CONF_NAME: NAME,
    CONF_HOST: HOST,
    CONF_USERNAME: USERNAME,
    CONF_PASSWORD: PASSWORD,
    CONF_PORT: PORT,
}


@pytest.fixture(name="api")
def mock_transmission_api():
    """Mock an api."""
    with patch("transmissionrpc.Client"):
        yield


@pytest.fixture(name="auth_error")
def mock_api_authentication_error():
    """Mock an api."""
    with patch(
        "transmissionrpc.Client", side_effect=TransmissionError("401: Unauthorized")
    ):
        yield


@pytest.fixture(name="conn_error")
def mock_api_connection_error():
    """Mock an api."""
    with patch(
        "transmissionrpc.Client",
        side_effect=TransmissionError("111: Connection refused"),
    ):
        yield


@pytest.fixture(name="unknown_error")
def mock_api_unknown_error():
    """Mock an api."""
    with patch("transmissionrpc.Client", side_effect=TransmissionError):
        yield


@pytest.fixture(name="transmission_setup", autouse=True)
def transmission_setup_fixture():
    """Mock transmission entry setup."""
    with patch(
        "homeassistant.components.transmission.async_setup_entry", return_value=True
    ):
        yield


def init_config_flow(hass):
    """Init a configuration flow."""
    flow = config_flow.TransmissionFlowHandler()
    flow.hass = hass
    return flow


async def test_flow_user_config(hass, api):
    """Test user config."""
    result = await hass.config_entries.flow.async_init(
        transmission.DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_flow_required_fields(hass, api):
    """Test with required fields only."""
    result = await hass.config_entries.flow.async_init(
        transmission.DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_NAME: NAME, CONF_HOST: HOST, CONF_PORT: PORT},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"][CONF_NAME] == NAME
    assert result["data"][CONF_HOST] == HOST
    assert result["data"][CONF_PORT] == PORT


async def test_flow_all_provided(hass, api):
    """Test with all provided."""
    result = await hass.config_entries.flow.async_init(
        transmission.DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=MOCK_ENTRY,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"][CONF_NAME] == NAME
    assert result["data"][CONF_HOST] == HOST
    assert result["data"][CONF_USERNAME] == USERNAME
    assert result["data"][CONF_PASSWORD] == PASSWORD
    assert result["data"][CONF_PORT] == PORT


async def test_options(hass):
    """Test updating options."""
    entry = MockConfigEntry(
        domain=transmission.DOMAIN,
        title=CONF_NAME,
        data=MOCK_ENTRY,
        options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
    )
    flow = init_config_flow(hass)
    options_flow = flow.async_get_options_flow(entry)

    result = await options_flow.async_step_init()
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await options_flow.async_step_init({CONF_SCAN_INTERVAL: 10})
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SCAN_INTERVAL] == 10


async def test_host_already_configured(hass, api):
    """Test host is already configured."""
    entry = MockConfigEntry(
        domain=transmission.DOMAIN,
        data=MOCK_ENTRY,
        options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
    )
    entry.add_to_hass(hass)

    mock_entry_unique_name = MOCK_ENTRY.copy()
    mock_entry_unique_name[CONF_NAME] = "Transmission 1"
    result = await hass.config_entries.flow.async_init(
        transmission.DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=mock_entry_unique_name,
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"

    mock_entry_unique_port = MOCK_ENTRY.copy()
    mock_entry_unique_port[CONF_PORT] = 9092
    mock_entry_unique_port[CONF_NAME] = "Transmission 2"
    result = await hass.config_entries.flow.async_init(
        transmission.DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=mock_entry_unique_port,
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    mock_entry_unique_host = MOCK_ENTRY.copy()
    mock_entry_unique_host[CONF_HOST] = "192.168.1.101"
    mock_entry_unique_host[CONF_NAME] = "Transmission 3"
    result = await hass.config_entries.flow.async_init(
        transmission.DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=mock_entry_unique_host,
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_name_already_configured(hass, api):
    """Test name is already configured."""
    entry = MockConfigEntry(
        domain=transmission.DOMAIN,
        data=MOCK_ENTRY,
        options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
    )
    entry.add_to_hass(hass)

    mock_entry = MOCK_ENTRY.copy()
    mock_entry[CONF_HOST] = "0.0.0.0"
    result = await hass.config_entries.flow.async_init(
        transmission.DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=mock_entry,
    )

    assert result["type"] == "form"
    assert result["errors"] == {CONF_NAME: "name_exists"}


async def test_error_on_wrong_credentials(hass, auth_error):
    """Test with wrong credentials."""
    flow = init_config_flow(hass)

    result = await flow.async_step_user(
        {
            CONF_NAME: NAME,
            CONF_HOST: HOST,
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_PORT: PORT,
        }
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {
        CONF_USERNAME: "invalid_auth",
        CONF_PASSWORD: "invalid_auth",
    }


async def test_error_on_connection_failure(hass, conn_error):
    """Test when connection to host fails."""
    flow = init_config_flow(hass)

    result = await flow.async_step_user(
        {
            CONF_NAME: NAME,
            CONF_HOST: HOST,
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_PORT: PORT,
        }
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_error_on_unknown_error(hass, unknown_error):
    """Test when connection to host fails."""
    flow = init_config_flow(hass)

    result = await flow.async_step_user(
        {
            CONF_NAME: NAME,
            CONF_HOST: HOST,
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_PORT: PORT,
        }
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_success(hass, api):
    """Test we can reauth."""
    entry = MockConfigEntry(
        domain=transmission.DOMAIN,
        data=MOCK_ENTRY,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        transmission.DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=MOCK_ENTRY,
    )

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"] == {CONF_USERNAME: USERNAME}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PASSWORD: "test-password",
        },
    )

    assert result2["type"] == "abort"
    assert result2["reason"] == "reauth_successful"


async def test_reauth_failed(hass, auth_error):
    """Test we can reauth."""
    entry = MockConfigEntry(
        domain=transmission.DOMAIN,
        data=MOCK_ENTRY,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        transmission.DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=MOCK_ENTRY,
    )

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PASSWORD: "test-wrong-password",
        },
    )

    assert result2["type"] == "form"
    assert result2["errors"] == {
        CONF_PASSWORD: "invalid_auth",
    }


async def test_reauth_failed_conn_error(hass, conn_error):
    """Test we can reauth."""
    entry = MockConfigEntry(
        domain=transmission.DOMAIN,
        data=MOCK_ENTRY,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        transmission.DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=MOCK_ENTRY,
    )

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PASSWORD: "test-wrong-password",
        },
    )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "cannot_connect"}
