"""The tests for the Ring component."""

import requests_mock

import homeassistant.components.ring as ring
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import load_fixture


async def test_setup(hass: HomeAssistant, requests_mock: requests_mock.Mocker) -> None:
    """Test the setup."""
    await async_setup_component(hass, ring.DOMAIN, {})

    requests_mock.post(
        "https://oauth.ring.com/oauth/token", text=load_fixture("oauth.json", "ring")
    )
    requests_mock.post(
        "https://api.ring.com/clients_api/session",
        text=load_fixture("session.json", "ring"),
    )
    requests_mock.get(
        "https://api.ring.com/clients_api/ring_devices",
        text=load_fixture("devices.json", "ring"),
    )
    requests_mock.get(
        "https://api.ring.com/clients_api/chimes/999999/health",
        text=load_fixture("chime_health_attrs.json", "ring"),
    )
    requests_mock.get(
        "https://api.ring.com/clients_api/doorbots/987652/health",
        text=load_fixture("doorboot_health_attrs.json", "ring"),
    )
