"""Test the Waze Travel Time config flow."""
import pytest

from homeassistant import config_entries, data_entry_flow
from homeassistant.components.waze_travel_time.const import (
    CONF_AVOID_FERRIES,
    CONF_AVOID_SUBSCRIPTION_ROADS,
    CONF_AVOID_TOLL_ROADS,
    CONF_DESTINATION,
    CONF_EXCL_FILTER,
    CONF_INCL_FILTER,
    CONF_ORIGIN,
    CONF_REALTIME,
    CONF_UNITS,
    CONF_VEHICLE_TYPE,
    DEFAULT_NAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    IMPERIAL_UNITS,
)
from homeassistant.const import CONF_NAME, CONF_REGION
from homeassistant.core import HomeAssistant

from .const import MOCK_CONFIG

from tests.common import MockConfigEntry


@pytest.mark.usefixtures("validate_config_entry")
async def test_minimum_fields(hass: HomeAssistant) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        MOCK_CONFIG,
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == DEFAULT_NAME
    assert result2["data"] == {
        CONF_NAME: DEFAULT_NAME,
        CONF_ORIGIN: "location1",
        CONF_DESTINATION: "location2",
        CONF_REGION: "US",
    }


async def test_options(hass: HomeAssistant) -> None:
    """Test options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options=DEFAULT_OPTIONS,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id, data=None)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_AVOID_FERRIES: True,
            CONF_AVOID_SUBSCRIPTION_ROADS: True,
            CONF_AVOID_TOLL_ROADS: True,
            CONF_EXCL_FILTER: "exclude",
            CONF_INCL_FILTER: "include",
            CONF_REALTIME: False,
            CONF_UNITS: IMPERIAL_UNITS,
            CONF_VEHICLE_TYPE: "taxi",
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == ""
    assert result["data"] == {
        CONF_AVOID_FERRIES: True,
        CONF_AVOID_SUBSCRIPTION_ROADS: True,
        CONF_AVOID_TOLL_ROADS: True,
        CONF_EXCL_FILTER: "exclude",
        CONF_INCL_FILTER: "include",
        CONF_REALTIME: False,
        CONF_UNITS: IMPERIAL_UNITS,
        CONF_VEHICLE_TYPE: "taxi",
    }

    assert entry.options == {
        CONF_AVOID_FERRIES: True,
        CONF_AVOID_SUBSCRIPTION_ROADS: True,
        CONF_AVOID_TOLL_ROADS: True,
        CONF_EXCL_FILTER: "exclude",
        CONF_INCL_FILTER: "include",
        CONF_REALTIME: False,
        CONF_UNITS: IMPERIAL_UNITS,
        CONF_VEHICLE_TYPE: "taxi",
    }


@pytest.mark.usefixtures("validate_config_entry")
async def test_dupe(hass: HomeAssistant) -> None:
    """Test setting up the same entry data twice is OK."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        MOCK_CONFIG,
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        MOCK_CONFIG,
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("invalidate_config_entry")
async def test_invalid_config_entry(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {}
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        MOCK_CONFIG,
    )

    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}

    assert "Error trying to validate entry" in caplog.text


@pytest.mark.usefixtures("mock_update")
async def test_reset_filters(hass: HomeAssistant) -> None:
    """Test resetting inclusive and exclusive filters to empty string."""
    options = {**DEFAULT_OPTIONS}
    options[CONF_INCL_FILTER] = "test"
    options[CONF_EXCL_FILTER] = "test"
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, options=options, entry_id="test"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(
        config_entry.entry_id, data=None
    )

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_AVOID_FERRIES: True,
            CONF_AVOID_SUBSCRIPTION_ROADS: True,
            CONF_AVOID_TOLL_ROADS: True,
            CONF_EXCL_FILTER: "",
            CONF_INCL_FILTER: "",
            CONF_REALTIME: False,
            CONF_UNITS: IMPERIAL_UNITS,
            CONF_VEHICLE_TYPE: "taxi",
        },
    )

    assert config_entry.options == {
        CONF_AVOID_FERRIES: True,
        CONF_AVOID_SUBSCRIPTION_ROADS: True,
        CONF_AVOID_TOLL_ROADS: True,
        CONF_EXCL_FILTER: "",
        CONF_INCL_FILTER: "",
        CONF_REALTIME: False,
        CONF_UNITS: IMPERIAL_UNITS,
        CONF_VEHICLE_TYPE: "taxi",
    }
