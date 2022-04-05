"""Test the Brunt config flow."""
from unittest.mock import Mock, patch

from aiohttp import ClientResponseError
from aiohttp.client_exceptions import ServerDisconnectedError
import pytest

from homeassistant import config_entries, data_entry_flow
from homeassistant.components.brunt.const import DOMAIN
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from tests.common import MockConfigEntry

CONFIG = {CONF_USERNAME: "test-username", CONF_PASSWORD: "test-password"}


async def test_form(hass):
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=None
    )
    assert result["type"] == "form"
    assert result["errors"] is None

    with patch(
        "homeassistant.components.brunt.config_flow.BruntClientAsync.async_login",
        return_value=None,
    ), patch(
        "homeassistant.components.brunt.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            CONFIG,
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result2["title"] == "test-username"
    assert result2["data"] == CONFIG
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_duplicate_login(hass):
    """Test uniqueness of username."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=CONFIG,
        title="test-username",
        unique_id="test-username",
    )
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.brunt.config_flow.BruntClientAsync.async_login",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=CONFIG
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    "side_effect, error_message",
    [
        (ServerDisconnectedError, "cannot_connect"),
        (ClientResponseError(Mock(), None, status=403), "invalid_auth"),
        (ClientResponseError(Mock(), None, status=401), "unknown"),
        (Exception, "unknown"),
    ],
)
async def test_form_error(hass, side_effect, error_message):
    """Test we handle cannot connect."""
    with patch(
        "homeassistant.components.brunt.config_flow.BruntClientAsync.async_login",
        side_effect=side_effect,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=CONFIG
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"] == {"base": error_message}


@pytest.mark.parametrize(
    "side_effect, result_type, password, step_id, reason",
    [
        (None, data_entry_flow.RESULT_TYPE_ABORT, "test", None, "reauth_successful"),
        (
            Exception,
            data_entry_flow.RESULT_TYPE_FORM,
            CONFIG[CONF_PASSWORD],
            "reauth_confirm",
            None,
        ),
    ],
)
async def test_reauth(hass, side_effect, result_type, password, step_id, reason):
    """Test uniqueness of username."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=CONFIG,
        title="test-username",
        unique_id="test-username",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "unique_id": entry.unique_id,
            "entry_id": entry.entry_id,
        },
        data=None,
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "reauth_confirm"
    with patch(
        "homeassistant.components.brunt.config_flow.BruntClientAsync.async_login",
        return_value=None,
        side_effect=side_effect,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"password": "test"},
        )
        assert result3["type"] == result_type
        assert entry.data["password"] == password
        assert result3.get("step_id", None) == step_id
        assert result3.get("reason", None) == reason
