"""Tests for the AndroidTV config flow."""
import json
from socket import gaierror
from unittest.mock import patch

import pytest

from homeassistant import data_entry_flow
from homeassistant.components.androidtv.config_flow import (
    APPS_NEW_ID,
    CONF_APP_DELETE,
    CONF_APP_ID,
    CONF_APP_NAME,
    CONF_RULE_DELETE,
    CONF_RULE_ID,
    CONF_RULE_VALUES,
    RULES_NEW_ID,
)
from homeassistant.components.androidtv.const import (
    CONF_ADB_SERVER_IP,
    CONF_ADB_SERVER_PORT,
    CONF_ADBKEY,
    CONF_APPS,
    CONF_EXCLUDE_UNNAMED_APPS,
    CONF_GET_SOURCES,
    CONF_SCREENCAP,
    CONF_STATE_DETECTION_RULES,
    CONF_TURN_OFF_COMMAND,
    CONF_TURN_ON_COMMAND,
    DEFAULT_ADB_SERVER_PORT,
    DEFAULT_PORT,
    DOMAIN,
    PROP_ETHMAC,
)
from homeassistant.components.media_player import DOMAIN as MP_DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import CONF_DEVICE_CLASS, CONF_HOST, CONF_PLATFORM, CONF_PORT
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry
from tests.components.androidtv.patchers import isfile

ADBKEY = "adbkey"
ETH_MAC = "a1:b1:c1:d1:e1:f1"
HOST = "127.0.0.1"
VALID_DETECT_RULE = [{"paused": {"media_session_state": 3}}]

# Android TV device with Python ADB implementation
CONFIG_PYTHON_ADB = {
    CONF_HOST: HOST,
    CONF_PORT: DEFAULT_PORT,
    CONF_DEVICE_CLASS: "androidtv",
    CONF_ADB_SERVER_PORT: DEFAULT_ADB_SERVER_PORT,
}

# Android TV device with ADB server
CONFIG_ADB_SERVER = {
    CONF_HOST: HOST,
    CONF_PORT: DEFAULT_PORT,
    CONF_DEVICE_CLASS: "androidtv",
    CONF_ADB_SERVER_IP: "127.0.0.1",
    CONF_ADB_SERVER_PORT: DEFAULT_ADB_SERVER_PORT,
}

CONNECT_METHOD = (
    "homeassistant.components.androidtv.config_flow.async_connect_androidtv"
)
PATCH_ACCESS = patch(
    "homeassistant.components.androidtv.config_flow.os.access", return_value=True
)
PATCH_GET_HOST_IP = patch(
    "homeassistant.components.androidtv.config_flow.socket.gethostbyname",
    return_value=HOST,
)
PATCH_ISFILE = patch(
    "homeassistant.components.androidtv.config_flow.os.path.isfile", isfile
)
PATCH_SETUP_ENTRY = patch(
    "homeassistant.components.androidtv.async_setup_entry",
    return_value=True,
)


class MockConfigDevice:
    """Mock class to emulate Android TV device."""

    def __init__(self, eth_mac=ETH_MAC):
        """Initialize a fake device to test config flow."""
        self.available = True
        self.device_properties = {PROP_ETHMAC: eth_mac}

    async def adb_close(self):
        """Fake method to close connection."""
        self.available = False


@pytest.mark.parametrize("config", [CONFIG_PYTHON_ADB, CONFIG_ADB_SERVER])
async def test_user(hass, config):
    """Test user config."""
    flow_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER, "show_advanced_options": True}
    )
    assert flow_result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert flow_result["step_id"] == "user"

    # test with all provided
    with patch(
        CONNECT_METHOD,
        return_value=(MockConfigDevice(), None),
    ), PATCH_SETUP_ENTRY as mock_setup_entry, PATCH_GET_HOST_IP:
        result = await hass.config_entries.flow.async_configure(
            flow_result["flow_id"], user_input=config
        )
        await hass.async_block_till_done()

        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["title"] == HOST
        assert result["data"] == config

        assert len(mock_setup_entry.mock_calls) == 1


async def test_import(hass):
    """Test import config."""

    # test with all provided
    with patch(
        CONNECT_METHOD,
        return_value=(MockConfigDevice(), None),
    ), PATCH_SETUP_ENTRY as mock_setup_entry, PATCH_GET_HOST_IP:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=CONFIG_PYTHON_ADB,
        )
        await hass.async_block_till_done()

        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["title"] == HOST
        assert result["data"] == CONFIG_PYTHON_ADB

        assert len(mock_setup_entry.mock_calls) == 1


async def test_user_adbkey(hass):
    """Test user step with adbkey file."""
    config_data = CONFIG_PYTHON_ADB.copy()
    config_data[CONF_ADBKEY] = ADBKEY

    with patch(
        CONNECT_METHOD,
        return_value=(MockConfigDevice(), None),
    ), PATCH_SETUP_ENTRY as mock_setup_entry, PATCH_GET_HOST_IP, PATCH_ISFILE, PATCH_ACCESS:

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER, "show_advanced_options": True},
            data=config_data,
        )
        await hass.async_block_till_done()

        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["title"] == HOST
        assert result["data"] == config_data

        assert len(mock_setup_entry.mock_calls) == 1


async def test_import_data(hass):
    """Test import from configuration file."""
    config_data = CONFIG_PYTHON_ADB.copy()
    config_data[CONF_PLATFORM] = DOMAIN
    config_data[CONF_ADBKEY] = ADBKEY
    config_data[CONF_TURN_OFF_COMMAND] = "off"
    platform_data = {MP_DOMAIN: config_data}

    with patch(
        CONNECT_METHOD,
        return_value=(MockConfigDevice(), None),
    ), PATCH_SETUP_ENTRY as mock_setup_entry, PATCH_GET_HOST_IP, PATCH_ISFILE, PATCH_ACCESS:

        assert await async_setup_component(hass, MP_DOMAIN, platform_data)
        await hass.async_block_till_done()

        assert len(mock_setup_entry.mock_calls) == 1


async def test_error_both_key_server(hass):
    """Test we abort if both adb key and server are provided."""
    config_data = CONFIG_ADB_SERVER.copy()

    config_data[CONF_ADBKEY] = ADBKEY
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER, "show_advanced_options": True},
        data=config_data,
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] == {"base": "key_and_server"}

    with patch(
        CONNECT_METHOD,
        return_value=(MockConfigDevice(), None),
    ), PATCH_SETUP_ENTRY, PATCH_GET_HOST_IP:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=CONFIG_ADB_SERVER
        )
        await hass.async_block_till_done()

        assert result2["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result2["title"] == HOST
        assert result2["data"] == CONFIG_ADB_SERVER


async def test_error_invalid_key(hass):
    """Test we abort if component is already setup."""
    config_data = CONFIG_PYTHON_ADB.copy()
    config_data[CONF_ADBKEY] = ADBKEY
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER, "show_advanced_options": True},
        data=config_data,
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] == {"base": "adbkey_not_file"}

    with patch(
        CONNECT_METHOD,
        return_value=(MockConfigDevice(), None),
    ), PATCH_SETUP_ENTRY, PATCH_GET_HOST_IP:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=CONFIG_ADB_SERVER
        )
        await hass.async_block_till_done()

        assert result2["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result2["title"] == HOST
        assert result2["data"] == CONFIG_ADB_SERVER


async def test_error_invalid_host(hass):
    """Test we abort if host name is invalid."""
    with patch(
        "socket.gethostbyname",
        side_effect=gaierror,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER, "show_advanced_options": True},
            data=CONFIG_ADB_SERVER,
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"] == {"base": "invalid_host"}

    with patch(
        CONNECT_METHOD,
        return_value=(MockConfigDevice(), None),
    ), PATCH_SETUP_ENTRY, PATCH_GET_HOST_IP:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=CONFIG_ADB_SERVER
        )
        await hass.async_block_till_done()

        assert result2["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result2["title"] == HOST
        assert result2["data"] == CONFIG_ADB_SERVER


async def test_invalid_serial(hass):
    """Test for invallid serialno."""
    with patch(
        CONNECT_METHOD,
        return_value=(MockConfigDevice(eth_mac=""), None),
    ), PATCH_GET_HOST_IP:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=CONFIG_ADB_SERVER,
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "invalid_unique_id"


async def test_abort_if_host_exist(hass):
    """Test we abort if component is already setup."""
    MockConfigEntry(
        domain=DOMAIN, data=CONFIG_ADB_SERVER, unique_id=ETH_MAC
    ).add_to_hass(hass)

    config_data = CONFIG_ADB_SERVER.copy()
    config_data[CONF_HOST] = "name"
    # Should fail, same IP Address (by PATCH_GET_HOST_IP)
    with PATCH_GET_HOST_IP:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=config_data,
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "already_configured"


async def test_abort_import_if_host_exist(hass):
    """Test we abort if component is already setup."""
    MockConfigEntry(
        domain=DOMAIN, data=CONFIG_ADB_SERVER, unique_id=ETH_MAC
    ).add_to_hass(hass)

    # Should fail, same Host in entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data=CONFIG_ADB_SERVER,
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "already_configured"


async def test_abort_if_unique_exist(hass):
    """Test we abort if component is already setup."""
    config_data = CONFIG_ADB_SERVER.copy()
    config_data[CONF_HOST] = "127.0.0.2"
    MockConfigEntry(domain=DOMAIN, data=config_data, unique_id=ETH_MAC).add_to_hass(
        hass
    )

    # Should fail, same SerialNo
    with patch(
        CONNECT_METHOD,
        return_value=(MockConfigDevice(), None),
    ), PATCH_GET_HOST_IP:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=CONFIG_ADB_SERVER,
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "already_configured"


async def test_on_connect_failed(hass):
    """Test when we have errors connecting the router."""
    flow_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER, "show_advanced_options": True},
    )

    with patch(CONNECT_METHOD, return_value=(None, "Error")), PATCH_GET_HOST_IP:
        result = await hass.config_entries.flow.async_configure(
            flow_result["flow_id"], user_input=CONFIG_ADB_SERVER
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"] == {"base": "cannot_connect"}

    with patch(
        CONNECT_METHOD,
        side_effect=TypeError,
    ), PATCH_GET_HOST_IP:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=CONFIG_ADB_SERVER
        )
        assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result2["errors"] == {"base": "unknown"}

    with patch(
        CONNECT_METHOD,
        return_value=(MockConfigDevice(), None),
    ), PATCH_SETUP_ENTRY, PATCH_GET_HOST_IP:
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"], user_input=CONFIG_ADB_SERVER
        )
        await hass.async_block_till_done()

        assert result3["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result3["title"] == HOST
        assert result3["data"] == CONFIG_ADB_SERVER


async def test_options_flow(hass):
    """Test config flow options."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=CONFIG_ADB_SERVER,
        unique_id=ETH_MAC,
        options={
            CONF_APPS: {"app1": "App1"},
            CONF_STATE_DETECTION_RULES: {"com.plexapp.android": VALID_DETECT_RULE},
        },
    )
    config_entry.add_to_hass(hass)

    with PATCH_SETUP_ENTRY:
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(config_entry.entry_id)

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"

        # test app form with existing app
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_APPS: "app1",
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "apps"

        # test change value in apps form
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_APP_NAME: "Appl1",
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"

        # test app form with new app
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_APPS: APPS_NEW_ID,
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "apps"

        # test save value for new app
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_APP_ID: "app2",
                CONF_APP_NAME: "Appl2",
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"

        # test app form for delete
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_APPS: "app1",
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "apps"

        # test delete app1
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_APP_NAME: "Appl1",
                CONF_APP_DELETE: True,
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"

        # test rules form with existing rule
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_STATE_DETECTION_RULES: "com.plexapp.android",
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "rules"

        # test change value in rule form with invalid json rule
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RULE_VALUES: "a",
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "rules"
        assert result["errors"] == {"base": "invalid_det_rules"}

        # test change value in rule form with invalid rule
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RULE_VALUES: json.dumps({"a": "b"}),
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "rules"
        assert result["errors"] == {"base": "invalid_det_rules"}

        # test change value in rule form with valid rule
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RULE_VALUES: json.dumps(["standby"]),
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"

        # test rule form with new rule
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_STATE_DETECTION_RULES: RULES_NEW_ID,
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "rules"

        # test save value for new rule
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RULE_ID: "rule2",
                CONF_RULE_VALUES: json.dumps(VALID_DETECT_RULE),
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"

        # test rules form with delete existing rule
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_STATE_DETECTION_RULES: "com.plexapp.android",
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "rules"

        # test delete rule
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RULE_DELETE: True,
            },
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_GET_SOURCES: True,
                CONF_EXCLUDE_UNNAMED_APPS: True,
                CONF_SCREENCAP: True,
                CONF_TURN_OFF_COMMAND: "off",
                CONF_TURN_ON_COMMAND: "on",
            },
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY

        apps_options = config_entry.options[CONF_APPS]
        assert apps_options.get("app1") is None
        assert apps_options["app2"] == "Appl2"

        assert config_entry.options[CONF_GET_SOURCES] is True
        assert config_entry.options[CONF_EXCLUDE_UNNAMED_APPS] is True
        assert config_entry.options[CONF_SCREENCAP] is True
        assert config_entry.options[CONF_TURN_OFF_COMMAND] == "off"
        assert config_entry.options[CONF_TURN_ON_COMMAND] == "on"
