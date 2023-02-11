"""Test Home Assistant Cast."""
from unittest.mock import patch

import pytest

from homeassistant.components.cast import home_assistant_cast
from homeassistant.config import async_process_ha_core_config
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from tests.common import MockConfigEntry, async_mock_signal


async def test_service_show_view(hass: HomeAssistant, mock_zeroconf: None) -> None:
    """Test showing a view."""
    await home_assistant_cast.async_setup_ha_cast(hass, MockConfigEntry())
    calls = async_mock_signal(hass, home_assistant_cast.SIGNAL_HASS_CAST_SHOW_VIEW)

    # No valid URL
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "cast",
            "show_lovelace_view",
            {"entity_id": "media_player.kitchen", "view_path": "mock_path"},
            blocking=True,
        )

    # Set valid URL
    await async_process_ha_core_config(
        hass,
        {"external_url": "https://example.com"},
    )
    await hass.services.async_call(
        "cast",
        "show_lovelace_view",
        {"entity_id": "media_player.kitchen", "view_path": "mock_path"},
        blocking=True,
    )

    assert len(calls) == 1
    controller, entity_id, view_path, url_path = calls[0]
    assert controller.hass_url == "https://example.com"
    assert controller.client_id is None
    # Verify user did not accidentally submit their dev app id
    assert controller.supporting_app_id == "A078F6B0"
    assert entity_id == "media_player.kitchen"
    assert view_path == "mock_path"
    assert url_path is None


async def test_service_show_view_dashboard(
    hass: HomeAssistant, mock_zeroconf: None
) -> None:
    """Test casting a specific dashboard."""
    await async_process_ha_core_config(
        hass,
        {"external_url": "https://example.com"},
    )
    await home_assistant_cast.async_setup_ha_cast(hass, MockConfigEntry())
    calls = async_mock_signal(hass, home_assistant_cast.SIGNAL_HASS_CAST_SHOW_VIEW)

    await hass.services.async_call(
        "cast",
        "show_lovelace_view",
        {
            "entity_id": "media_player.kitchen",
            "view_path": "mock_path",
            "dashboard_path": "mock-dashboard",
        },
        blocking=True,
    )

    assert len(calls) == 1
    _controller, entity_id, view_path, url_path = calls[0]
    assert entity_id == "media_player.kitchen"
    assert view_path == "mock_path"
    assert url_path == "mock-dashboard"


async def test_use_cloud_url(hass: HomeAssistant, mock_zeroconf: None) -> None:
    """Test that we fall back to cloud url."""
    await async_process_ha_core_config(
        hass,
        {"internal_url": "http://example.local:8123"},
    )
    hass.config.components.add("cloud")

    await home_assistant_cast.async_setup_ha_cast(hass, MockConfigEntry())
    calls = async_mock_signal(hass, home_assistant_cast.SIGNAL_HASS_CAST_SHOW_VIEW)

    with patch(
        "homeassistant.components.cloud.async_remote_ui_url",
        return_value="https://something.nabu.casa",
    ):
        await hass.services.async_call(
            "cast",
            "show_lovelace_view",
            {"entity_id": "media_player.kitchen", "view_path": "mock_path"},
            blocking=True,
        )

    assert len(calls) == 1
    controller = calls[0][0]
    assert controller.hass_url == "https://something.nabu.casa"


async def test_remove_entry(hass: HomeAssistant, mock_zeroconf: None) -> None:
    """Test removing config entry removes user."""
    entry = MockConfigEntry(
        data={},
        domain="cast",
        title="Google Cast",
    )

    entry.add_to_hass(hass)

    with patch(
        "pychromecast.discovery.discover_chromecasts", return_value=(True, None)
    ), patch("pychromecast.discovery.stop_discovery"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert "cast" in hass.config.components

    user_id = entry.data.get("user_id")
    assert await hass.auth.async_get_user(user_id)

    assert await hass.config_entries.async_remove(entry.entry_id)
    assert not await hass.auth.async_get_user(user_id)
