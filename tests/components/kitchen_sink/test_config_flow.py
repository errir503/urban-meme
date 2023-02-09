"""Test the Everything but the Kitchen Sink config flow."""
from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow, setup
from homeassistant.components.kitchen_sink import DOMAIN
from homeassistant.core import HomeAssistant


async def test_import(hass: HomeAssistant) -> None:
    """Test that we can import a config entry."""
    with patch("homeassistant.components.kitchen_sink.async_setup_entry"):
        assert await setup.async_setup_component(hass, DOMAIN, {DOMAIN: {}})
        await hass.async_block_till_done()

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data == {}


async def test_import_once(hass: HomeAssistant) -> None:
    """Test that we don't create multiple config entries."""
    with patch(
        "homeassistant.components.kitchen_sink.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={},
        )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kitchen Sink"
    assert result["data"] == {}
    assert result["options"] == {}
    mock_setup_entry.assert_called_once()

    # Test importing again doesn't create a 2nd entry
    with patch(
        "homeassistant.components.kitchen_sink.async_setup_entry"
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={},
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
    mock_setup_entry.assert_not_called()
