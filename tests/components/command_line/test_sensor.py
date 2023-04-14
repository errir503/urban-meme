"""The tests for the Command line sensor platform."""
from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest

from homeassistant import setup
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt

from tests.common import async_fire_time_changed


async def setup_test_entities(hass: HomeAssistant, config_dict: dict[str, Any]) -> None:
    """Set up a test command line sensor entity."""
    hass.states.async_set("sensor.input_sensor", "sensor_value")
    assert await setup.async_setup_component(
        hass,
        SENSOR_DOMAIN,
        {
            SENSOR_DOMAIN: [
                {"platform": "command_line", "name": "Test", **config_dict},
            ]
        },
    )
    await hass.async_block_till_done()


async def test_setup(hass: HomeAssistant) -> None:
    """Test sensor setup."""
    await setup_test_entities(
        hass,
        {
            "command": "echo 5",
            "unit_of_measurement": "in",
        },
    )
    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert entity_state.state == "5"
    assert entity_state.name == "Test"
    assert entity_state.attributes["unit_of_measurement"] == "in"


async def test_template(hass: HomeAssistant) -> None:
    """Test command sensor with template."""
    await setup_test_entities(
        hass,
        {
            "command": "echo 50",
            "unit_of_measurement": "in",
            "value_template": "{{ value | multiply(0.1) }}",
        },
    )
    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert float(entity_state.state) == 5


async def test_template_render(hass: HomeAssistant) -> None:
    """Ensure command with templates get rendered properly."""

    await setup_test_entities(
        hass,
        {
            "command": "echo {{ states.sensor.input_sensor.state }}",
        },
    )

    # Give time for template to load
    async_fire_time_changed(
        hass,
        dt.utcnow() + timedelta(minutes=1),
    )
    await hass.async_block_till_done()

    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert entity_state.state == "sensor_value"


async def test_template_render_with_quote(hass: HomeAssistant) -> None:
    """Ensure command with templates and quotes get rendered properly."""

    with patch(
        "homeassistant.components.command_line.utils.subprocess.check_output",
        return_value=b"Works\n",
    ) as check_output:
        await setup_test_entities(
            hass,
            {
                "command": 'echo "{{ states.sensor.input_sensor.state }}" "3 4"',
            },
        )

        # Give time for template to load
        async_fire_time_changed(
            hass,
            dt.utcnow() + timedelta(minutes=1),
        )
        await hass.async_block_till_done()

        assert len(check_output.mock_calls) == 2
        check_output.assert_called_with(
            'echo "sensor_value" "3 4"',
            shell=True,  # nosec # shell by design
            timeout=15,
            close_fds=False,
        )


async def test_bad_template_render(
    caplog: pytest.LogCaptureFixture, hass: HomeAssistant
) -> None:
    """Test rendering a broken template."""

    await setup_test_entities(
        hass,
        {
            "command": "echo {{ this template doesn't parse",
        },
    )

    assert "Error rendering command template" in caplog.text


async def test_bad_command(hass: HomeAssistant) -> None:
    """Test bad command."""
    await setup_test_entities(
        hass,
        {
            "command": "asdfasdf",
        },
    )
    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert entity_state.state == "unknown"


async def test_return_code(
    caplog: pytest.LogCaptureFixture, hass: HomeAssistant
) -> None:
    """Test that an error return code is logged."""
    await setup_test_entities(
        hass,
        {
            "command": "exit 33",
        },
    )
    assert "return code 33" in caplog.text


async def test_update_with_json_attrs(hass: HomeAssistant) -> None:
    """Test attributes get extracted from a JSON result."""
    await setup_test_entities(
        hass,
        {
            "command": (
                'echo { \\"key\\": \\"some_json_value\\", \\"another_key\\": '
                '\\"another_json_value\\", \\"key_three\\": \\"value_three\\" }'
            ),
            "json_attributes": ["key", "another_key", "key_three"],
        },
    )
    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert entity_state.state == "unknown"
    assert entity_state.attributes["key"] == "some_json_value"
    assert entity_state.attributes["another_key"] == "another_json_value"
    assert entity_state.attributes["key_three"] == "value_three"


async def test_update_with_json_attrs_and_value_template(hass: HomeAssistant) -> None:
    """Test json_attributes can be used together with value_template."""
    await setup_test_entities(
        hass,
        {
            "command": (
                'echo { \\"key\\": \\"some_json_value\\", \\"another_key\\": '
                '\\"another_json_value\\", \\"key_three\\": \\"value_three\\" }'
            ),
            "json_attributes": ["key", "another_key", "key_three"],
            "value_template": '{{ value_json["key"] }}',
        },
    )
    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert entity_state.state == "some_json_value"
    assert entity_state.attributes["key"] == "some_json_value"
    assert entity_state.attributes["another_key"] == "another_json_value"
    assert entity_state.attributes["key_three"] == "value_three"


async def test_update_with_json_attrs_no_data(
    caplog: pytest.LogCaptureFixture, hass: HomeAssistant
) -> None:
    """Test attributes when no JSON result fetched."""

    await setup_test_entities(
        hass,
        {
            "command": "echo",
            "json_attributes": ["key"],
        },
    )
    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert "key" not in entity_state.attributes
    assert "Empty reply found when expecting JSON data" in caplog.text


async def test_update_with_json_attrs_not_dict(
    caplog: pytest.LogCaptureFixture, hass: HomeAssistant
) -> None:
    """Test attributes when the return value not a dict."""

    await setup_test_entities(
        hass,
        {
            "command": "echo [1, 2, 3]",
            "json_attributes": ["key"],
        },
    )
    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert "key" not in entity_state.attributes
    assert "JSON result was not a dictionary" in caplog.text


async def test_update_with_json_attrs_bad_json(
    caplog: pytest.LogCaptureFixture, hass: HomeAssistant
) -> None:
    """Test attributes when the return value is invalid JSON."""

    await setup_test_entities(
        hass,
        {
            "command": "echo This is text rather than JSON data.",
            "json_attributes": ["key"],
        },
    )
    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert "key" not in entity_state.attributes
    assert "Unable to parse output as JSON" in caplog.text


async def test_update_with_missing_json_attrs(
    caplog: pytest.LogCaptureFixture, hass: HomeAssistant
) -> None:
    """Test attributes when an expected key is missing."""

    await setup_test_entities(
        hass,
        {
            "command": (
                'echo { \\"key\\": \\"some_json_value\\", \\"another_key\\": '
                '\\"another_json_value\\", \\"key_three\\": \\"value_three\\" }'
            ),
            "json_attributes": ["key", "another_key", "key_three", "missing_key"],
        },
    )
    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert entity_state.attributes["key"] == "some_json_value"
    assert entity_state.attributes["another_key"] == "another_json_value"
    assert entity_state.attributes["key_three"] == "value_three"
    assert "missing_key" not in entity_state.attributes


async def test_update_with_unnecessary_json_attrs(
    caplog: pytest.LogCaptureFixture, hass: HomeAssistant
) -> None:
    """Test attributes when an expected key is missing."""

    await setup_test_entities(
        hass,
        {
            "command": (
                'echo { \\"key\\": \\"some_json_value\\", \\"another_key\\": '
                '\\"another_json_value\\", \\"key_three\\": \\"value_three\\" }'
            ),
            "json_attributes": ["key", "another_key"],
        },
    )
    entity_state = hass.states.get("sensor.test")
    assert entity_state
    assert entity_state.attributes["key"] == "some_json_value"
    assert entity_state.attributes["another_key"] == "another_json_value"
    assert "key_three" not in entity_state.attributes


async def test_unique_id(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test unique_id option and if it only creates one sensor per id."""
    assert await setup.async_setup_component(
        hass,
        SENSOR_DOMAIN,
        {
            SENSOR_DOMAIN: [
                {
                    "platform": "command_line",
                    "unique_id": "unique",
                    "command": "echo 0",
                },
                {
                    "platform": "command_line",
                    "unique_id": "not-so-unique-anymore",
                    "command": "echo 1",
                },
                {
                    "platform": "command_line",
                    "unique_id": "not-so-unique-anymore",
                    "command": "echo 2",
                },
            ]
        },
    )
    await hass.async_block_till_done()

    assert len(hass.states.async_all()) == 2

    assert len(entity_registry.entities) == 2
    assert entity_registry.async_get_entity_id("sensor", "command_line", "unique")
    assert entity_registry.async_get_entity_id(
        "sensor", "command_line", "not-so-unique-anymore"
    )
