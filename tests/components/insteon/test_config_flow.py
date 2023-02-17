"""Test the config flow for the Insteon integration."""

from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.components import usb
from homeassistant.components.insteon.config_flow import (
    HUB1,
    HUB2,
    MODEM_TYPE,
    PLM,
    STEP_ADD_OVERRIDE,
    STEP_ADD_X10,
    STEP_CHANGE_HUB_CONFIG,
    STEP_CHANGE_PLM_CONFIG,
    STEP_HUB_V2,
    STEP_REMOVE_OVERRIDE,
    STEP_REMOVE_X10,
)
from homeassistant.components.insteon.const import (
    CONF_CAT,
    CONF_DIM_STEPS,
    CONF_HOUSECODE,
    CONF_HUB_VERSION,
    CONF_OVERRIDE,
    CONF_SUBCAT,
    CONF_UNITCODE,
    CONF_X10,
    DOMAIN,
)
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_DEVICE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PLATFORM,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant

from .const import (
    MOCK_HOSTNAME,
    MOCK_IMPORT_CONFIG_PLM,
    MOCK_IMPORT_MINIMUM_HUB_V1,
    MOCK_IMPORT_MINIMUM_HUB_V2,
    MOCK_PASSWORD,
    MOCK_USER_INPUT_HUB_V1,
    MOCK_USER_INPUT_HUB_V2,
    MOCK_USER_INPUT_PLM,
    MOCK_USERNAME,
    PATCH_ASYNC_SETUP,
    PATCH_ASYNC_SETUP_ENTRY,
    PATCH_CONNECTION,
)

from tests.common import MockConfigEntry


async def mock_successful_connection(*args, **kwargs):
    """Return a successful connection."""
    return True


async def mock_failed_connection(*args, **kwargs):
    """Return a failed connection."""
    raise ConnectionError("Connection failed")


async def _init_form(hass, modem_type):
    """Run the user form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {}

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {MODEM_TYPE: modem_type},
    )
    return result2


async def _device_form(hass, flow_id, connection, user_input):
    """Test the PLM, Hub v1 or Hub v2 form."""
    with patch(
        PATCH_CONNECTION,
        new=connection,
    ), patch(PATCH_ASYNC_SETUP, return_value=True) as mock_setup, patch(
        PATCH_ASYNC_SETUP_ENTRY,
        return_value=True,
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(flow_id, user_input)
        await hass.async_block_till_done()
    return result, mock_setup, mock_setup_entry


async def test_form_select_modem(hass: HomeAssistant) -> None:
    """Test we get a modem form."""

    result = await _init_form(hass, HUB2)
    assert result["step_id"] == STEP_HUB_V2
    assert result["type"] == "form"


async def test_fail_on_existing(hass: HomeAssistant) -> None:
    """Test we fail if the integration is already configured."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={},
    )
    config_entry.add_to_hass(hass)
    assert config_entry.state is config_entries.ConfigEntryState.NOT_LOADED

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_form_select_plm(hass: HomeAssistant) -> None:
    """Test we set up the PLM correctly."""

    result = await _init_form(hass, PLM)

    result2, mock_setup, mock_setup_entry = await _device_form(
        hass, result["flow_id"], mock_successful_connection, MOCK_USER_INPUT_PLM
    )
    assert result2["type"] == "create_entry"
    assert result2["data"] == MOCK_USER_INPUT_PLM

    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_select_hub_v1(hass: HomeAssistant) -> None:
    """Test we set up the Hub v1 correctly."""

    result = await _init_form(hass, HUB1)

    result2, mock_setup, mock_setup_entry = await _device_form(
        hass, result["flow_id"], mock_successful_connection, MOCK_USER_INPUT_HUB_V1
    )
    assert result2["type"] == "create_entry"
    assert result2["data"] == {
        **MOCK_USER_INPUT_HUB_V1,
        CONF_HUB_VERSION: 1,
    }

    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_select_hub_v2(hass: HomeAssistant) -> None:
    """Test we set up the Hub v2 correctly."""

    result = await _init_form(hass, HUB2)

    result2, mock_setup, mock_setup_entry = await _device_form(
        hass, result["flow_id"], mock_successful_connection, MOCK_USER_INPUT_HUB_V2
    )
    assert result2["type"] == "create_entry"
    assert result2["data"] == {
        **MOCK_USER_INPUT_HUB_V2,
        CONF_HUB_VERSION: 2,
    }

    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


async def test_failed_connection_plm(hass: HomeAssistant) -> None:
    """Test a failed connection with the PLM."""

    result = await _init_form(hass, PLM)

    result2, _, _ = await _device_form(
        hass, result["flow_id"], mock_failed_connection, MOCK_USER_INPUT_PLM
    )
    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_failed_connection_hub(hass: HomeAssistant) -> None:
    """Test a failed connection with a Hub."""

    result = await _init_form(hass, HUB2)

    result2, _, _ = await _device_form(
        hass, result["flow_id"], mock_failed_connection, MOCK_USER_INPUT_HUB_V2
    )
    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "cannot_connect"}


async def _import_config(hass, config):
    """Run the import step."""
    with patch(
        PATCH_CONNECTION,
        new=mock_successful_connection,
    ), patch(
        PATCH_ASYNC_SETUP, return_value=True
    ), patch(PATCH_ASYNC_SETUP_ENTRY, return_value=True):
        return await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data=config
        )


async def test_import_plm(hass: HomeAssistant) -> None:
    """Test importing a minimum PLM config from yaml."""

    result = await _import_config(hass, MOCK_IMPORT_CONFIG_PLM)

    assert result["type"] == "create_entry"
    assert hass.config_entries.async_entries(DOMAIN)
    for entry in hass.config_entries.async_entries(DOMAIN):
        assert entry.data == MOCK_IMPORT_CONFIG_PLM


async def _options_init_form(hass, entry_id, step):
    """Run the init options form."""
    with patch(PATCH_ASYNC_SETUP_ENTRY, return_value=True):
        result = await hass.config_entries.options.async_init(entry_id)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {step: True},
    )
    return result2


async def test_import_min_hub_v2(hass: HomeAssistant) -> None:
    """Test importing a minimum Hub v2 config from yaml."""

    result = await _import_config(
        hass, {**MOCK_IMPORT_MINIMUM_HUB_V2, CONF_PORT: 25105, CONF_HUB_VERSION: 2}
    )

    assert result["type"] == "create_entry"
    assert hass.config_entries.async_entries(DOMAIN)
    for entry in hass.config_entries.async_entries(DOMAIN):
        assert entry.data[CONF_HOST] == MOCK_HOSTNAME
        assert entry.data[CONF_PORT] == 25105
        assert entry.data[CONF_USERNAME] == MOCK_USERNAME
        assert entry.data[CONF_PASSWORD] == MOCK_PASSWORD
        assert entry.data[CONF_HUB_VERSION] == 2


async def test_import_min_hub_v1(hass: HomeAssistant) -> None:
    """Test importing a minimum Hub v1 config from yaml."""

    result = await _import_config(
        hass, {**MOCK_IMPORT_MINIMUM_HUB_V1, CONF_PORT: 9761, CONF_HUB_VERSION: 1}
    )

    assert result["type"] == "create_entry"
    assert hass.config_entries.async_entries(DOMAIN)
    for entry in hass.config_entries.async_entries(DOMAIN):
        assert entry.data[CONF_HOST] == MOCK_HOSTNAME
        assert entry.data[CONF_PORT] == 9761
        assert entry.data[CONF_HUB_VERSION] == 1


async def test_import_existing(hass: HomeAssistant) -> None:
    """Test we fail on an existing config imported."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={},
    )
    config_entry.add_to_hass(hass)
    assert config_entry.state is config_entries.ConfigEntryState.NOT_LOADED

    result = await _import_config(
        hass, {**MOCK_IMPORT_MINIMUM_HUB_V2, CONF_PORT: 25105, CONF_HUB_VERSION: 2}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_import_failed_connection(hass: HomeAssistant) -> None:
    """Test a failed connection on import."""

    with patch(
        PATCH_CONNECTION,
        new=mock_failed_connection,
    ), patch(
        PATCH_ASYNC_SETUP, return_value=True
    ), patch(PATCH_ASYNC_SETUP_ENTRY, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={**MOCK_IMPORT_MINIMUM_HUB_V2, CONF_PORT: 25105, CONF_HUB_VERSION: 2},
        )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def _options_form(hass, flow_id, user_input):
    """Test an options form."""

    with patch(PATCH_ASYNC_SETUP_ENTRY, return_value=True) as mock_setup_entry:
        result = await hass.config_entries.options.async_configure(flow_id, user_input)
        return result, mock_setup_entry


async def test_options_change_hub_config(hass: HomeAssistant) -> None:
    """Test changing Hub v2 config."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={},
    )

    config_entry.add_to_hass(hass)
    result = await _options_init_form(
        hass, config_entry.entry_id, STEP_CHANGE_HUB_CONFIG
    )

    user_input = {
        CONF_HOST: "2.3.4.5",
        CONF_PORT: 9999,
        CONF_USERNAME: "new username",
        CONF_PASSWORD: "new password",
    }
    result, _ = await _options_form(hass, result["flow_id"], user_input)

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert config_entry.options == {}
    assert config_entry.data == {**user_input, CONF_HUB_VERSION: 2}


async def test_options_change_plm_config(hass: HomeAssistant) -> None:
    """Test changing PLM config."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data=MOCK_USER_INPUT_PLM,
        options={},
    )

    config_entry.add_to_hass(hass)
    result = await _options_init_form(
        hass, config_entry.entry_id, STEP_CHANGE_PLM_CONFIG
    )

    user_input = {CONF_DEVICE: "/dev/some_other_device"}
    result, _ = await _options_form(hass, result["flow_id"], user_input)

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert config_entry.options == {}
    assert config_entry.data == user_input


async def test_options_add_device_override(hass: HomeAssistant) -> None:
    """Test adding a device override."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={},
    )

    config_entry.add_to_hass(hass)
    result = await _options_init_form(hass, config_entry.entry_id, STEP_ADD_OVERRIDE)

    user_input = {
        CONF_ADDRESS: "1a2b3c",
        CONF_CAT: "0x04",
        CONF_SUBCAT: "0xaa",
    }
    result, _ = await _options_form(hass, result["flow_id"], user_input)

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert len(config_entry.options[CONF_OVERRIDE]) == 1
    assert config_entry.options[CONF_OVERRIDE][0][CONF_ADDRESS] == "1A.2B.3C"
    assert config_entry.options[CONF_OVERRIDE][0][CONF_CAT] == 4
    assert config_entry.options[CONF_OVERRIDE][0][CONF_SUBCAT] == 170

    result2 = await _options_init_form(hass, config_entry.entry_id, STEP_ADD_OVERRIDE)

    user_input = {
        CONF_ADDRESS: "4d5e6f",
        CONF_CAT: "05",
        CONF_SUBCAT: "bb",
    }
    result3, _ = await _options_form(hass, result2["flow_id"], user_input)

    assert len(config_entry.options[CONF_OVERRIDE]) == 2
    assert config_entry.options[CONF_OVERRIDE][1][CONF_ADDRESS] == "4D.5E.6F"
    assert config_entry.options[CONF_OVERRIDE][1][CONF_CAT] == 5
    assert config_entry.options[CONF_OVERRIDE][1][CONF_SUBCAT] == 187

    # If result1 eq result2 the changes will not save
    assert result["data"] != result3["data"]


async def test_options_remove_device_override(hass: HomeAssistant) -> None:
    """Test removing a device override."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={
            CONF_OVERRIDE: [
                {CONF_ADDRESS: "1A.2B.3C", CONF_CAT: 6, CONF_SUBCAT: 100},
                {CONF_ADDRESS: "4D.5E.6F", CONF_CAT: 7, CONF_SUBCAT: 200},
            ]
        },
    )

    config_entry.add_to_hass(hass)
    result = await _options_init_form(hass, config_entry.entry_id, STEP_REMOVE_OVERRIDE)

    user_input = {CONF_ADDRESS: "1A.2B.3C"}
    result, _ = await _options_form(hass, result["flow_id"], user_input)

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert len(config_entry.options[CONF_OVERRIDE]) == 1


async def test_options_remove_device_override_with_x10(hass: HomeAssistant) -> None:
    """Test removing a device override when an X10 device is configured."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={
            CONF_OVERRIDE: [
                {CONF_ADDRESS: "1A.2B.3C", CONF_CAT: 6, CONF_SUBCAT: 100},
                {CONF_ADDRESS: "4D.5E.6F", CONF_CAT: 7, CONF_SUBCAT: 200},
            ],
            CONF_X10: [
                {
                    CONF_HOUSECODE: "d",
                    CONF_UNITCODE: 5,
                    CONF_PLATFORM: "light",
                    CONF_DIM_STEPS: 22,
                }
            ],
        },
    )

    config_entry.add_to_hass(hass)
    result = await _options_init_form(hass, config_entry.entry_id, STEP_REMOVE_OVERRIDE)

    user_input = {CONF_ADDRESS: "1A.2B.3C"}
    result, _ = await _options_form(hass, result["flow_id"], user_input)

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert len(config_entry.options[CONF_OVERRIDE]) == 1
    assert len(config_entry.options[CONF_X10]) == 1


async def test_options_add_x10_device(hass: HomeAssistant) -> None:
    """Test adding an X10 device."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={},
    )

    config_entry.add_to_hass(hass)
    result = await _options_init_form(hass, config_entry.entry_id, STEP_ADD_X10)

    user_input = {
        CONF_HOUSECODE: "c",
        CONF_UNITCODE: 12,
        CONF_PLATFORM: "light",
        CONF_DIM_STEPS: 18,
    }
    result2, _ = await _options_form(hass, result["flow_id"], user_input)

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert len(config_entry.options[CONF_X10]) == 1
    assert config_entry.options[CONF_X10][0][CONF_HOUSECODE] == "c"
    assert config_entry.options[CONF_X10][0][CONF_UNITCODE] == 12
    assert config_entry.options[CONF_X10][0][CONF_PLATFORM] == "light"
    assert config_entry.options[CONF_X10][0][CONF_DIM_STEPS] == 18

    result = await _options_init_form(hass, config_entry.entry_id, STEP_ADD_X10)
    user_input = {
        CONF_HOUSECODE: "d",
        CONF_UNITCODE: 10,
        CONF_PLATFORM: "binary_sensor",
        CONF_DIM_STEPS: 15,
    }
    result3, _ = await _options_form(hass, result["flow_id"], user_input)

    assert result3["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert len(config_entry.options[CONF_X10]) == 2
    assert config_entry.options[CONF_X10][1][CONF_HOUSECODE] == "d"
    assert config_entry.options[CONF_X10][1][CONF_UNITCODE] == 10
    assert config_entry.options[CONF_X10][1][CONF_PLATFORM] == "binary_sensor"
    assert config_entry.options[CONF_X10][1][CONF_DIM_STEPS] == 15

    # If result2 eq result3 the changes will not save
    assert result2["data"] != result3["data"]


async def test_options_remove_x10_device(hass: HomeAssistant) -> None:
    """Test removing an X10 device."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={
            CONF_X10: [
                {
                    CONF_HOUSECODE: "C",
                    CONF_UNITCODE: 4,
                    CONF_PLATFORM: "light",
                    CONF_DIM_STEPS: 18,
                },
                {
                    CONF_HOUSECODE: "D",
                    CONF_UNITCODE: 10,
                    CONF_PLATFORM: "binary_sensor",
                    CONF_DIM_STEPS: 15,
                },
            ]
        },
    )

    config_entry.add_to_hass(hass)
    result = await _options_init_form(hass, config_entry.entry_id, STEP_REMOVE_X10)

    user_input = {CONF_DEVICE: "Housecode: C, Unitcode: 4"}
    result, _ = await _options_form(hass, result["flow_id"], user_input)

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert len(config_entry.options[CONF_X10]) == 1


async def test_options_remove_x10_device_with_override(hass: HomeAssistant) -> None:
    """Test removing an X10 device when a device override is configured."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={
            CONF_X10: [
                {
                    CONF_HOUSECODE: "C",
                    CONF_UNITCODE: 4,
                    CONF_PLATFORM: "light",
                    CONF_DIM_STEPS: 18,
                },
                {
                    CONF_HOUSECODE: "D",
                    CONF_UNITCODE: 10,
                    CONF_PLATFORM: "binary_sensor",
                    CONF_DIM_STEPS: 15,
                },
            ],
            CONF_OVERRIDE: [{CONF_ADDRESS: "1A.2B.3C", CONF_CAT: 1, CONF_SUBCAT: 18}],
        },
    )

    config_entry.add_to_hass(hass)
    result = await _options_init_form(hass, config_entry.entry_id, STEP_REMOVE_X10)

    user_input = {CONF_DEVICE: "Housecode: C, Unitcode: 4"}
    result, _ = await _options_form(hass, result["flow_id"], user_input)

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert len(config_entry.options[CONF_X10]) == 1
    assert len(config_entry.options[CONF_OVERRIDE]) == 1


async def test_options_dup_selection(hass: HomeAssistant) -> None:
    """Test if a duplicate selection was made in options."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={},
    )
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {STEP_ADD_OVERRIDE: True, STEP_ADD_X10: True},
    )
    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["errors"] == {"base": "select_single"}


async def test_options_override_bad_data(hass: HomeAssistant) -> None:
    """Test for bad data in a device override."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="abcde12345",
        data={**MOCK_USER_INPUT_HUB_V2, CONF_HUB_VERSION: 2},
        options={},
    )

    config_entry.add_to_hass(hass)
    result = await _options_init_form(hass, config_entry.entry_id, STEP_ADD_OVERRIDE)

    user_input = {
        CONF_ADDRESS: "zzzzzz",
        CONF_CAT: "bad",
        CONF_SUBCAT: "data",
    }
    result, _ = await _options_form(hass, result["flow_id"], user_input)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "input_error"}


async def test_discovery_via_usb(hass: HomeAssistant) -> None:
    """Test usb flow."""
    discovery_info = usb.UsbServiceInfo(
        device="/dev/ttyINSTEON",
        pid="AAAA",
        vid="AAAA",
        serial_number="1234",
        description="insteon radio",
        manufacturer="test",
    )
    result = await hass.config_entries.flow.async_init(
        "insteon", context={"source": config_entries.SOURCE_USB}, data=discovery_info
    )
    await hass.async_block_till_done()
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "confirm_usb"

    with patch("homeassistant.components.insteon.config_flow.async_connect"), patch(
        "homeassistant.components.insteon.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["data"] == {"device": "/dev/ttyINSTEON"}


async def test_discovery_via_usb_already_setup(hass: HomeAssistant) -> None:
    """Test usb flow -- already setup."""

    MockConfigEntry(
        domain=DOMAIN, data={CONF_DEVICE: {CONF_DEVICE: "/dev/ttyUSB1"}}
    ).add_to_hass(hass)

    discovery_info = usb.UsbServiceInfo(
        device="/dev/ttyINSTEON",
        pid="AAAA",
        vid="AAAA",
        serial_number="1234",
        description="insteon radio",
        manufacturer="test",
    )
    result = await hass.config_entries.flow.async_init(
        "insteon", context={"source": config_entries.SOURCE_USB}, data=discovery_info
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
