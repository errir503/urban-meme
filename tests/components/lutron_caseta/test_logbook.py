"""The tests for lutron caseta logbook."""
from unittest.mock import patch

from homeassistant.components.lutron_caseta.const import (
    ATTR_ACTION,
    ATTR_AREA_NAME,
    ATTR_BUTTON_NUMBER,
    ATTR_DEVICE_NAME,
    ATTR_LEAP_BUTTON_NUMBER,
    ATTR_SERIAL,
    ATTR_TYPE,
    CONF_CA_CERTS,
    CONF_CERTFILE,
    CONF_KEYFILE,
    DOMAIN,
    LUTRON_CASETA_BUTTON_EVENT,
)
from homeassistant.const import ATTR_DEVICE_ID, CONF_HOST
from homeassistant.setup import async_setup_component

from . import MockBridge

from tests.common import MockConfigEntry
from tests.components.logbook.common import MockRow, mock_humanify


async def test_humanify_lutron_caseta_button_event(hass):
    """Test humanifying lutron_caseta_button_events."""
    hass.config.components.add("recorder")
    assert await async_setup_component(hass, "logbook", {})
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "1.1.1.1",
            CONF_KEYFILE: "",
            CONF_CERTFILE: "",
            CONF_CA_CERTS: "",
        },
        unique_id="abc",
    )
    config_entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.lutron_caseta.Smartbridge.create_tls",
        return_value=MockBridge(can_connect=True),
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    await hass.async_block_till_done()

    (event1,) = mock_humanify(
        hass,
        [
            MockRow(
                LUTRON_CASETA_BUTTON_EVENT,
                {
                    ATTR_SERIAL: "123",
                    ATTR_DEVICE_ID: "1234",
                    ATTR_TYPE: "Pico3ButtonRaiseLower",
                    ATTR_LEAP_BUTTON_NUMBER: 3,
                    ATTR_BUTTON_NUMBER: 3,
                    ATTR_DEVICE_NAME: "Pico",
                    ATTR_AREA_NAME: "Living Room",
                    ATTR_ACTION: "press",
                },
            ),
        ],
    )

    assert event1["name"] == "Living Room Pico"
    assert event1["domain"] == DOMAIN
    assert event1["message"] == "press raise"
