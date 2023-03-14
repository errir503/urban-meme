"""Test the Coronavirus config flow."""
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientError
import pytest

from homeassistant import config_entries
from homeassistant.components.coronavirus.const import DOMAIN, OPTION_WORLDWIDE
from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def test_form(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Test we get the form."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"country": OPTION_WORLDWIDE},
    )
    assert result2["type"] == "create_entry"
    assert result2["title"] == "Worldwide"
    assert result2["result"].unique_id == OPTION_WORLDWIDE
    assert result2["data"] == {
        "country": OPTION_WORLDWIDE,
    }
    await hass.async_block_till_done()
    mock_setup_entry.assert_called_once()


@patch(
    "coronavirus.get_cases",
    side_effect=ClientError,
)
async def test_abort_on_connection_error(
    mock_get_cases: MagicMock, hass: HomeAssistant
) -> None:
    """Test we abort on connection error."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert "type" in result
    assert result["type"] == "abort"
    assert "reason" in result
    assert result["reason"] == "cannot_connect"
