"""Test UniFi Network integration setup process."""
from typing import Any
from unittest.mock import patch

from homeassistant.components import unifi
from homeassistant.components.unifi.const import DOMAIN as UNIFI_DOMAIN
from homeassistant.components.unifi.errors import AuthenticationRequired, CannotConnect
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from .test_controller import DEFAULT_CONFIG_ENTRY_ID, setup_unifi_integration

from tests.common import flush_store
from tests.test_util.aiohttp import AiohttpClientMocker


async def test_setup_with_no_config(hass: HomeAssistant) -> None:
    """Test that we do not discover anything or try to set up a controller."""
    assert await async_setup_component(hass, UNIFI_DOMAIN, {}) is True
    assert UNIFI_DOMAIN not in hass.data


async def test_successful_config_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test that configured options for a host are loaded via config entry."""
    await setup_unifi_integration(hass, aioclient_mock, unique_id=None)
    assert hass.data[UNIFI_DOMAIN]


async def test_setup_entry_fails_config_entry_not_ready(hass: HomeAssistant) -> None:
    """Failed authentication trigger a reauthentication flow."""
    with patch(
        "homeassistant.components.unifi.get_unifi_controller",
        side_effect=CannotConnect,
    ):
        await setup_unifi_integration(hass)

    assert hass.data[UNIFI_DOMAIN] == {}


async def test_setup_entry_fails_trigger_reauth_flow(hass: HomeAssistant) -> None:
    """Failed authentication trigger a reauthentication flow."""
    with patch(
        "homeassistant.components.unifi.get_unifi_controller",
        side_effect=AuthenticationRequired,
    ), patch.object(hass.config_entries.flow, "async_init") as mock_flow_init:
        await setup_unifi_integration(hass)
        mock_flow_init.assert_called_once()

    assert hass.data[UNIFI_DOMAIN] == {}


async def test_unload_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test being able to unload an entry."""
    config_entry = await setup_unifi_integration(hass, aioclient_mock)
    assert hass.data[UNIFI_DOMAIN]

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert not hass.data[UNIFI_DOMAIN]


async def test_wireless_clients(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Verify wireless clients class."""
    hass_storage[unifi.STORAGE_KEY] = {
        "version": unifi.STORAGE_VERSION,
        "data": {
            DEFAULT_CONFIG_ENTRY_ID: {
                "wireless_devices": ["00:00:00:00:00:00", "00:00:00:00:00:01"]
            }
        },
    }

    client_1 = {
        "hostname": "client_1",
        "ip": "10.0.0.1",
        "is_wired": False,
        "mac": "00:00:00:00:00:01",
    }
    client_2 = {
        "hostname": "client_2",
        "ip": "10.0.0.2",
        "is_wired": False,
        "mac": "00:00:00:00:00:02",
    }
    await setup_unifi_integration(
        hass, aioclient_mock, clients_response=[client_1, client_2]
    )
    await flush_store(hass.data[unifi.UNIFI_WIRELESS_CLIENTS]._store)

    assert sorted(hass_storage[unifi.STORAGE_KEY]["data"]["wireless_clients"]) == [
        "00:00:00:00:00:00",
        "00:00:00:00:00:01",
        "00:00:00:00:00:02",
    ]
