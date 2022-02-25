"""The tests for local file sensor platform."""
from unittest.mock import Mock, mock_open, patch

import pytest

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import mock_registry


@pytest.fixture
def entity_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_registry(hass)


@patch("os.path.isfile", Mock(return_value=True))
@patch("os.access", Mock(return_value=True))
async def test_file_value(hass: HomeAssistant) -> None:
    """Test the File sensor."""
    config = {
        "sensor": {"platform": "file", "name": "file1", "file_path": "mock.file1"}
    }

    m_open = mock_open(read_data="43\n45\n21")
    with patch(
        "homeassistant.components.file.sensor.open", m_open, create=True
    ), patch.object(hass.config, "is_allowed_path", return_value=True):
        assert await async_setup_component(hass, "sensor", config)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.file1")
    assert state.state == "21"


@patch("os.path.isfile", Mock(return_value=True))
@patch("os.access", Mock(return_value=True))
async def test_file_value_template(hass: HomeAssistant) -> None:
    """Test the File sensor with JSON entries."""
    config = {
        "sensor": {
            "platform": "file",
            "name": "file2",
            "file_path": "mock.file2",
            "value_template": "{{ value_json.temperature }}",
        }
    }

    data = (
        '{"temperature": 29, "humidity": 31}\n' + '{"temperature": 26, "humidity": 36}'
    )

    m_open = mock_open(read_data=data)
    with patch(
        "homeassistant.components.file.sensor.open", m_open, create=True
    ), patch.object(hass.config, "is_allowed_path", return_value=True):
        assert await async_setup_component(hass, "sensor", config)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.file2")
    assert state.state == "26"


@patch("os.path.isfile", Mock(return_value=True))
@patch("os.access", Mock(return_value=True))
async def test_file_empty(hass: HomeAssistant) -> None:
    """Test the File sensor with an empty file."""
    config = {"sensor": {"platform": "file", "name": "file3", "file_path": "mock.file"}}

    m_open = mock_open(read_data="")
    with patch(
        "homeassistant.components.file.sensor.open", m_open, create=True
    ), patch.object(hass.config, "is_allowed_path", return_value=True):
        assert await async_setup_component(hass, "sensor", config)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.file3")
    assert state.state == STATE_UNKNOWN


@patch("os.path.isfile", Mock(return_value=True))
@patch("os.access", Mock(return_value=True))
async def test_file_path_invalid(hass: HomeAssistant) -> None:
    """Test the File sensor with invalid path."""
    config = {
        "sensor": {"platform": "file", "name": "file4", "file_path": "mock.file4"}
    }

    m_open = mock_open(read_data="43\n45\n21")
    with patch(
        "homeassistant.components.file.sensor.open", m_open, create=True
    ), patch.object(hass.config, "is_allowed_path", return_value=False):
        assert await async_setup_component(hass, "sensor", config)
        await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids("sensor")) == 0
