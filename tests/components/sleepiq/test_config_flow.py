"""Tests for the SleepIQ config flow."""
from unittest.mock import patch

from asyncsleepiq import SleepIQLoginException, SleepIQTimeoutException

from homeassistant import config_entries, data_entry_flow, setup
from homeassistant.components.sleepiq.const import DOMAIN
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

SLEEPIQ_CONFIG = {
    CONF_USERNAME: "username",
    CONF_PASSWORD: "password",
}


async def test_import(hass: HomeAssistant) -> None:
    """Test that we can import a config entry."""
    with patch("asyncsleepiq.AsyncSleepIQ.login"):
        assert await setup.async_setup_component(hass, DOMAIN, {DOMAIN: SLEEPIQ_CONFIG})
        await hass.async_block_till_done()

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data[CONF_USERNAME] == SLEEPIQ_CONFIG[CONF_USERNAME]
    assert entry.data[CONF_PASSWORD] == SLEEPIQ_CONFIG[CONF_PASSWORD]


async def test_show_set_form(hass: HomeAssistant) -> None:
    """Test that the setup form is served."""
    with patch("asyncsleepiq.AsyncSleepIQ.login"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=None
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "user"


async def test_login_invalid_auth(hass: HomeAssistant) -> None:
    """Test we show user form with appropriate error on login failure."""
    with patch(
        "asyncsleepiq.AsyncSleepIQ.login",
        side_effect=SleepIQLoginException,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=SLEEPIQ_CONFIG
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "invalid_auth"}


async def test_login_cannot_connect(hass: HomeAssistant) -> None:
    """Test we show user form with appropriate error on login failure."""
    with patch(
        "asyncsleepiq.AsyncSleepIQ.login",
        side_effect=SleepIQTimeoutException,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=SLEEPIQ_CONFIG
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "cannot_connect"}


async def test_success(hass: HomeAssistant) -> None:
    """Test successful flow provides entry creation data."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch("asyncsleepiq.AsyncSleepIQ.login", return_value=True), patch(
        "homeassistant.components.sleepiq.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], SLEEPIQ_CONFIG
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result2["data"][CONF_USERNAME] == SLEEPIQ_CONFIG[CONF_USERNAME]
    assert result2["data"][CONF_PASSWORD] == SLEEPIQ_CONFIG[CONF_PASSWORD]
    assert len(mock_setup_entry.mock_calls) == 1
