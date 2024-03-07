"""Test Lutron Homeworks Series 4 and 8 config flow."""
from unittest.mock import ANY, MagicMock

import pytest
from pytest_unordered import unordered

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.homeworks.const import (
    CONF_ADDR,
    CONF_BUTTONS,
    CONF_DIMMERS,
    CONF_INDEX,
    CONF_KEYPADS,
    CONF_NUMBER,
    CONF_RATE,
    CONF_RELEASE_DELAY,
    DOMAIN,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from tests.common import MockConfigEntry


async def test_user_flow(
    hass: HomeAssistant, mock_homeworks: MagicMock, mock_setup_entry
) -> None:
    """Test the user configuration flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    mock_controller = MagicMock()
    mock_homeworks.return_value = mock_controller
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "192.168.0.1",
            CONF_NAME: "Main controller",
            CONF_PORT: 1234,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Main controller"
    assert result["data"] == {}
    assert result["options"] == {
        "controller_id": "main_controller",
        "dimmers": [],
        "host": "192.168.0.1",
        "keypads": [],
        "port": 1234,
    }
    mock_homeworks.assert_called_once_with("192.168.0.1", 1234, ANY)
    mock_controller.close.assert_called_once_with()
    mock_controller.join.assert_called_once_with()


async def test_user_flow_already_exists(
    hass: HomeAssistant, mock_empty_config_entry: MockConfigEntry, mock_setup_entry
) -> None:
    """Test the user configuration flow."""
    mock_empty_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "192.168.0.1",
            CONF_NAME: "Main controller",
            CONF_PORT: 1234,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "duplicated_host_port"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "192.168.0.2",
            CONF_NAME: "Main controller",
            CONF_PORT: 1234,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "duplicated_controller_id"}


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [(ConnectionError, "connection_error"), (Exception, "unknown_error")],
)
async def test_user_flow_cannot_connect(
    hass: HomeAssistant,
    mock_homeworks: MagicMock,
    mock_setup_entry,
    side_effect: type[Exception],
    error: str,
) -> None:
    """Test handling invalid connection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )

    mock_homeworks.side_effect = side_effect
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "192.168.0.1",
            CONF_NAME: "Main controller",
            CONF_PORT: 1234,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert result["step_id"] == "user"


async def test_import_flow(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    issue_registry: ir.IssueRegistry,
    mock_homeworks: MagicMock,
    mock_setup_entry,
) -> None:
    """Test importing yaml config."""
    entry = entity_registry.async_get_or_create(
        LIGHT_DOMAIN, DOMAIN, "homeworks.[02:08:01:01]"
    )

    mock_controller = MagicMock()
    mock_homeworks.return_value = mock_controller
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={
            CONF_HOST: "192.168.0.1",
            CONF_PORT: 1234,
            CONF_DIMMERS: [
                {
                    CONF_ADDR: "[02:08:01:01]",
                    CONF_NAME: "Foyer Sconces",
                    CONF_RATE: 1.0,
                }
            ],
            CONF_KEYPADS: [
                {
                    CONF_ADDR: "[02:08:02:01]",
                    CONF_NAME: "Foyer Keypad",
                    CONF_BUTTONS: [
                        {
                            CONF_NAME: "Morning",
                            CONF_NUMBER: 1,
                            CONF_RELEASE_DELAY: None,
                        },
                        {
                            CONF_NAME: "Relax",
                            CONF_NUMBER: 2,
                            CONF_RELEASE_DELAY: None,
                        },
                        {
                            CONF_NAME: "Dim up",
                            CONF_NUMBER: 3,
                            CONF_RELEASE_DELAY: 0.2,
                        },
                    ],
                }
            ],
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_controller_name"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_NAME: "Main controller"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_finish"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Main controller"
    assert result["data"] == {}
    assert result["options"] == {
        "controller_id": "main_controller",
        "dimmers": [{"addr": "[02:08:01:01]", "name": "Foyer Sconces", "rate": 1.0}],
        "host": "192.168.0.1",
        "keypads": [
            {
                "addr": "[02:08:02:01]",
                "buttons": [
                    {
                        "name": "Morning",
                        "number": 1,
                        "release_delay": None,
                    },
                    {"name": "Relax", "number": 2, "release_delay": None},
                    {"name": "Dim up", "number": 3, "release_delay": 0.2},
                ],
                "name": "Foyer Keypad",
            }
        ],
        "port": 1234,
    }
    assert len(issue_registry.issues) == 0

    # Check unique ID is updated in entity registry
    entry = entity_registry.async_get(entry.id)
    assert entry.unique_id == "homeworks.main_controller.[02:08:01:01].0"


async def test_import_flow_already_exists(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    mock_empty_config_entry: MockConfigEntry,
) -> None:
    """Test importing yaml config where entry already exists."""
    mock_empty_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={"host": "192.168.0.1", "port": 1234, CONF_DIMMERS: [], CONF_KEYPADS: []},
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(issue_registry.issues) == 1


async def test_import_flow_controller_id_exists(
    hass: HomeAssistant, mock_empty_config_entry: MockConfigEntry
) -> None:
    """Test importing yaml config where entry already exists."""
    mock_empty_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={"host": "192.168.0.2", "port": 1234, CONF_DIMMERS: [], CONF_KEYPADS: []},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_controller_name"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_NAME: "Main controller"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_controller_name"
    assert result["errors"] == {"base": "duplicated_controller_id"}


async def test_options_add_light_flow(
    hass: HomeAssistant,
    mock_empty_config_entry: MockConfigEntry,
    mock_homeworks: MagicMock,
) -> None:
    """Test options flow to add a light."""
    mock_empty_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_empty_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.async_entity_ids("light") == unordered([])

    result = await hass.config_entries.options.async_init(
        mock_empty_config_entry.entry_id
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "add_light"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_light"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_ADDR: "[02:08:01:02]",
            CONF_NAME: "Foyer Downlights",
            CONF_RATE: 2.0,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "controller_id": "main_controller",
        "dimmers": [
            {"addr": "[02:08:01:02]", "name": "Foyer Downlights", "rate": 2.0},
        ],
        "host": "192.168.0.1",
        "keypads": [],
        "port": 1234,
    }

    await hass.async_block_till_done()

    # Check the entry was updated with the new entity
    assert hass.states.async_entity_ids("light") == unordered(
        ["light.foyer_downlights"]
    )


async def test_options_add_remove_light_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_homeworks: MagicMock
) -> None:
    """Test options flow to add and remove a light."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.async_entity_ids("light") == unordered(["light.foyer_sconces"])

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "add_light"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_light"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_ADDR: "[02:08:01:02]",
            CONF_NAME: "Foyer Downlights",
            CONF_RATE: 2.0,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "controller_id": "main_controller",
        "dimmers": [
            {"addr": "[02:08:01:01]", "name": "Foyer Sconces", "rate": 1.0},
            {"addr": "[02:08:01:02]", "name": "Foyer Downlights", "rate": 2.0},
        ],
        "host": "192.168.0.1",
        "keypads": [
            {
                "addr": "[02:08:02:01]",
                "buttons": [
                    {
                        "name": "Morning",
                        "number": 1,
                        "release_delay": None,
                    },
                    {"name": "Relax", "number": 2, "release_delay": None},
                    {"name": "Dim up", "number": 3, "release_delay": 0.2},
                ],
                "name": "Foyer Keypad",
            }
        ],
        "port": 1234,
    }

    await hass.async_block_till_done()

    # Check the entry was updated with the new entity
    assert hass.states.async_entity_ids("light") == unordered(
        ["light.foyer_sconces", "light.foyer_downlights"]
    )

    # Now remove the original light
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "remove_light"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "remove_light"
    assert result["data_schema"].schema["index"].options == {
        "0": "Foyer Sconces ([02:08:01:01])",
        "1": "Foyer Downlights ([02:08:01:02])",
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_INDEX: ["0"]}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "controller_id": "main_controller",
        "dimmers": [
            {"addr": "[02:08:01:02]", "name": "Foyer Downlights", "rate": 2.0},
        ],
        "host": "192.168.0.1",
        "keypads": [
            {
                "addr": "[02:08:02:01]",
                "buttons": [
                    {
                        "name": "Morning",
                        "number": 1,
                        "release_delay": None,
                    },
                    {"name": "Relax", "number": 2, "release_delay": None},
                    {"name": "Dim up", "number": 3, "release_delay": 0.2},
                ],
                "name": "Foyer Keypad",
            }
        ],
        "port": 1234,
    }

    await hass.async_block_till_done()

    # Check the original entity was removed, with only the new entity left
    assert hass.states.async_entity_ids("light") == unordered(
        ["light.foyer_downlights"]
    )


async def test_options_add_remove_keypad_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_homeworks: MagicMock
) -> None:
    """Test options flow to add and remove a keypad."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "add_keypad"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_keypad"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_ADDR: "[02:08:03:01]",
            CONF_NAME: "Hall Keypad",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "controller_id": "main_controller",
        "dimmers": [
            {"addr": "[02:08:01:01]", "name": "Foyer Sconces", "rate": 1.0},
        ],
        "host": "192.168.0.1",
        "keypads": [
            {
                "addr": "[02:08:02:01]",
                "buttons": [
                    {
                        "name": "Morning",
                        "number": 1,
                        "release_delay": None,
                    },
                    {"name": "Relax", "number": 2, "release_delay": None},
                    {"name": "Dim up", "number": 3, "release_delay": 0.2},
                ],
                "name": "Foyer Keypad",
            },
            {"addr": "[02:08:03:01]", "buttons": [], "name": "Hall Keypad"},
        ],
        "port": 1234,
    }

    await hass.async_block_till_done()

    # Now remove the original keypad
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "remove_keypad"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "remove_keypad"
    assert result["data_schema"].schema["index"].options == {
        "0": "Foyer Keypad ([02:08:02:01])",
        "1": "Hall Keypad ([02:08:03:01])",
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_INDEX: ["0"]}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "controller_id": "main_controller",
        "dimmers": [
            {"addr": "[02:08:01:01]", "name": "Foyer Sconces", "rate": 1.0},
        ],
        "host": "192.168.0.1",
        "keypads": [{"addr": "[02:08:03:01]", "buttons": [], "name": "Hall Keypad"}],
        "port": 1234,
    }
    await hass.async_block_till_done()


async def test_options_add_keypad_with_error(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_homeworks: MagicMock
) -> None:
    """Test options flow to add and remove a keypad."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "add_keypad"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_keypad"

    # Try an invalid address
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_ADDR: "[02:08:03:01",
            CONF_NAME: "Hall Keypad",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_keypad"
    assert result["errors"] == {"base": "invalid_addr"}

    # Try an address claimed by another keypad
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_ADDR: "[02:08:02:01]",
            CONF_NAME: "Hall Keypad",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_keypad"
    assert result["errors"] == {"base": "duplicated_addr"}

    # Try an address claimed by a light
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_ADDR: "[02:08:01:01]",
            CONF_NAME: "Hall Keypad",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_keypad"
    assert result["errors"] == {"base": "duplicated_addr"}


async def test_options_edit_light_no_lights_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_homeworks: MagicMock
) -> None:
    """Test options flow to edit a light."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.async_entity_ids("light") == unordered(["light.foyer_sconces"])

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "select_edit_light"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_edit_light"
    assert result["data_schema"].schema["index"].container == {
        "0": "Foyer Sconces ([02:08:01:01])"
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"index": "0"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_light"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_RATE: 3.0}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "controller_id": "main_controller",
        "dimmers": [{"addr": "[02:08:01:01]", "name": "Foyer Sconces", "rate": 3.0}],
        "host": "192.168.0.1",
        "keypads": [
            {
                "addr": "[02:08:02:01]",
                "buttons": [
                    {
                        "name": "Morning",
                        "number": 1,
                        "release_delay": None,
                    },
                    {"name": "Relax", "number": 2, "release_delay": None},
                    {"name": "Dim up", "number": 3, "release_delay": 0.2},
                ],
                "name": "Foyer Keypad",
            }
        ],
        "port": 1234,
    }

    await hass.async_block_till_done()

    # Check the entity was updated
    assert len(hass.states.async_entity_ids("light")) == 1


async def test_options_edit_light_flow_empty(
    hass: HomeAssistant,
    mock_empty_config_entry: MockConfigEntry,
    mock_homeworks: MagicMock,
) -> None:
    """Test options flow to edit a light."""
    mock_empty_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_empty_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.async_entity_ids("light") == unordered([])

    result = await hass.config_entries.options.async_init(
        mock_empty_config_entry.entry_id
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "select_edit_light"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_edit_light"
    assert result["data_schema"].schema["index"].container == {}


async def test_options_add_button_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_homeworks: MagicMock
) -> None:
    """Test options flow to add a button."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids(BUTTON_DOMAIN)) == 3

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "select_edit_keypad"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_edit_keypad"
    assert result["data_schema"].schema["index"].container == {
        "0": "Foyer Keypad ([02:08:02:01])"
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"index": "0"},
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "edit_keypad"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_button"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_button"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Dim down",
            CONF_NUMBER: 4,
            CONF_RELEASE_DELAY: 0.2,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "controller_id": "main_controller",
        "dimmers": [{"addr": "[02:08:01:01]", "name": "Foyer Sconces", "rate": 1.0}],
        "host": "192.168.0.1",
        "keypads": [
            {
                "addr": "[02:08:02:01]",
                "buttons": [
                    {
                        "name": "Morning",
                        "number": 1,
                        "release_delay": None,
                    },
                    {"name": "Relax", "number": 2, "release_delay": None},
                    {"name": "Dim up", "number": 3, "release_delay": 0.2},
                    {
                        "name": "Dim down",
                        "number": 4,
                        "release_delay": 0.2,
                    },
                ],
                "name": "Foyer Keypad",
            }
        ],
        "port": 1234,
    }

    await hass.async_block_till_done()

    # Check the new entities were added
    assert len(hass.states.async_entity_ids(BUTTON_DOMAIN)) == 4


async def test_options_add_button_flow_duplicate(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_homeworks: MagicMock
) -> None:
    """Test options flow to add a button."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids(BUTTON_DOMAIN)) == 3

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "select_edit_keypad"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_edit_keypad"
    assert result["data_schema"].schema["index"].container == {
        "0": "Foyer Keypad ([02:08:02:01])"
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"index": "0"},
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "edit_keypad"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_button"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_button"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Dim down",
            CONF_NUMBER: 1,
            CONF_RELEASE_DELAY: 0.2,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "duplicated_number"}


async def test_options_edit_button_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_homeworks: MagicMock
) -> None:
    """Test options flow to add a button."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids(BUTTON_DOMAIN)) == 3

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "select_edit_keypad"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_edit_keypad"
    assert result["data_schema"].schema["index"].container == {
        "0": "Foyer Keypad ([02:08:02:01])"
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"index": "0"},
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "edit_keypad"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "select_edit_button"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_edit_button"
    assert result["data_schema"].schema["index"].container == {
        "0": "Morning (1)",
        "1": "Relax (2)",
        "2": "Dim up (3)",
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"index": "0"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_button"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_RELEASE_DELAY: 0,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "controller_id": "main_controller",
        "dimmers": [{"addr": "[02:08:01:01]", "name": "Foyer Sconces", "rate": 1.0}],
        "host": "192.168.0.1",
        "keypads": [
            {
                "addr": "[02:08:02:01]",
                "buttons": [
                    {
                        "name": "Morning",
                        "number": 1,
                        "release_delay": 0.0,
                    },
                    {"name": "Relax", "number": 2, "release_delay": None},
                    {"name": "Dim up", "number": 3, "release_delay": 0.2},
                ],
                "name": "Foyer Keypad",
            }
        ],
        "port": 1234,
    }

    await hass.async_block_till_done()

    # Check the new entities were added
    assert len(hass.states.async_entity_ids(BUTTON_DOMAIN)) == 3


async def test_options_remove_button_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_homeworks: MagicMock
) -> None:
    """Test options flow to remove a button."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids(BUTTON_DOMAIN)) == 3

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "select_edit_keypad"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select_edit_keypad"
    assert result["data_schema"].schema["index"].container == {
        "0": "Foyer Keypad ([02:08:02:01])"
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"index": "0"},
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "edit_keypad"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_button"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "remove_button"
    assert result["data_schema"].schema["index"].options == {
        "0": "Morning (1)",
        "1": "Relax (2)",
        "2": "Dim up (3)",
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_INDEX: ["0"]}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "controller_id": "main_controller",
        "dimmers": [{"addr": "[02:08:01:01]", "name": "Foyer Sconces", "rate": 1.0}],
        "host": "192.168.0.1",
        "keypads": [
            {
                "addr": "[02:08:02:01]",
                "buttons": [
                    {"name": "Relax", "number": 2, "release_delay": None},
                    {"name": "Dim up", "number": 3, "release_delay": 0.2},
                ],
                "name": "Foyer Keypad",
            }
        ],
        "port": 1234,
    }

    await hass.async_block_till_done()

    # Check the entities were removed
    assert len(hass.states.async_entity_ids(BUTTON_DOMAIN)) == 2
