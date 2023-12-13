"""Unit tests for the Todoist todo platform."""
from typing import Any
from unittest.mock import AsyncMock

import pytest
from todoist_api_python.models import Due, Task

from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import async_update_entity

from .conftest import PROJECT_ID, make_api_task

from tests.typing import WebSocketGenerator


@pytest.fixture(autouse=True)
def platforms() -> list[Platform]:
    """Fixture to specify platforms to test."""
    return [Platform.TODO]


@pytest.fixture(autouse=True)
def set_time_zone(hass: HomeAssistant) -> None:
    """Set the time zone for the tests that keesp UTC-6 all year round."""
    hass.config.set_time_zone("America/Regina")


@pytest.mark.parametrize(
    ("tasks", "expected_state"),
    [
        ([], "0"),
        ([make_api_task(id="12345", content="Soda", is_completed=False)], "1"),
        ([make_api_task(id="12345", content="Soda", is_completed=True)], "0"),
        (
            [
                make_api_task(id="12345", content="Milk", is_completed=False),
                make_api_task(id="54321", content="Soda", is_completed=False),
            ],
            "2",
        ),
        (
            [
                make_api_task(
                    id="12345",
                    content="Soda",
                    is_completed=False,
                    project_id="other-project-id",
                )
            ],
            "0",
        ),
        (
            [
                make_api_task(
                    id="12345", content="sub-task", is_completed=False, parent_id="1"
                )
            ],
            "0",
        ),
    ],
)
async def test_todo_item_state(
    hass: HomeAssistant,
    setup_integration: None,
    expected_state: str,
) -> None:
    """Test for a To-do List entity state."""

    state = hass.states.get("todo.name")
    assert state
    assert state.state == expected_state


@pytest.mark.parametrize(
    ("tasks", "item_data", "tasks_after_update", "add_kwargs", "expected_item"),
    [
        (
            [],
            {},
            [make_api_task(id="task-id-1", content="Soda", is_completed=False)],
            {"content": "Soda"},
            {"uid": "task-id-1", "summary": "Soda", "status": "needs_action"},
        ),
        (
            [],
            {"due_date": "2023-11-18"},
            [
                make_api_task(
                    id="task-id-1",
                    content="Soda",
                    is_completed=False,
                    due=Due(is_recurring=False, date="2023-11-18", string="today"),
                )
            ],
            {"due": {"date": "2023-11-18"}},
            {
                "uid": "task-id-1",
                "summary": "Soda",
                "status": "needs_action",
                "due": "2023-11-18",
            },
        ),
        (
            [],
            {"due_datetime": "2023-11-18T06:30:00"},
            [
                make_api_task(
                    id="task-id-1",
                    content="Soda",
                    is_completed=False,
                    due=Due(
                        date="2023-11-18",
                        is_recurring=False,
                        datetime="2023-11-18T12:30:00.000000Z",
                        string="today",
                    ),
                )
            ],
            {
                "due": {"date": "2023-11-18", "datetime": "2023-11-18T06:30:00-06:00"},
            },
            {
                "uid": "task-id-1",
                "summary": "Soda",
                "status": "needs_action",
                "due": "2023-11-18T06:30:00-06:00",
            },
        ),
        (
            [],
            {"description": "6-pack"},
            [
                make_api_task(
                    id="task-id-1",
                    content="Soda",
                    description="6-pack",
                    is_completed=False,
                )
            ],
            {"description": "6-pack"},
            {
                "uid": "task-id-1",
                "summary": "Soda",
                "status": "needs_action",
                "description": "6-pack",
            },
        ),
    ],
    ids=["summary", "due_date", "due_datetime", "description"],
)
async def test_add_todo_list_item(
    hass: HomeAssistant,
    setup_integration: None,
    api: AsyncMock,
    item_data: dict[str, Any],
    tasks_after_update: list[Task],
    add_kwargs: dict[str, Any],
    expected_item: dict[str, Any],
) -> None:
    """Test for adding a To-do Item."""

    state = hass.states.get("todo.name")
    assert state
    assert state.state == "0"

    api.add_task = AsyncMock()
    # Fake API response when state is refreshed after create
    api.get_tasks.return_value = tasks_after_update

    await hass.services.async_call(
        TODO_DOMAIN,
        "add_item",
        {"item": "Soda", **item_data},
        target={"entity_id": "todo.name"},
        blocking=True,
    )

    args = api.add_task.call_args
    assert args
    assert args.kwargs == {"project_id": PROJECT_ID, "content": "Soda", **add_kwargs}

    # Verify state is refreshed
    state = hass.states.get("todo.name")
    assert state
    assert state.state == "1"

    result = await hass.services.async_call(
        TODO_DOMAIN,
        "get_items",
        {},
        target={"entity_id": "todo.name"},
        blocking=True,
        return_response=True,
    )
    assert result == {"todo.name": {"items": [expected_item]}}


@pytest.mark.parametrize(
    ("tasks"), [[make_api_task(id="task-id-1", content="Soda", is_completed=False)]]
)
async def test_update_todo_item_status(
    hass: HomeAssistant,
    setup_integration: None,
    api: AsyncMock,
) -> None:
    """Test for updating a To-do Item that changes the status."""

    state = hass.states.get("todo.name")
    assert state
    assert state.state == "1"

    api.close_task = AsyncMock()
    api.reopen_task = AsyncMock()

    # Fake API response when state is refreshed after close
    api.get_tasks.return_value = [
        make_api_task(id="task-id-1", content="Soda", is_completed=True)
    ]

    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"item": "task-id-1", "status": "completed"},
        target={"entity_id": "todo.name"},
        blocking=True,
    )
    assert api.close_task.called
    args = api.close_task.call_args
    assert args
    assert args.kwargs.get("task_id") == "task-id-1"
    assert not api.reopen_task.called

    # Verify state is refreshed
    state = hass.states.get("todo.name")
    assert state
    assert state.state == "0"

    # Fake API response when state is refreshed after reopen
    api.get_tasks.return_value = [
        make_api_task(id="task-id-1", content="Soda", is_completed=False)
    ]

    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"item": "task-id-1", "status": "needs_action"},
        target={"entity_id": "todo.name"},
        blocking=True,
    )
    assert api.reopen_task.called
    args = api.reopen_task.call_args
    assert args
    assert args.kwargs.get("task_id") == "task-id-1"

    # Verify state is refreshed
    state = hass.states.get("todo.name")
    assert state
    assert state.state == "1"


@pytest.mark.parametrize(
    ("tasks", "update_data", "tasks_after_update", "update_kwargs", "expected_item"),
    [
        (
            [make_api_task(id="task-id-1", content="Soda", is_completed=False)],
            {"rename": "Milk"},
            [make_api_task(id="task-id-1", content="Milk", is_completed=False)],
            {"task_id": "task-id-1", "content": "Milk"},
            {"uid": "task-id-1", "summary": "Milk", "status": "needs_action"},
        ),
        (
            [make_api_task(id="task-id-1", content="Soda", is_completed=False)],
            {"due_date": "2023-11-18"},
            [
                make_api_task(
                    id="task-id-1",
                    content="Soda",
                    is_completed=False,
                    due=Due(is_recurring=False, date="2023-11-18", string="today"),
                )
            ],
            {"task_id": "task-id-1", "due": {"date": "2023-11-18"}},
            {
                "uid": "task-id-1",
                "summary": "Soda",
                "status": "needs_action",
                "due": "2023-11-18",
            },
        ),
        (
            [make_api_task(id="task-id-1", content="Soda", is_completed=False)],
            {"due_datetime": "2023-11-18T06:30:00"},
            [
                make_api_task(
                    id="task-id-1",
                    content="Soda",
                    is_completed=False,
                    due=Due(
                        date="2023-11-18",
                        is_recurring=False,
                        datetime="2023-11-18T12:30:00.000000Z",
                        string="today",
                    ),
                )
            ],
            {
                "task_id": "task-id-1",
                "due": {"date": "2023-11-18", "datetime": "2023-11-18T06:30:00-06:00"},
            },
            {
                "uid": "task-id-1",
                "summary": "Soda",
                "status": "needs_action",
                "due": "2023-11-18T06:30:00-06:00",
            },
        ),
        (
            [make_api_task(id="task-id-1", content="Soda", is_completed=False)],
            {"description": "6-pack"},
            [
                make_api_task(
                    id="task-id-1",
                    content="Soda",
                    description="6-pack",
                    is_completed=False,
                )
            ],
            {"task_id": "task-id-1", "description": "6-pack"},
            {
                "uid": "task-id-1",
                "summary": "Soda",
                "status": "needs_action",
                "description": "6-pack",
            },
        ),
    ],
    ids=["rename", "due_date", "due_datetime", "description"],
)
async def test_update_todo_items(
    hass: HomeAssistant,
    setup_integration: None,
    api: AsyncMock,
    update_data: dict[str, Any],
    tasks_after_update: list[Task],
    update_kwargs: dict[str, Any],
    expected_item: dict[str, Any],
) -> None:
    """Test for updating a To-do Item that changes the summary."""

    state = hass.states.get("todo.name")
    assert state
    assert state.state == "1"

    api.update_task = AsyncMock()

    # Fake API response when state is refreshed after close
    api.get_tasks.return_value = tasks_after_update

    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"item": "task-id-1", **update_data},
        target={"entity_id": "todo.name"},
        blocking=True,
    )
    assert api.update_task.called
    args = api.update_task.call_args
    assert args
    assert args.kwargs == update_kwargs

    result = await hass.services.async_call(
        TODO_DOMAIN,
        "get_items",
        {},
        target={"entity_id": "todo.name"},
        blocking=True,
        return_response=True,
    )
    assert result == {"todo.name": {"items": [expected_item]}}


@pytest.mark.parametrize(
    ("tasks"),
    [
        [
            make_api_task(id="task-id-1", content="Soda", is_completed=False),
            make_api_task(id="task-id-2", content="Milk", is_completed=False),
        ]
    ],
)
async def test_remove_todo_item(
    hass: HomeAssistant,
    setup_integration: None,
    api: AsyncMock,
) -> None:
    """Test for removing a To-do Item."""

    state = hass.states.get("todo.name")
    assert state
    assert state.state == "2"

    api.delete_task = AsyncMock()
    # Fake API response when state is refreshed after close
    api.get_tasks.return_value = []

    await hass.services.async_call(
        TODO_DOMAIN,
        "remove_item",
        {"item": ["task-id-1", "task-id-2"]},
        target={"entity_id": "todo.name"},
        blocking=True,
    )
    assert api.delete_task.call_count == 2
    args = api.delete_task.call_args_list
    assert args[0].kwargs.get("task_id") == "task-id-1"
    assert args[1].kwargs.get("task_id") == "task-id-2"

    await async_update_entity(hass, "todo.name")
    state = hass.states.get("todo.name")
    assert state
    assert state.state == "0"


@pytest.mark.parametrize(
    ("tasks"), [[make_api_task(id="task-id-1", content="Cheese", is_completed=False)]]
)
async def test_subscribe(
    hass: HomeAssistant,
    setup_integration: None,
    api: AsyncMock,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test for subscribing to state updates."""

    # Subscribe and get the initial list
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "todo/item/subscribe",
            "entity_id": "todo.name",
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] is None
    subscription_id = msg["id"]

    msg = await client.receive_json()
    assert msg["id"] == subscription_id
    assert msg["type"] == "event"
    items = msg["event"].get("items")
    assert items
    assert len(items) == 1
    assert items[0]["summary"] == "Cheese"
    assert items[0]["status"] == "needs_action"
    assert items[0]["uid"]

    # Fake API response when state is refreshed
    api.get_tasks.return_value = [
        make_api_task(id="test-id-1", content="Wine", is_completed=False)
    ]
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"item": "Cheese", "rename": "Wine"},
        target={"entity_id": "todo.name"},
        blocking=True,
    )

    # Verify update is published
    msg = await client.receive_json()
    assert msg["id"] == subscription_id
    assert msg["type"] == "event"
    items = msg["event"].get("items")
    assert items
    assert len(items) == 1
    assert items[0]["summary"] == "Wine"
    assert items[0]["status"] == "needs_action"
    assert items[0]["uid"]
