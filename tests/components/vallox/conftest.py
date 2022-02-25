"""Common utilities for Vallox tests."""

import random
import string
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
from vallox_websocket_api.vallox import PROFILE

from homeassistant.components.vallox.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


@pytest.fixture
def mock_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create mocked Vallox config entry."""
    vallox_mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.100.50",
            CONF_NAME: "Vallox",
        },
    )
    vallox_mock_entry.add_to_hass(hass)

    return vallox_mock_entry


def patch_metrics(metrics: dict[str, Any]):
    """Patch the Vallox metrics response."""
    return patch(
        "homeassistant.components.vallox.Vallox.fetch_metrics",
        return_value=metrics,
    )


@pytest.fixture(autouse=True)
def patch_profile_home():
    """Patch the Vallox profile response."""
    with patch(
        "homeassistant.components.vallox.Vallox.get_profile",
        return_value=PROFILE.HOME,
    ):
        yield


@pytest.fixture(autouse=True)
def patch_uuid():
    """Patch the Vallox entity UUID."""
    with patch(
        "homeassistant.components.vallox.calculate_uuid",
        return_value=_random_uuid(),
    ):
        yield


def _random_uuid():
    """Generate a random UUID."""
    uuid = "".join(random.choices(string.hexdigits, k=32))
    return UUID(uuid)
