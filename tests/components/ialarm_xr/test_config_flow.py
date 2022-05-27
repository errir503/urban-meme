"""Test the Antifurto365 iAlarmXR config flow."""

from unittest.mock import patch

from pyialarmxr import IAlarmXRGenericException, IAlarmXRSocketTimeoutException

from homeassistant import config_entries, data_entry_flow
from homeassistant.components.ialarm_xr.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

from tests.common import MockConfigEntry

TEST_DATA = {
    CONF_HOST: "1.1.1.1",
    CONF_PORT: 18034,
    CONF_USERNAME: "000ZZZ0Z00",
    CONF_PASSWORD: "00000000",
}

TEST_MAC = "00:00:54:12:34:56"


async def test_form(hass):
    """Test we get the form."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["handler"] == "ialarm_xr"
    assert result["data_schema"].schema.get("host") == str
    assert result["data_schema"].schema.get("port") == int
    assert result["data_schema"].schema.get("password") == str
    assert result["data_schema"].schema.get("username") == str
    assert result["errors"] == {}

    with patch(
        "homeassistant.components.ialarm_xr.config_flow.IAlarmXR.get_status",
        return_value=1,
    ), patch(
        "homeassistant.components.ialarm_xr.config_flow.IAlarmXR.get_mac",
        return_value=TEST_MAC,
    ), patch(
        "homeassistant.components.ialarm_xr.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result2["title"] == TEST_DATA["host"]
    assert result2["data"] == TEST_DATA
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_cannot_connect(hass):
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.ialarm_xr.config_flow.IAlarmXR.get_mac",
        side_effect=ConnectionError,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_exception(hass):
    """Test we handle unknown exception."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.ialarm_xr.config_flow.IAlarmXR.get_mac",
        side_effect=Exception,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["errors"] == {"base": "unknown"}


async def test_form_cannot_connect_throwing_connection_error(hass):
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.ialarm_xr.config_flow.IAlarmXR.get_mac",
        side_effect=ConnectionError,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_cannot_connect_throwing_socket_timeout_exception(hass):
    """Test we handle cannot connect error because of socket timeout."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.ialarm_xr.config_flow.IAlarmXR.get_mac",
        side_effect=IAlarmXRSocketTimeoutException,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["errors"] == {"base": "unknown"}


async def test_form_cannot_connect_throwing_generic_exception(hass):
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.ialarm_xr.config_flow.IAlarmXR.get_mac",
        side_effect=IAlarmXRGenericException,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["errors"] == {"base": "unknown"}


async def test_form_already_exists(hass):
    """Test that a flow with an existing host aborts."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_MAC,
        data=TEST_DATA,
    )

    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.ialarm_xr.config_flow.IAlarmXR.get_mac",
        return_value=TEST_MAC,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )

    assert result2["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result2["reason"] == "already_configured"


async def test_flow_user_step_no_input(hass):
    """Test appropriate error when no input is provided."""
    _result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        _result["flow_id"], user_input=None
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == config_entries.SOURCE_USER
    assert result["errors"] == {}
