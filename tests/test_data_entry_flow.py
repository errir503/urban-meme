"""Test the flow classes."""
import asyncio
from unittest.mock import patch

import pytest
import voluptuous as vol

from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from homeassistant.util.decorator import Registry

from tests.common import async_capture_events


@pytest.fixture
def manager():
    """Return a flow manager."""
    handlers = Registry()
    entries = []

    class FlowManager(data_entry_flow.FlowManager):
        """Test flow manager."""

        async def async_create_flow(self, handler_key, *, context, data):
            """Test create flow."""
            handler = handlers.get(handler_key)

            if handler is None:
                raise data_entry_flow.UnknownHandler

            flow = handler()
            flow.init_step = context.get("init_step", "init")
            return flow

        async def async_finish_flow(self, flow, result):
            """Test finish flow."""
            if result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY:
                result["source"] = flow.context.get("source")
                entries.append(result)
            return result

    mgr = FlowManager(None)
    mgr.mock_created_entries = entries
    mgr.mock_reg_handler = handlers.register
    return mgr


async def test_configure_reuses_handler_instance(manager):
    """Test that we reuse instances."""

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        handle_count = 0

        async def async_step_init(self, user_input=None):
            self.handle_count += 1
            return self.async_show_form(
                errors={"base": str(self.handle_count)}, step_id="init"
            )

    form = await manager.async_init("test")
    assert form["errors"]["base"] == "1"
    form = await manager.async_configure(form["flow_id"])
    assert form["errors"]["base"] == "2"
    assert manager.async_progress() == [
        {
            "flow_id": form["flow_id"],
            "handler": "test",
            "step_id": "init",
            "context": {},
        }
    ]
    assert len(manager.mock_created_entries) == 0


async def test_configure_two_steps(manager):
    """Test that we reuse instances."""

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        VERSION = 1

        async def async_step_first(self, user_input=None):
            if user_input is not None:
                self.init_data = user_input
                return await self.async_step_second()
            return self.async_show_form(step_id="first", data_schema=vol.Schema([str]))

        async def async_step_second(self, user_input=None):
            if user_input is not None:
                return self.async_create_entry(
                    title="Test Entry", data=self.init_data + user_input
                )
            return self.async_show_form(step_id="second", data_schema=vol.Schema([str]))

    form = await manager.async_init("test", context={"init_step": "first"})

    with pytest.raises(vol.Invalid):
        form = await manager.async_configure(form["flow_id"], "INCORRECT-DATA")

    form = await manager.async_configure(form["flow_id"], ["INIT-DATA"])
    form = await manager.async_configure(form["flow_id"], ["SECOND-DATA"])
    assert form["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert len(manager.async_progress()) == 0
    assert len(manager.mock_created_entries) == 1
    result = manager.mock_created_entries[0]
    assert result["handler"] == "test"
    assert result["data"] == ["INIT-DATA", "SECOND-DATA"]


async def test_show_form(manager):
    """Test that we can show a form."""
    schema = vol.Schema({vol.Required("username"): str, vol.Required("password"): str})

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        async def async_step_init(self, user_input=None):
            return self.async_show_form(
                step_id="init",
                data_schema=schema,
                errors={"username": "Should be unique."},
            )

    form = await manager.async_init("test")
    assert form["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert form["data_schema"] is schema
    assert form["errors"] == {"username": "Should be unique."}


async def test_abort_removes_instance(manager):
    """Test that abort removes the flow from progress."""

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        is_new = True

        async def async_step_init(self, user_input=None):
            old = self.is_new
            self.is_new = False
            return self.async_abort(reason=str(old))

    form = await manager.async_init("test")
    assert form["reason"] == "True"
    assert len(manager.async_progress()) == 0
    assert len(manager.mock_created_entries) == 0
    form = await manager.async_init("test")
    assert form["reason"] == "True"
    assert len(manager.async_progress()) == 0
    assert len(manager.mock_created_entries) == 0


async def test_create_saves_data(manager):
    """Test creating a config entry."""

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        VERSION = 5

        async def async_step_init(self, user_input=None):
            return self.async_create_entry(title="Test Title", data="Test Data")

    await manager.async_init("test")
    assert len(manager.async_progress()) == 0
    assert len(manager.mock_created_entries) == 1

    entry = manager.mock_created_entries[0]
    assert entry["version"] == 5
    assert entry["handler"] == "test"
    assert entry["title"] == "Test Title"
    assert entry["data"] == "Test Data"
    assert entry["source"] is None


async def test_discovery_init_flow(manager):
    """Test a flow initialized by discovery."""

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        VERSION = 5

        async def async_step_init(self, info):
            return self.async_create_entry(title=info["id"], data=info)

    data = {"id": "hello", "token": "secret"}

    await manager.async_init(
        "test", context={"source": config_entries.SOURCE_DISCOVERY}, data=data
    )
    assert len(manager.async_progress()) == 0
    assert len(manager.mock_created_entries) == 1

    entry = manager.mock_created_entries[0]
    assert entry["version"] == 5
    assert entry["handler"] == "test"
    assert entry["title"] == "hello"
    assert entry["data"] == data
    assert entry["source"] == config_entries.SOURCE_DISCOVERY


async def test_finish_callback_change_result_type(hass):
    """Test finish callback can change result type."""

    class TestFlow(data_entry_flow.FlowHandler):
        VERSION = 1

        async def async_step_init(self, input):
            """Return init form with one input field 'count'."""
            if input is not None:
                return self.async_create_entry(title="init", data=input)
            return self.async_show_form(
                step_id="init", data_schema=vol.Schema({"count": int})
            )

    class FlowManager(data_entry_flow.FlowManager):
        async def async_create_flow(self, handler_name, *, context, data):
            """Create a test flow."""
            return TestFlow()

        async def async_finish_flow(self, flow, result):
            """Redirect to init form if count <= 1."""
            if result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY:
                if result["data"] is None or result["data"].get("count", 0) <= 1:
                    return flow.async_show_form(
                        step_id="init", data_schema=vol.Schema({"count": int})
                    )
                else:
                    result["result"] = result["data"]["count"]
            return result

    manager = FlowManager(hass)

    result = await manager.async_init("test")
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "init"

    result = await manager.async_configure(result["flow_id"], {"count": 0})
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "init"
    assert "result" not in result

    result = await manager.async_configure(result["flow_id"], {"count": 2})
    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["result"] == 2


async def test_external_step(hass, manager):
    """Test external step logic."""
    manager.hass = hass

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        VERSION = 5
        data = None

        async def async_step_init(self, user_input=None):
            if not user_input:
                return self.async_external_step(
                    step_id="init", url="https://example.com"
                )

            self.data = user_input
            return self.async_external_step_done(next_step_id="finish")

        async def async_step_finish(self, user_input=None):
            return self.async_create_entry(title=self.data["title"], data=self.data)

    events = async_capture_events(
        hass, data_entry_flow.EVENT_DATA_ENTRY_FLOW_PROGRESSED
    )

    result = await manager.async_init("test")
    assert result["type"] == data_entry_flow.RESULT_TYPE_EXTERNAL_STEP
    assert len(manager.async_progress()) == 1
    assert len(manager.async_progress_by_handler("test")) == 1
    assert manager.async_get(result["flow_id"])["handler"] == "test"

    # Mimic external step
    # Called by integrations: `hass.config_entries.flow.async_configure(…)`
    result = await manager.async_configure(result["flow_id"], {"title": "Hello"})
    assert result["type"] == data_entry_flow.RESULT_TYPE_EXTERNAL_STEP_DONE

    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data == {
        "handler": "test",
        "flow_id": result["flow_id"],
        "refresh": True,
    }

    # Frontend refreshses the flow
    result = await manager.async_configure(result["flow_id"])
    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "Hello"


async def test_show_progress(hass, manager):
    """Test show progress logic."""
    manager.hass = hass

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        VERSION = 5
        data = None
        task_one_done = False

        async def async_step_init(self, user_input=None):
            if not user_input:
                if not self.task_one_done:
                    self.task_one_done = True
                    progress_action = "task_one"
                else:
                    progress_action = "task_two"
                return self.async_show_progress(
                    step_id="init",
                    progress_action=progress_action,
                )

            self.data = user_input
            return self.async_show_progress_done(next_step_id="finish")

        async def async_step_finish(self, user_input=None):
            return self.async_create_entry(title=self.data["title"], data=self.data)

    events = async_capture_events(
        hass, data_entry_flow.EVENT_DATA_ENTRY_FLOW_PROGRESSED
    )

    result = await manager.async_init("test")
    assert result["type"] == data_entry_flow.RESULT_TYPE_SHOW_PROGRESS
    assert result["progress_action"] == "task_one"
    assert len(manager.async_progress()) == 1
    assert len(manager.async_progress_by_handler("test")) == 1
    assert manager.async_get(result["flow_id"])["handler"] == "test"

    # Mimic task one done and moving to task two
    # Called by integrations: `hass.config_entries.flow.async_configure(…)`
    result = await manager.async_configure(result["flow_id"])
    assert result["type"] == data_entry_flow.RESULT_TYPE_SHOW_PROGRESS
    assert result["progress_action"] == "task_two"

    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data == {
        "handler": "test",
        "flow_id": result["flow_id"],
        "refresh": True,
    }

    # Mimic task two done and continuing step
    # Called by integrations: `hass.config_entries.flow.async_configure(…)`
    result = await manager.async_configure(result["flow_id"], {"title": "Hello"})
    assert result["type"] == data_entry_flow.RESULT_TYPE_SHOW_PROGRESS_DONE

    await hass.async_block_till_done()
    assert len(events) == 2
    assert events[1].data == {
        "handler": "test",
        "flow_id": result["flow_id"],
        "refresh": True,
    }

    # Frontend refreshes the flow
    result = await manager.async_configure(result["flow_id"])
    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "Hello"


async def test_abort_flow_exception(manager):
    """Test that the AbortFlow exception works."""

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        async def async_step_init(self, user_input=None):
            raise data_entry_flow.AbortFlow("mock-reason", {"placeholder": "yo"})

    form = await manager.async_init("test")
    assert form["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert form["reason"] == "mock-reason"
    assert form["description_placeholders"] == {"placeholder": "yo"}


async def test_initializing_flows_canceled_on_shutdown(hass, manager):
    """Test that initializing flows are canceled on shutdown."""

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        async def async_step_init(self, user_input=None):
            await asyncio.sleep(1)

    task = asyncio.create_task(manager.async_init("test"))
    await hass.async_block_till_done()
    await manager.async_shutdown()

    with pytest.raises(asyncio.exceptions.CancelledError):
        await task


async def test_init_unknown_flow(manager):
    """Test that UnknownFlow is raised when async_create_flow returns None."""

    with pytest.raises(data_entry_flow.UnknownFlow), patch.object(
        manager, "async_create_flow", return_value=None
    ):
        await manager.async_init("test")


async def test_async_get_unknown_flow(manager):
    """Test that UnknownFlow is raised when async_get is called with a flow_id that does not exist."""

    with pytest.raises(data_entry_flow.UnknownFlow):
        await manager.async_get("does_not_exist")


async def test_async_has_matching_flow(
    hass: HomeAssistant, manager: data_entry_flow.FlowManager
):
    """Test we can check for matching flows."""
    manager.hass = hass

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        VERSION = 5

        async def async_step_init(self, user_input=None):
            return self.async_show_progress(
                step_id="init",
                progress_action="task_one",
            )

    result = await manager.async_init(
        "test",
        context={"source": config_entries.SOURCE_HOMEKIT},
        data={"properties": {"id": "aa:bb:cc:dd:ee:ff"}},
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_SHOW_PROGRESS
    assert result["progress_action"] == "task_one"
    assert len(manager.async_progress()) == 1
    assert len(manager.async_progress_by_handler("test")) == 1
    assert manager.async_get(result["flow_id"])["handler"] == "test"

    assert (
        manager.async_has_matching_flow(
            "test",
            {"source": config_entries.SOURCE_HOMEKIT},
            {"properties": {"id": "aa:bb:cc:dd:ee:ff"}},
        )
        is True
    )
    assert (
        manager.async_has_matching_flow(
            "test",
            {"source": config_entries.SOURCE_SSDP},
            {"properties": {"id": "aa:bb:cc:dd:ee:ff"}},
        )
        is False
    )
    assert (
        manager.async_has_matching_flow(
            "other",
            {"source": config_entries.SOURCE_HOMEKIT},
            {"properties": {"id": "aa:bb:cc:dd:ee:ff"}},
        )
        is False
    )


async def test_move_to_unknown_step_raises_and_removes_from_in_progress(manager):
    """Test that moving to an unknown step raises and removes the flow from in progress."""

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        VERSION = 1

    with pytest.raises(data_entry_flow.UnknownStep):
        await manager.async_init("test", context={"init_step": "does_not_exist"})

    assert manager.async_progress() == []


async def test_configure_raises_unknown_flow_if_not_in_progress(manager):
    """Test configure raises UnknownFlow if the flow is not in progress."""
    with pytest.raises(data_entry_flow.UnknownFlow):
        await manager.async_configure("wrong_flow_id")


async def test_abort_raises_unknown_flow_if_not_in_progress(manager):
    """Test abort raises UnknownFlow if the flow is not in progress."""
    with pytest.raises(data_entry_flow.UnknownFlow):
        await manager.async_abort("wrong_flow_id")


@pytest.mark.parametrize(
    "menu_options",
    (["target1", "target2"], {"target1": "Target 1", "target2": "Target 2"}),
)
async def test_show_menu(hass, manager, menu_options):
    """Test show menu."""
    manager.hass = hass

    @manager.mock_reg_handler("test")
    class TestFlow(data_entry_flow.FlowHandler):
        VERSION = 5
        data = None
        task_one_done = False

        async def async_step_init(self, user_input=None):
            return self.async_show_menu(
                step_id="init",
                menu_options=menu_options,
                description_placeholders={"name": "Paulus"},
            )

        async def async_step_target1(self, user_input=None):
            return self.async_show_form(step_id="target1")

        async def async_step_target2(self, user_input=None):
            return self.async_show_form(step_id="target2")

    result = await manager.async_init("test")
    assert result["type"] == data_entry_flow.RESULT_TYPE_MENU
    assert result["menu_options"] == menu_options
    assert result["description_placeholders"] == {"name": "Paulus"}
    assert len(manager.async_progress()) == 1
    assert len(manager.async_progress_by_handler("test")) == 1
    assert manager.async_get(result["flow_id"])["handler"] == "test"

    # Mimic picking a step
    result = await manager.async_configure(
        result["flow_id"], {"next_step_id": "target1"}
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "target1"
