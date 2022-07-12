"""Test the Risco config flow."""
from unittest.mock import PropertyMock, patch

import pytest
import voluptuous as vol

from homeassistant import config_entries, data_entry_flow
from homeassistant.components.risco.config_flow import (
    CannotConnectError,
    UnauthorizedError,
)
from homeassistant.components.risco.const import DOMAIN

from tests.common import MockConfigEntry

TEST_SITE_NAME = "test-site-name"
TEST_DATA = {
    "username": "test-username",
    "password": "test-password",
    "pin": "1234",
}

TEST_RISCO_TO_HA = {
    "arm": "armed_away",
    "partial_arm": "armed_home",
    "A": "armed_home",
    "B": "armed_home",
    "C": "armed_night",
    "D": "armed_night",
}

TEST_HA_TO_RISCO = {
    "armed_away": "arm",
    "armed_home": "partial_arm",
    "armed_night": "C",
}

TEST_OPTIONS = {
    "scan_interval": 10,
    "code_arm_required": True,
    "code_disarm_required": True,
}


async def test_form(hass):
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch(
        "homeassistant.components.risco.config_flow.RiscoAPI.login",
        return_value=True,
    ), patch(
        "homeassistant.components.risco.config_flow.RiscoAPI.site_name",
        new_callable=PropertyMock(return_value=TEST_SITE_NAME),
    ), patch(
        "homeassistant.components.risco.config_flow.RiscoAPI.close"
    ) as mock_close, patch(
        "homeassistant.components.risco.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == TEST_SITE_NAME
    assert result2["data"] == TEST_DATA
    assert len(mock_setup_entry.mock_calls) == 1
    mock_close.assert_awaited_once()


async def test_form_invalid_auth(hass):
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.risco.config_flow.RiscoAPI.login",
        side_effect=UnauthorizedError,
    ), patch("homeassistant.components.risco.config_flow.RiscoAPI.close") as mock_close:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "invalid_auth"}
    mock_close.assert_awaited_once()


async def test_form_cannot_connect(hass):
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.risco.config_flow.RiscoAPI.login",
        side_effect=CannotConnectError,
    ), patch("homeassistant.components.risco.config_flow.RiscoAPI.close") as mock_close:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "cannot_connect"}
    mock_close.assert_awaited_once()


async def test_form_exception(hass):
    """Test we handle unknown exception."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.risco.config_flow.RiscoAPI.login",
        side_effect=Exception,
    ), patch("homeassistant.components.risco.config_flow.RiscoAPI.close") as mock_close:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], TEST_DATA
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "unknown"}
    mock_close.assert_awaited_once()


async def test_form_already_exists(hass):
    """Test that a flow with an existing username aborts."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_DATA["username"],
        data=TEST_DATA,
    )

    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], TEST_DATA
    )

    assert result2["type"] == "abort"
    assert result2["reason"] == "already_configured"


async def test_options_flow(hass):
    """Test options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_DATA["username"],
        data=TEST_DATA,
    )

    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=TEST_OPTIONS,
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "risco_to_ha"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=TEST_RISCO_TO_HA,
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "ha_to_risco"

    with patch("homeassistant.components.risco.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=TEST_HA_TO_RISCO,
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.options == {
        **TEST_OPTIONS,
        "risco_states_to_ha": TEST_RISCO_TO_HA,
        "ha_states_to_risco": TEST_HA_TO_RISCO,
    }


async def test_ha_to_risco_schema(hass):
    """Test that the schema for the ha-to-risco mapping step is generated properly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_DATA["username"],
        data=TEST_DATA,
    )

    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=TEST_OPTIONS,
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=TEST_RISCO_TO_HA,
    )

    # Test an HA state that isn't used
    with pytest.raises(vol.error.MultipleInvalid):
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={**TEST_HA_TO_RISCO, "armed_custom_bypass": "D"},
        )

    # Test a combo that can't be selected
    with pytest.raises(vol.error.MultipleInvalid):
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={**TEST_HA_TO_RISCO, "armed_night": "A"},
        )
