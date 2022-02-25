"""Test the Sense config flow."""
from unittest.mock import AsyncMock, patch

import pytest
from sense_energy import (
    SenseAPITimeoutException,
    SenseAuthenticationException,
    SenseMFARequiredException,
)

from homeassistant import config_entries
from homeassistant.components.sense.const import DOMAIN
from homeassistant.const import CONF_CODE

from tests.common import MockConfigEntry

MOCK_CONFIG = {
    "timeout": 6,
    "email": "test-email",
    "password": "test-password",
    "access_token": "ABC",
    "user_id": "123",
    "monitor_id": "456",
}


@pytest.fixture(name="mock_sense")
def mock_sense():
    """Mock Sense object for authenticatation."""
    with patch(
        "homeassistant.components.sense.config_flow.ASyncSenseable"
    ) as mock_sense:
        mock_sense.return_value.authenticate = AsyncMock(return_value=True)
        mock_sense.return_value.validate_mfa = AsyncMock(return_value=True)
        mock_sense.return_value.sense_access_token = "ABC"
        mock_sense.return_value.sense_user_id = "123"
        mock_sense.return_value.sense_monitor_id = "456"
        yield mock_sense


async def test_form(hass, mock_sense):
    """Test we get the form."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch(
        "homeassistant.components.sense.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"timeout": "6", "email": "test-email", "password": "test-password"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "test-email"
    assert result2["data"] == MOCK_CONFIG
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_invalid_auth(hass):
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "sense_energy.ASyncSenseable.authenticate",
        side_effect=SenseAuthenticationException,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"timeout": "6", "email": "test-email", "password": "test-password"},
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_form_mfa_required(hass, mock_sense):
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_sense.return_value.authenticate.side_effect = SenseMFARequiredException

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"timeout": "6", "email": "test-email", "password": "test-password"},
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "validation"

    mock_sense.return_value.validate_mfa.side_effect = None
    result3 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CODE: "012345"},
    )

    assert result3["type"] == "create_entry"
    assert result3["title"] == "test-email"
    assert result3["data"] == MOCK_CONFIG


async def test_form_mfa_required_wrong(hass, mock_sense):
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_sense.return_value.authenticate.side_effect = SenseMFARequiredException

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"timeout": "6", "email": "test-email", "password": "test-password"},
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "validation"

    mock_sense.return_value.validate_mfa.side_effect = SenseAuthenticationException
    # Try with the WRONG verification code give us the form back again
    result3 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CODE: "000000"},
    )

    assert result3["type"] == "form"
    assert result3["errors"] == {"base": "invalid_auth"}
    assert result3["step_id"] == "validation"


async def test_form_mfa_required_timeout(hass, mock_sense):
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_sense.return_value.authenticate.side_effect = SenseMFARequiredException

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"timeout": "6", "email": "test-email", "password": "test-password"},
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "validation"

    mock_sense.return_value.validate_mfa.side_effect = SenseAPITimeoutException
    result3 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CODE: "000000"},
    )

    assert result3["type"] == "form"
    assert result3["errors"] == {"base": "cannot_connect"}


async def test_form_mfa_required_exception(hass, mock_sense):
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_sense.return_value.authenticate.side_effect = SenseMFARequiredException

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"timeout": "6", "email": "test-email", "password": "test-password"},
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "validation"

    mock_sense.return_value.validate_mfa.side_effect = Exception
    result3 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CODE: "000000"},
    )

    assert result3["type"] == "form"
    assert result3["errors"] == {"base": "unknown"}


async def test_form_cannot_connect(hass):
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "sense_energy.ASyncSenseable.authenticate",
        side_effect=SenseAPITimeoutException,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"timeout": "6", "email": "test-email", "password": "test-password"},
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_unknown_exception(hass):
    """Test we handle unknown error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "sense_energy.ASyncSenseable.authenticate",
        side_effect=Exception,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"timeout": "6", "email": "test-email", "password": "test-password"},
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "unknown"}


async def test_reauth_no_form(hass, mock_sense):
    """Test reauth where no form needed."""

    # set up initially
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-email",
    )
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_REAUTH}, data=MOCK_CONFIG
        )
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"


async def test_reauth_password(hass, mock_sense):
    """Test reauth form."""

    # set up initially
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="test-email",
    )
    entry.add_to_hass(hass)
    mock_sense.return_value.authenticate.side_effect = SenseAuthenticationException

    # Reauth success without user input
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_REAUTH}, data=entry.data
    )
    assert result["type"] == "form"

    mock_sense.return_value.authenticate.side_effect = None
    with patch(
        "homeassistant.components.sense.async_setup_entry",
        return_value=True,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "test-password"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reauth_successful"
