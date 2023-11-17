"""The tests for the webdav todo component."""
from typing import Any
from unittest.mock import MagicMock, Mock

from caldav.lib.error import DAVError, NotFoundError
from caldav.objects import Todo
import pytest

from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from tests.common import MockConfigEntry

CALENDAR_NAME = "My Tasks"
ENTITY_NAME = "My tasks"
TEST_ENTITY = "todo.my_tasks"
SUPPORTED_FEATURES = 7

TODO_NO_STATUS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//E-Corp.//CalDAV Client//EN
BEGIN:VTODO
UID:1
DTSTAMP:20231125T000000Z
SUMMARY:Milk
END:VTODO
END:VCALENDAR"""

TODO_NEEDS_ACTION = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//E-Corp.//CalDAV Client//EN
BEGIN:VTODO
UID:2
DTSTAMP:20171125T000000Z
SUMMARY:Cheese
STATUS:NEEDS-ACTION
END:VTODO
END:VCALENDAR"""

TODO_COMPLETED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//E-Corp.//CalDAV Client//EN
BEGIN:VTODO
UID:3
DTSTAMP:20231125T000000Z
SUMMARY:Wine
STATUS:COMPLETED
END:VTODO
END:VCALENDAR"""


TODO_NO_SUMMARY = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//E-Corp.//CalDAV Client//EN
BEGIN:VTODO
UID:4
DTSTAMP:20171126T000000Z
STATUS:NEEDS-ACTION
END:VTODO
END:VCALENDAR"""


@pytest.fixture
def platforms() -> list[Platform]:
    """Fixture to set up config entry platforms."""
    return [Platform.TODO]


@pytest.fixture(name="todos")
def mock_todos() -> list[str]:
    """Fixture to return VTODO objects for the calendar."""
    return []


@pytest.fixture(name="supported_components")
def mock_supported_components() -> list[str]:
    """Fixture to set supported components of the calendar."""
    return ["VTODO"]


@pytest.fixture(name="calendar")
def mock_calendar(supported_components: list[str]) -> Mock:
    """Fixture to create the primary calendar for the test."""
    calendar = Mock()
    calendar.search = MagicMock(return_value=[])
    calendar.name = CALENDAR_NAME
    calendar.get_supported_components = MagicMock(return_value=supported_components)
    return calendar


def create_todo(calendar: Mock, idx: str, ics: str) -> Todo:
    """Create a caldav Todo object."""
    return Todo(client=None, url=f"{idx}.ics", data=ics, parent=calendar, id=idx)


@pytest.fixture(autouse=True)
def mock_search_items(calendar: Mock, todos: list[str]) -> None:
    """Fixture to add search results to the test calendar."""
    calendar.search.return_value = [
        create_todo(calendar, str(idx), item) for idx, item in enumerate(todos)
    ]


@pytest.fixture(name="calendars")
def mock_calendars(calendar: Mock) -> list[Mock]:
    """Fixture to create calendars for the test."""
    return [calendar]


@pytest.fixture(autouse=True)
async def mock_add_to_hass(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Fixture to add the ConfigEntry."""
    config_entry.add_to_hass(hass)


@pytest.mark.parametrize(
    ("todos", "expected_state"),
    [
        ([], "0"),
        (
            [TODO_NEEDS_ACTION],
            "1",
        ),
        (
            [TODO_NO_STATUS],
            "1",
        ),
        ([TODO_COMPLETED], "0"),
        ([TODO_NO_STATUS, TODO_NEEDS_ACTION, TODO_COMPLETED], "2"),
        ([TODO_NO_SUMMARY], "0"),
    ],
    ids=(
        "empty",
        "needs_action",
        "no_status",
        "completed",
        "all",
        "no_summary",
    ),
)
async def test_todo_list_state(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    expected_state: str,
) -> None:
    """Test a calendar entity from a config entry."""
    await config_entry.async_setup(hass)

    state = hass.states.get(TEST_ENTITY)
    assert state
    assert state.name == ENTITY_NAME
    assert state.state == expected_state
    assert dict(state.attributes) == {
        "friendly_name": ENTITY_NAME,
        "supported_features": SUPPORTED_FEATURES,
    }


@pytest.mark.parametrize(
    ("supported_components", "has_entity"),
    [([], False), (["VTODO"], True), (["VEVENT"], False), (["VEVENT", "VTODO"], True)],
)
async def test_supported_components(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    has_entity: bool,
) -> None:
    """Test a calendar supported components matches VTODO."""
    await config_entry.async_setup(hass)

    state = hass.states.get(TEST_ENTITY)
    assert (state is not None) == has_entity


async def test_add_item(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    calendar: Mock,
) -> None:
    """Test adding an item to the list."""
    calendar.search.return_value = []
    await config_entry.async_setup(hass)

    state = hass.states.get(TEST_ENTITY)
    assert state
    assert state.state == "0"

    # Simulat return value for the state update after the service call
    calendar.search.return_value = [create_todo(calendar, "2", TODO_NEEDS_ACTION)]

    await hass.services.async_call(
        TODO_DOMAIN,
        "add_item",
        {"item": "Cheese"},
        target={"entity_id": TEST_ENTITY},
        blocking=True,
    )

    assert calendar.save_todo.call_args
    assert calendar.save_todo.call_args.kwargs == {
        "status": "NEEDS-ACTION",
        "summary": "Cheese",
    }

    # Verify state was updated
    state = hass.states.get(TEST_ENTITY)
    assert state
    assert state.state == "1"


async def test_add_item_failure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    calendar: Mock,
) -> None:
    """Test failure when adding an item to the list."""
    await config_entry.async_setup(hass)

    calendar.save_todo.side_effect = DAVError()

    with pytest.raises(HomeAssistantError, match="CalDAV save error"):
        await hass.services.async_call(
            TODO_DOMAIN,
            "add_item",
            {"item": "Cheese"},
            target={"entity_id": TEST_ENTITY},
            blocking=True,
        )


@pytest.mark.parametrize(
    ("update_data", "expected_ics", "expected_state"),
    [
        (
            {"rename": "Swiss Cheese"},
            ["SUMMARY:Swiss Cheese", "STATUS:NEEDS-ACTION"],
            "1",
        ),
        ({"status": "needs_action"}, ["SUMMARY:Cheese", "STATUS:NEEDS-ACTION"], "1"),
        ({"status": "completed"}, ["SUMMARY:Cheese", "STATUS:COMPLETED"], "0"),
        (
            {"rename": "Swiss Cheese", "status": "needs_action"},
            ["SUMMARY:Swiss Cheese", "STATUS:NEEDS-ACTION"],
            "1",
        ),
    ],
)
async def test_update_item(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    dav_client: Mock,
    calendar: Mock,
    update_data: dict[str, Any],
    expected_ics: list[str],
    expected_state: str,
) -> None:
    """Test creating a an item on the list."""

    item = Todo(dav_client, None, TODO_NEEDS_ACTION, calendar, "2")
    calendar.search = MagicMock(return_value=[item])

    await config_entry.async_setup(hass)

    state = hass.states.get(TEST_ENTITY)
    assert state
    assert state.state == "1"

    calendar.todo_by_uid = MagicMock(return_value=item)

    dav_client.put.return_value.status = 204

    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {
            "item": "Cheese",
            **update_data,
        },
        target={"entity_id": TEST_ENTITY},
        blocking=True,
    )

    assert dav_client.put.call_args
    ics = dav_client.put.call_args.args[1]
    for expected in expected_ics:
        assert expected in ics

    state = hass.states.get(TEST_ENTITY)
    assert state
    assert state.state == expected_state


async def test_update_item_failure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    dav_client: Mock,
    calendar: Mock,
) -> None:
    """Test failure when updating an item on the list."""

    item = Todo(dav_client, None, TODO_NEEDS_ACTION, calendar, "2")
    calendar.search = MagicMock(return_value=[item])

    await config_entry.async_setup(hass)

    calendar.todo_by_uid = MagicMock(return_value=item)
    dav_client.put.side_effect = DAVError()

    with pytest.raises(HomeAssistantError, match="CalDAV save error"):
        await hass.services.async_call(
            TODO_DOMAIN,
            "update_item",
            {
                "item": "Cheese",
                "status": "completed",
            },
            target={"entity_id": TEST_ENTITY},
            blocking=True,
        )


@pytest.mark.parametrize(
    ("side_effect", "match"),
    [(DAVError, "CalDAV lookup error"), (NotFoundError, "Could not find")],
)
async def test_update_item_lookup_failure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    dav_client: Mock,
    calendar: Mock,
    side_effect: Any,
    match: str,
) -> None:
    """Test failure when looking up an item to update."""

    item = Todo(dav_client, None, TODO_NEEDS_ACTION, calendar, "2")
    calendar.search = MagicMock(return_value=[item])

    await config_entry.async_setup(hass)

    calendar.todo_by_uid.side_effect = side_effect

    with pytest.raises(HomeAssistantError, match=match):
        await hass.services.async_call(
            TODO_DOMAIN,
            "update_item",
            {
                "item": "Cheese",
                "status": "completed",
            },
            target={"entity_id": TEST_ENTITY},
            blocking=True,
        )


@pytest.mark.parametrize(
    ("uids_to_delete", "expect_item1_delete_called", "expect_item2_delete_called"),
    [
        ([], False, False),
        (["Cheese"], True, False),
        (["Wine"], False, True),
        (["Wine", "Cheese"], True, True),
    ],
    ids=("none", "item1-only", "item2-only", "both-items"),
)
async def test_remove_item(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    dav_client: Mock,
    calendar: Mock,
    uids_to_delete: list[str],
    expect_item1_delete_called: bool,
    expect_item2_delete_called: bool,
) -> None:
    """Test removing an item on the list."""

    item1 = Todo(dav_client, None, TODO_NEEDS_ACTION, calendar, "2")
    item2 = Todo(dav_client, None, TODO_COMPLETED, calendar, "3")
    calendar.search = MagicMock(return_value=[item1, item2])

    await config_entry.async_setup(hass)

    state = hass.states.get(TEST_ENTITY)
    assert state
    assert state.state == "1"

    def lookup(uid: str) -> Mock:
        assert uid == "2" or uid == "3"
        if uid == "2":
            return item1
        return item2

    calendar.todo_by_uid = Mock(side_effect=lookup)
    item1.delete = Mock()
    item2.delete = Mock()

    await hass.services.async_call(
        TODO_DOMAIN,
        "remove_item",
        {"item": uids_to_delete},
        target={"entity_id": TEST_ENTITY},
        blocking=True,
    )

    assert item1.delete.called == expect_item1_delete_called
    assert item2.delete.called == expect_item2_delete_called


@pytest.mark.parametrize(
    ("todos", "side_effect", "match"),
    [
        ([TODO_NEEDS_ACTION], DAVError, "CalDAV lookup error"),
        ([TODO_NEEDS_ACTION], NotFoundError, "Could not find"),
    ],
)
async def test_remove_item_lookup_failure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    calendar: Mock,
    side_effect: Any,
    match: str,
) -> None:
    """Test failure while removing an item from the list."""

    await config_entry.async_setup(hass)

    calendar.todo_by_uid.side_effect = side_effect

    with pytest.raises(HomeAssistantError, match=match):
        await hass.services.async_call(
            TODO_DOMAIN,
            "remove_item",
            {"item": "Cheese"},
            target={"entity_id": TEST_ENTITY},
            blocking=True,
        )


async def test_remove_item_failure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    dav_client: Mock,
    calendar: Mock,
) -> None:
    """Test removing an item on the list."""

    item = Todo(dav_client, "2.ics", TODO_NEEDS_ACTION, calendar, "2")
    calendar.search = MagicMock(return_value=[item])

    await config_entry.async_setup(hass)

    def lookup(uid: str) -> Mock:
        return item

    calendar.todo_by_uid = Mock(side_effect=lookup)
    dav_client.delete.return_value.status = 500

    with pytest.raises(HomeAssistantError, match="CalDAV delete error"):
        await hass.services.async_call(
            TODO_DOMAIN,
            "remove_item",
            {"item": "Cheese"},
            target={"entity_id": TEST_ENTITY},
            blocking=True,
        )


async def test_remove_item_not_found(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    dav_client: Mock,
    calendar: Mock,
) -> None:
    """Test removing an item on the list."""

    item = Todo(dav_client, "2.ics", TODO_NEEDS_ACTION, calendar, "2")
    calendar.search = MagicMock(return_value=[item])

    await config_entry.async_setup(hass)

    def lookup(uid: str) -> Mock:
        return item

    calendar.todo_by_uid.side_effect = NotFoundError()

    with pytest.raises(HomeAssistantError, match="Could not find"):
        await hass.services.async_call(
            TODO_DOMAIN,
            "remove_item",
            {"item": "Cheese"},
            target={"entity_id": TEST_ENTITY},
            blocking=True,
        )
