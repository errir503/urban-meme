"""Global fixtures for Roborock integration."""
from unittest.mock import patch

import pytest

from .mock_data import PROP


@pytest.fixture(name="bypass_api_fixture")
def bypass_api_fixture() -> None:
    """Skip calls to the API."""
    with patch("homeassistant.components.roborock.RoborockMqttClient.connect"), patch(
        "homeassistant.components.roborock.RoborockMqttClient.send_command"
    ), patch(
        "homeassistant.components.roborock.coordinator.RoborockLocalClient.get_prop",
        return_value=PROP,
    ):
        yield
