"""Setup mocks for the Plugwise integration tests."""
from __future__ import annotations

from collections.abc import Generator
from functools import partial
from http import HTTPStatus
import re
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import jsonpickle
from plugwise.exceptions import (
    ConnectionFailedError,
    InvalidAuthentication,
    PlugwiseException,
    XMLDataMissingError,
)
import pytest

from tests.common import load_fixture
from tests.test_util.aiohttp import AiohttpClientMocker


def _read_json(environment, call):
    """Undecode the json data."""
    fixture = load_fixture(f"plugwise/{environment}/{call}.json")
    return jsonpickle.decode(fixture)


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock, None, None]:
    """Mock setting up a config entry."""
    with patch(
        "homeassistant.components.plugwise.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture()
def mock_smile_config_flow() -> Generator[None, MagicMock, None]:
    """Return a mocked Smile client."""
    with patch(
        "homeassistant.components.plugwise.config_flow.Smile",
        autospec=True,
    ) as smile_mock:
        smile = smile_mock.return_value
        smile.smile_hostname = "smile12345"
        smile.smile_name = "Test Smile Name"
        smile.connect.return_value = True
        yield smile


@pytest.fixture(name="mock_smile_unauth")
def mock_smile_unauth(aioclient_mock: AiohttpClientMocker) -> None:
    """Mock the Plugwise Smile unauthorized for Home Assistant."""
    aioclient_mock.get(re.compile(".*"), status=HTTPStatus.UNAUTHORIZED)
    aioclient_mock.put(re.compile(".*"), status=HTTPStatus.UNAUTHORIZED)


@pytest.fixture(name="mock_smile_error")
def mock_smile_error(aioclient_mock: AiohttpClientMocker) -> None:
    """Mock the Plugwise Smile server failure for Home Assistant."""
    aioclient_mock.get(re.compile(".*"), status=HTTPStatus.INTERNAL_SERVER_ERROR)
    aioclient_mock.put(re.compile(".*"), status=HTTPStatus.INTERNAL_SERVER_ERROR)


@pytest.fixture(name="mock_smile_notconnect")
def mock_smile_notconnect():
    """Mock the Plugwise Smile general connection failure for Home Assistant."""
    with patch("homeassistant.components.plugwise.gateway.Smile") as smile_mock:
        smile_mock.InvalidAuthentication = InvalidAuthentication
        smile_mock.ConnectionFailedError = ConnectionFailedError
        smile_mock.PlugwiseException = PlugwiseException
        smile_mock.return_value.connect.side_effect = AsyncMock(return_value=False)
        yield smile_mock.return_value


def _get_device_data(chosen_env, device_id):
    """Mock return data for specific devices."""
    return _read_json(chosen_env, "get_device_data/" + device_id)


@pytest.fixture(name="mock_smile_adam")
def mock_smile_adam():
    """Create a Mock Adam environment for testing exceptions."""
    chosen_env = "adam_multiple_devices_per_zone"
    with patch("homeassistant.components.plugwise.gateway.Smile") as smile_mock:
        smile_mock.InvalidAuthentication = InvalidAuthentication
        smile_mock.ConnectionFailedError = ConnectionFailedError
        smile_mock.XMLDataMissingError = XMLDataMissingError

        smile_mock.return_value.gateway_id = "fe799307f1624099878210aa0b9f1475"
        smile_mock.return_value.heater_id = "90986d591dcd426cae3ec3e8111ff730"
        smile_mock.return_value.smile_version = "3.0.15"
        smile_mock.return_value.smile_type = "thermostat"
        smile_mock.return_value.smile_hostname = "smile98765"

        smile_mock.return_value.notifications = _read_json(chosen_env, "notifications")

        smile_mock.return_value.connect.side_effect = AsyncMock(return_value=True)
        smile_mock.return_value.full_update_device.side_effect = AsyncMock(
            return_value=True
        )
        smile_mock.return_value.single_master_thermostat.side_effect = Mock(
            return_value=False
        )
        smile_mock.return_value.set_schedule_state.side_effect = AsyncMock(
            return_value=True
        )
        smile_mock.return_value.set_preset.side_effect = AsyncMock(return_value=True)
        smile_mock.return_value.set_temperature.side_effect = AsyncMock(
            return_value=True
        )
        smile_mock.return_value.set_relay_state.side_effect = AsyncMock(
            return_value=True
        )

        smile_mock.return_value.get_all_devices.return_value = _read_json(
            chosen_env, "get_all_devices"
        )
        smile_mock.return_value.get_device_data.side_effect = partial(
            _get_device_data, chosen_env
        )

        yield smile_mock.return_value


@pytest.fixture(name="mock_smile_anna")
def mock_smile_anna():
    """Create a Mock Anna environment for testing exceptions."""
    chosen_env = "anna_heatpump"
    with patch("homeassistant.components.plugwise.gateway.Smile") as smile_mock:
        smile_mock.InvalidAuthentication = InvalidAuthentication
        smile_mock.ConnectionFailedError = ConnectionFailedError
        smile_mock.XMLDataMissingError = XMLDataMissingError

        smile_mock.return_value.gateway_id = "015ae9ea3f964e668e490fa39da3870b"
        smile_mock.return_value.heater_id = "1cbf783bb11e4a7c8a6843dee3a86927"
        smile_mock.return_value.smile_version = "4.0.15"
        smile_mock.return_value.smile_type = "thermostat"
        smile_mock.return_value.smile_hostname = "smile98765"

        smile_mock.return_value.notifications = _read_json(chosen_env, "notifications")

        smile_mock.return_value.connect.side_effect = AsyncMock(return_value=True)
        smile_mock.return_value.full_update_device.side_effect = AsyncMock(
            return_value=True
        )
        smile_mock.return_value.single_master_thermostat.side_effect = Mock(
            return_value=True
        )
        smile_mock.return_value.set_schedule_state.side_effect = AsyncMock(
            return_value=True
        )
        smile_mock.return_value.set_preset.side_effect = AsyncMock(return_value=True)
        smile_mock.return_value.set_temperature.side_effect = AsyncMock(
            return_value=True
        )
        smile_mock.return_value.set_relay_state.side_effect = AsyncMock(
            return_value=True
        )

        smile_mock.return_value.get_all_devices.return_value = _read_json(
            chosen_env, "get_all_devices"
        )
        smile_mock.return_value.get_device_data.side_effect = partial(
            _get_device_data, chosen_env
        )

        yield smile_mock.return_value


@pytest.fixture(name="mock_smile_p1")
def mock_smile_p1():
    """Create a Mock P1 DSMR environment for testing exceptions."""
    chosen_env = "p1v3_full_option"
    with patch("homeassistant.components.plugwise.gateway.Smile") as smile_mock:
        smile_mock.InvalidAuthentication = InvalidAuthentication
        smile_mock.ConnectionFailedError = ConnectionFailedError
        smile_mock.XMLDataMissingError = XMLDataMissingError

        smile_mock.return_value.gateway_id = "e950c7d5e1ee407a858e2a8b5016c8b3"
        smile_mock.return_value.heater_id = None
        smile_mock.return_value.smile_version = "3.3.9"
        smile_mock.return_value.smile_type = "power"
        smile_mock.return_value.smile_hostname = "smile98765"

        smile_mock.return_value.notifications = _read_json(chosen_env, "notifications")

        smile_mock.return_value.connect.side_effect = AsyncMock(return_value=True)
        smile_mock.return_value.full_update_device.side_effect = AsyncMock(
            return_value=True
        )

        smile_mock.return_value.single_master_thermostat.side_effect = Mock(
            return_value=None
        )

        smile_mock.return_value.get_all_devices.return_value = _read_json(
            chosen_env, "get_all_devices"
        )
        smile_mock.return_value.get_device_data.side_effect = partial(
            _get_device_data, chosen_env
        )

        yield smile_mock.return_value


@pytest.fixture(name="mock_stretch")
def mock_stretch():
    """Create a Mock Stretch environment for testing exceptions."""
    chosen_env = "stretch_v31"
    with patch("homeassistant.components.plugwise.gateway.Smile") as smile_mock:
        smile_mock.InvalidAuthentication = InvalidAuthentication
        smile_mock.ConnectionFailedError = ConnectionFailedError
        smile_mock.XMLDataMissingError = XMLDataMissingError

        smile_mock.return_value.gateway_id = "259882df3c05415b99c2d962534ce820"
        smile_mock.return_value.heater_id = None
        smile_mock.return_value.smile_version = "3.1.11"
        smile_mock.return_value.smile_type = "stretch"
        smile_mock.return_value.smile_hostname = "stretch98765"

        smile_mock.return_value.connect.side_effect = AsyncMock(return_value=True)
        smile_mock.return_value.full_update_device.side_effect = AsyncMock(
            return_value=True
        )
        smile_mock.return_value.set_relay_state.side_effect = AsyncMock(
            return_value=True
        )

        smile_mock.return_value.get_all_devices.return_value = _read_json(
            chosen_env, "get_all_devices"
        )
        smile_mock.return_value.get_device_data.side_effect = partial(
            _get_device_data, chosen_env
        )

        yield smile_mock.return_value
