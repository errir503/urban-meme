"""Test the MySensors config flow."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.components.mysensors.const import (
    CONF_BAUD_RATE,
    CONF_DEVICE,
    CONF_GATEWAY_TYPE,
    CONF_GATEWAY_TYPE_MQTT,
    CONF_GATEWAY_TYPE_SERIAL,
    CONF_GATEWAY_TYPE_TCP,
    CONF_PERSISTENCE_FILE,
    CONF_RETAIN,
    CONF_TCP_PORT,
    CONF_TOPIC_IN_PREFIX,
    CONF_TOPIC_OUT_PREFIX,
    CONF_VERSION,
    DOMAIN,
    ConfGatewayType,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from tests.common import MockConfigEntry


async def get_form(
    hass: HomeAssistant, gatway_type: ConfGatewayType, expected_step_id: str
) -> FlowResult:
    """Get a form for the given gateway type."""

    stepuser = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert stepuser["type"] == "form"
    assert not stepuser["errors"]

    result = await hass.config_entries.flow.async_configure(
        stepuser["flow_id"],
        {CONF_GATEWAY_TYPE: gatway_type},
    )
    await hass.async_block_till_done()
    assert result["type"] == "form"
    assert result["step_id"] == expected_step_id

    return result


async def test_config_mqtt(hass: HomeAssistant, mqtt: None) -> None:
    """Test configuring a mqtt gateway."""
    step = await get_form(hass, CONF_GATEWAY_TYPE_MQTT, "gw_mqtt")
    flow_id = step["flow_id"]

    with patch(
        "homeassistant.components.mysensors.async_setup", return_value=True
    ) as mock_setup, patch(
        "homeassistant.components.mysensors.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            flow_id,
            {
                CONF_RETAIN: True,
                CONF_TOPIC_IN_PREFIX: "bla",
                CONF_TOPIC_OUT_PREFIX: "blub",
                CONF_VERSION: "2.4",
            },
        )
        await hass.async_block_till_done()

    if "errors" in result2:
        assert not result2["errors"]
    assert result2["type"] == "create_entry"
    assert result2["title"] == "mqtt"
    assert result2["data"] == {
        CONF_DEVICE: "mqtt",
        CONF_RETAIN: True,
        CONF_TOPIC_IN_PREFIX: "bla",
        CONF_TOPIC_OUT_PREFIX: "blub",
        CONF_VERSION: "2.4",
        CONF_GATEWAY_TYPE: "MQTT",
    }
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


async def test_missing_mqtt(hass: HomeAssistant) -> None:
    """Test configuring a mqtt gateway without mqtt integration setup."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert not result["errors"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT},
    )
    assert result["step_id"] == "user"
    assert result["type"] == "form"
    assert result["errors"] == {"base": "mqtt_required"}


async def test_config_serial(hass: HomeAssistant) -> None:
    """Test configuring a gateway via serial."""
    step = await get_form(hass, CONF_GATEWAY_TYPE_SERIAL, "gw_serial")
    flow_id = step["flow_id"]

    with patch(  # mock is_serial_port because otherwise the test will be platform dependent (/dev/ttyACMx vs COMx)
        "homeassistant.components.mysensors.config_flow.is_serial_port",
        return_value=True,
    ), patch(
        "homeassistant.components.mysensors.config_flow.try_connect", return_value=True
    ), patch(
        "homeassistant.components.mysensors.async_setup", return_value=True
    ) as mock_setup, patch(
        "homeassistant.components.mysensors.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            flow_id,
            {
                CONF_BAUD_RATE: 115200,
                CONF_DEVICE: "/dev/ttyACM0",
                CONF_VERSION: "2.4",
            },
        )
        await hass.async_block_till_done()

    if "errors" in result2:
        assert not result2["errors"]
    assert result2["type"] == "create_entry"
    assert result2["title"] == "/dev/ttyACM0"
    assert result2["data"] == {
        CONF_DEVICE: "/dev/ttyACM0",
        CONF_BAUD_RATE: 115200,
        CONF_VERSION: "2.4",
        CONF_GATEWAY_TYPE: "Serial",
    }
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


async def test_config_tcp(hass: HomeAssistant) -> None:
    """Test configuring a gateway via tcp."""
    step = await get_form(hass, CONF_GATEWAY_TYPE_TCP, "gw_tcp")
    flow_id = step["flow_id"]

    with patch(
        "homeassistant.components.mysensors.config_flow.try_connect", return_value=True
    ), patch(
        "homeassistant.components.mysensors.async_setup", return_value=True
    ) as mock_setup, patch(
        "homeassistant.components.mysensors.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            flow_id,
            {
                CONF_TCP_PORT: 5003,
                CONF_DEVICE: "127.0.0.1",
                CONF_VERSION: "2.4",
            },
        )
        await hass.async_block_till_done()

    if "errors" in result2:
        assert not result2["errors"]
    assert result2["type"] == "create_entry"
    assert result2["title"] == "127.0.0.1"
    assert result2["data"] == {
        CONF_DEVICE: "127.0.0.1",
        CONF_TCP_PORT: 5003,
        CONF_VERSION: "2.4",
        CONF_GATEWAY_TYPE: "TCP",
    }
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


async def test_fail_to_connect(hass: HomeAssistant) -> None:
    """Test configuring a gateway via tcp."""
    step = await get_form(hass, CONF_GATEWAY_TYPE_TCP, "gw_tcp")
    flow_id = step["flow_id"]

    with patch(
        "homeassistant.components.mysensors.config_flow.try_connect", return_value=False
    ), patch(
        "homeassistant.components.mysensors.async_setup", return_value=True
    ) as mock_setup, patch(
        "homeassistant.components.mysensors.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            flow_id,
            {
                CONF_TCP_PORT: 5003,
                CONF_DEVICE: "127.0.0.1",
                CONF_VERSION: "2.4",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert "errors" in result2
    errors = result2["errors"]
    assert errors
    assert errors.get("base") == "cannot_connect"
    assert len(mock_setup.mock_calls) == 0
    assert len(mock_setup_entry.mock_calls) == 0


@pytest.mark.parametrize(
    "gateway_type, expected_step_id, user_input, err_field, err_string",
    [
        (
            CONF_GATEWAY_TYPE_TCP,
            "gw_tcp",
            {
                CONF_TCP_PORT: 600_000,
                CONF_DEVICE: "127.0.0.1",
                CONF_VERSION: "2.4",
            },
            CONF_TCP_PORT,
            "port_out_of_range",
        ),
        (
            CONF_GATEWAY_TYPE_TCP,
            "gw_tcp",
            {
                CONF_TCP_PORT: 0,
                CONF_DEVICE: "127.0.0.1",
                CONF_VERSION: "2.4",
            },
            CONF_TCP_PORT,
            "port_out_of_range",
        ),
        (
            CONF_GATEWAY_TYPE_TCP,
            "gw_tcp",
            {
                CONF_TCP_PORT: 5003,
                CONF_DEVICE: "127.0.0.1",
                CONF_VERSION: "a",
            },
            CONF_VERSION,
            "invalid_version",
        ),
        (
            CONF_GATEWAY_TYPE_TCP,
            "gw_tcp",
            {
                CONF_TCP_PORT: 5003,
                CONF_DEVICE: "127.0.0.1",
                CONF_VERSION: "a.b",
            },
            CONF_VERSION,
            "invalid_version",
        ),
        (
            CONF_GATEWAY_TYPE_TCP,
            "gw_tcp",
            {
                CONF_TCP_PORT: 5003,
                CONF_DEVICE: "127.0.0.1",
                CONF_VERSION: "4",
            },
            CONF_VERSION,
            "invalid_version",
        ),
        (
            CONF_GATEWAY_TYPE_TCP,
            "gw_tcp",
            {
                CONF_TCP_PORT: 5003,
                CONF_DEVICE: "127.0.0.1",
                CONF_VERSION: "v3",
            },
            CONF_VERSION,
            "invalid_version",
        ),
        (
            CONF_GATEWAY_TYPE_TCP,
            "gw_tcp",
            {
                CONF_TCP_PORT: 5003,
                CONF_DEVICE: "127.0.0.",
                CONF_VERSION: "2.4",
            },
            CONF_DEVICE,
            "invalid_ip",
        ),
        (
            CONF_GATEWAY_TYPE_TCP,
            "gw_tcp",
            {
                CONF_TCP_PORT: 5003,
                CONF_DEVICE: "abcd",
                CONF_VERSION: "2.4",
            },
            CONF_DEVICE,
            "invalid_ip",
        ),
        (
            CONF_GATEWAY_TYPE_MQTT,
            "gw_mqtt",
            {
                CONF_RETAIN: True,
                CONF_TOPIC_IN_PREFIX: "bla",
                CONF_TOPIC_OUT_PREFIX: "blub",
                CONF_PERSISTENCE_FILE: "asdf.zip",
                CONF_VERSION: "2.4",
            },
            CONF_PERSISTENCE_FILE,
            "invalid_persistence_file",
        ),
        (
            CONF_GATEWAY_TYPE_MQTT,
            "gw_mqtt",
            {
                CONF_RETAIN: True,
                CONF_TOPIC_IN_PREFIX: "/#/#",
                CONF_TOPIC_OUT_PREFIX: "blub",
                CONF_VERSION: "2.4",
            },
            CONF_TOPIC_IN_PREFIX,
            "invalid_subscribe_topic",
        ),
        (
            CONF_GATEWAY_TYPE_MQTT,
            "gw_mqtt",
            {
                CONF_RETAIN: True,
                CONF_TOPIC_IN_PREFIX: "asdf",
                CONF_TOPIC_OUT_PREFIX: "/#/#",
                CONF_VERSION: "2.4",
            },
            CONF_TOPIC_OUT_PREFIX,
            "invalid_publish_topic",
        ),
        (
            CONF_GATEWAY_TYPE_MQTT,
            "gw_mqtt",
            {
                CONF_RETAIN: True,
                CONF_TOPIC_IN_PREFIX: "asdf",
                CONF_TOPIC_OUT_PREFIX: "asdf",
                CONF_VERSION: "2.4",
            },
            CONF_TOPIC_OUT_PREFIX,
            "same_topic",
        ),
    ],
)
async def test_config_invalid(
    hass: HomeAssistant,
    mqtt: None,
    gateway_type: ConfGatewayType,
    expected_step_id: str,
    user_input: dict[str, Any],
    err_field: str,
    err_string: str,
) -> None:
    """Perform a test that is expected to generate an error."""
    step = await get_form(hass, gateway_type, expected_step_id)
    flow_id = step["flow_id"]

    with patch(
        "homeassistant.components.mysensors.config_flow.try_connect", return_value=True
    ), patch(
        "homeassistant.components.mysensors.gateway.socket.getaddrinfo",
        side_effect=OSError,
    ), patch(
        "homeassistant.components.mysensors.async_setup", return_value=True
    ) as mock_setup, patch(
        "homeassistant.components.mysensors.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            flow_id,
            user_input,
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert "errors" in result2
    errors = result2["errors"]
    assert errors
    assert err_field in errors
    assert errors[err_field] == err_string
    assert len(mock_setup.mock_calls) == 0
    assert len(mock_setup_entry.mock_calls) == 0


@pytest.mark.parametrize(
    "first_input, second_input, expected_result",
    [
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_DEVICE: "mqtt",
                CONF_VERSION: "2.3",
                CONF_TOPIC_IN_PREFIX: "same1",
                CONF_TOPIC_OUT_PREFIX: "same2",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_VERSION: "2.3",
                CONF_TOPIC_IN_PREFIX: "same1",
                CONF_TOPIC_OUT_PREFIX: "same2",
            },
            FlowResult(type="form", errors={CONF_TOPIC_IN_PREFIX: "duplicate_topic"}),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_DEVICE: "mqtt",
                CONF_VERSION: "2.3",
                CONF_TOPIC_IN_PREFIX: "different1",
                CONF_TOPIC_OUT_PREFIX: "different2",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_VERSION: "2.3",
                CONF_TOPIC_IN_PREFIX: "different3",
                CONF_TOPIC_OUT_PREFIX: "different4",
            },
            FlowResult(type="create_entry"),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_DEVICE: "mqtt",
                CONF_VERSION: "2.3",
                CONF_TOPIC_IN_PREFIX: "same1",
                CONF_TOPIC_OUT_PREFIX: "different2",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_VERSION: "2.3",
                CONF_TOPIC_IN_PREFIX: "same1",
                CONF_TOPIC_OUT_PREFIX: "different4",
            },
            FlowResult(type="form", errors={CONF_TOPIC_IN_PREFIX: "duplicate_topic"}),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_DEVICE: "mqtt",
                CONF_VERSION: "2.3",
                CONF_TOPIC_IN_PREFIX: "same1",
                CONF_TOPIC_OUT_PREFIX: "different2",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_VERSION: "2.3",
                CONF_TOPIC_IN_PREFIX: "different1",
                CONF_TOPIC_OUT_PREFIX: "same1",
            },
            FlowResult(type="form", errors={CONF_TOPIC_OUT_PREFIX: "duplicate_topic"}),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_DEVICE: "mqtt",
                CONF_VERSION: "2.3",
                CONF_TOPIC_IN_PREFIX: "same1",
                CONF_TOPIC_OUT_PREFIX: "different2",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_VERSION: "2.3",
                CONF_TOPIC_IN_PREFIX: "same1",
                CONF_TOPIC_OUT_PREFIX: "different1",
            },
            FlowResult(type="form", errors={CONF_TOPIC_IN_PREFIX: "duplicate_topic"}),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "127.0.0.1",
                CONF_PERSISTENCE_FILE: "same.json",
                CONF_TCP_PORT: 343,
                CONF_VERSION: "2.3",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "192.168.1.2",
                CONF_PERSISTENCE_FILE: "same.json",
                CONF_TCP_PORT: 343,
                CONF_VERSION: "2.3",
            },
            FlowResult(
                type="form", errors={"persistence_file": "duplicate_persistence_file"}
            ),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "127.0.0.1",
                CONF_TCP_PORT: 343,
                CONF_VERSION: "2.3",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "192.168.1.2",
                CONF_PERSISTENCE_FILE: "same.json",
                CONF_TCP_PORT: 343,
                CONF_VERSION: "2.3",
            },
            FlowResult(type="create_entry"),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "127.0.0.1",
                CONF_TCP_PORT: 343,
                CONF_VERSION: "2.3",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "192.168.1.2",
                CONF_TCP_PORT: 343,
                CONF_VERSION: "2.3",
            },
            FlowResult(type="create_entry"),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "192.168.1.2",
                CONF_PERSISTENCE_FILE: "different1.json",
                CONF_TCP_PORT: 343,
                CONF_VERSION: "2.3",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "192.168.1.2",
                CONF_PERSISTENCE_FILE: "different2.json",
                CONF_TCP_PORT: 343,
                CONF_VERSION: "2.3",
            },
            FlowResult(type="form", errors={"base": "already_configured"}),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "192.168.1.2",
                CONF_PERSISTENCE_FILE: "different1.json",
                CONF_TCP_PORT: 343,
                CONF_VERSION: "2.3",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "192.168.1.2",
                CONF_PERSISTENCE_FILE: "different2.json",
                CONF_TCP_PORT: 5003,
                CONF_VERSION: "2.3",
            },
            FlowResult(type="create_entry"),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "192.168.1.2",
                CONF_TCP_PORT: 5003,
                CONF_VERSION: "2.3",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_TCP,
                CONF_DEVICE: "192.168.1.3",
                CONF_TCP_PORT: 5003,
                CONF_VERSION: "2.3",
            },
            FlowResult(type="create_entry"),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_SERIAL,
                CONF_DEVICE: "COM5",
                CONF_VERSION: "2.3",
                CONF_PERSISTENCE_FILE: "different1.json",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_SERIAL,
                CONF_DEVICE: "COM5",
                CONF_VERSION: "2.3",
                CONF_PERSISTENCE_FILE: "different2.json",
            },
            FlowResult(type="form", errors={"base": "already_configured"}),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_SERIAL,
                CONF_DEVICE: "COM6",
                CONF_BAUD_RATE: 57600,
                CONF_VERSION: "2.3",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_SERIAL,
                CONF_DEVICE: "COM5",
                CONF_VERSION: "2.3",
            },
            FlowResult(type="create_entry"),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_SERIAL,
                CONF_DEVICE: "COM5",
                CONF_BAUD_RATE: 115200,
                CONF_VERSION: "2.3",
                CONF_PERSISTENCE_FILE: "different1.json",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_SERIAL,
                CONF_DEVICE: "COM5",
                CONF_BAUD_RATE: 57600,
                CONF_VERSION: "2.3",
                CONF_PERSISTENCE_FILE: "different2.json",
            },
            FlowResult(type="form", errors={"base": "already_configured"}),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_SERIAL,
                CONF_DEVICE: "COM5",
                CONF_BAUD_RATE: 115200,
                CONF_VERSION: "2.3",
                CONF_PERSISTENCE_FILE: "same.json",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_SERIAL,
                CONF_DEVICE: "COM6",
                CONF_BAUD_RATE: 57600,
                CONF_VERSION: "2.3",
                CONF_PERSISTENCE_FILE: "same.json",
            },
            FlowResult(
                type="form", errors={"persistence_file": "duplicate_persistence_file"}
            ),
        ),
        (
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_MQTT,
                CONF_DEVICE: "mqtt",
                CONF_PERSISTENCE_FILE: "bla.json",
                CONF_VERSION: "1.4",
            },
            {
                CONF_GATEWAY_TYPE: CONF_GATEWAY_TYPE_SERIAL,
                CONF_DEVICE: "COM6",
                CONF_PERSISTENCE_FILE: "bla2.json",
                CONF_BAUD_RATE: 115200,
                CONF_VERSION: "1.4",
            },
            FlowResult(type="create_entry"),
        ),
    ],
)
async def test_duplicate(
    hass: HomeAssistant,
    mqtt: None,
    first_input: dict,
    second_input: dict,
    expected_result: FlowResult,
) -> None:
    """Test duplicate detection."""

    with patch("sys.platform", "win32"), patch(
        "homeassistant.components.mysensors.config_flow.try_connect", return_value=True
    ), patch(
        "homeassistant.components.mysensors.async_setup_entry",
        return_value=True,
    ):
        MockConfigEntry(domain=DOMAIN, data=first_input).add_to_hass(hass)

        second_gateway_type = second_input.pop(CONF_GATEWAY_TYPE)
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            data={CONF_GATEWAY_TYPE: second_gateway_type},
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            second_input,
        )
        await hass.async_block_till_done()

        for key, val in expected_result.items():
            assert result[key] == val  # type: ignore[literal-required]
