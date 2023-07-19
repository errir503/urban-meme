"""Test ESPHome update entities."""
import asyncio
from collections.abc import Awaitable, Callable
import dataclasses
from unittest.mock import Mock, patch

from aioesphomeapi import (
    APIClient,
    EntityInfo,
    EntityState,
    UserService,
)
import pytest

from homeassistant.components.esphome.dashboard import (
    async_get_dashboard,
)
from homeassistant.components.update import UpdateEntityFeature
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .conftest import MockESPHomeDevice


@pytest.fixture
def stub_reconnect():
    """Stub reconnect."""
    with patch("homeassistant.components.esphome.manager.ReconnectLogic.start"):
        yield


@pytest.mark.parametrize(
    ("devices_payload", "expected_state", "expected_attributes"),
    [
        (
            [
                {
                    "name": "test",
                    "current_version": "2023.2.0-dev",
                    "configuration": "test.yaml",
                }
            ],
            STATE_ON,
            {
                "latest_version": "2023.2.0-dev",
                "installed_version": "1.0.0",
                "supported_features": UpdateEntityFeature.INSTALL,
            },
        ),
        (
            [
                {
                    "name": "test",
                    "current_version": "1.0.0",
                },
            ],
            STATE_OFF,
            {
                "latest_version": "1.0.0",
                "installed_version": "1.0.0",
                "supported_features": 0,
            },
        ),
        (
            [],
            STATE_UNKNOWN,  # dashboard is available but device is unknown
            {"supported_features": 0},
        ),
    ],
)
async def test_update_entity(
    hass: HomeAssistant,
    stub_reconnect,
    mock_config_entry,
    mock_device_info,
    mock_dashboard,
    devices_payload,
    expected_state,
    expected_attributes,
) -> None:
    """Test ESPHome update entity."""
    mock_dashboard["configured"] = devices_payload
    await async_get_dashboard(hass).async_refresh()

    with patch(
        "homeassistant.components.esphome.update.DomainData.get_entry_data",
        return_value=Mock(available=True, device_info=mock_device_info),
    ):
        assert await hass.config_entries.async_forward_entry_setup(
            mock_config_entry, "update"
        )

    state = hass.states.get("update.none_firmware")
    assert state is not None
    assert state.state == expected_state
    for key, expected_value in expected_attributes.items():
        assert state.attributes.get(key) == expected_value

    if expected_state != "on":
        return

    # Compile failed, don't try to upload
    with patch(
        "esphome_dashboard_api.ESPHomeDashboardAPI.compile", return_value=False
    ) as mock_compile, patch(
        "esphome_dashboard_api.ESPHomeDashboardAPI.upload", return_value=True
    ) as mock_upload, pytest.raises(
        HomeAssistantError, match="compiling"
    ):
        await hass.services.async_call(
            "update",
            "install",
            {"entity_id": "update.none_firmware"},
            blocking=True,
        )

    assert len(mock_compile.mock_calls) == 1
    assert mock_compile.mock_calls[0][1][0] == "test.yaml"

    assert len(mock_upload.mock_calls) == 0

    # Compile success, upload fails
    with patch(
        "esphome_dashboard_api.ESPHomeDashboardAPI.compile", return_value=True
    ) as mock_compile, patch(
        "esphome_dashboard_api.ESPHomeDashboardAPI.upload", return_value=False
    ) as mock_upload, pytest.raises(
        HomeAssistantError, match="OTA"
    ):
        await hass.services.async_call(
            "update",
            "install",
            {"entity_id": "update.none_firmware"},
            blocking=True,
        )

    assert len(mock_compile.mock_calls) == 1
    assert mock_compile.mock_calls[0][1][0] == "test.yaml"

    assert len(mock_upload.mock_calls) == 1
    assert mock_upload.mock_calls[0][1][0] == "test.yaml"

    # Everything works
    with patch(
        "esphome_dashboard_api.ESPHomeDashboardAPI.compile", return_value=True
    ) as mock_compile, patch(
        "esphome_dashboard_api.ESPHomeDashboardAPI.upload", return_value=True
    ) as mock_upload:
        await hass.services.async_call(
            "update",
            "install",
            {"entity_id": "update.none_firmware"},
            blocking=True,
        )

    assert len(mock_compile.mock_calls) == 1
    assert mock_compile.mock_calls[0][1][0] == "test.yaml"

    assert len(mock_upload.mock_calls) == 1
    assert mock_upload.mock_calls[0][1][0] == "test.yaml"


async def test_update_static_info(
    hass: HomeAssistant,
    stub_reconnect,
    mock_config_entry,
    mock_device_info,
    mock_dashboard,
) -> None:
    """Test ESPHome update entity."""
    mock_dashboard["configured"] = [
        {
            "name": "test",
            "current_version": "1.2.3",
        },
    ]
    await async_get_dashboard(hass).async_refresh()

    signal_static_info_updated = f"esphome_{mock_config_entry.entry_id}_on_list"
    runtime_data = Mock(
        available=True,
        device_info=mock_device_info,
        signal_static_info_updated=signal_static_info_updated,
    )

    with patch(
        "homeassistant.components.esphome.update.DomainData.get_entry_data",
        return_value=runtime_data,
    ):
        assert await hass.config_entries.async_forward_entry_setup(
            mock_config_entry, "update"
        )

    state = hass.states.get("update.none_firmware")
    assert state is not None
    assert state.state == "on"

    runtime_data.device_info = dataclasses.replace(
        runtime_data.device_info, esphome_version="1.2.3"
    )
    async_dispatcher_send(hass, signal_static_info_updated, [])

    state = hass.states.get("update.none_firmware")
    assert state.state == "off"


@pytest.mark.parametrize(
    "expected_disconnect_state", [(True, STATE_ON), (False, STATE_UNAVAILABLE)]
)
async def test_update_device_state_for_availability(
    hass: HomeAssistant,
    stub_reconnect,
    expected_disconnect_state: tuple[bool, str],
    mock_config_entry,
    mock_device_info,
    mock_dashboard,
) -> None:
    """Test ESPHome update entity changes availability with the device."""
    mock_dashboard["configured"] = [
        {
            "name": "test",
            "current_version": "1.2.3",
        },
    ]
    await async_get_dashboard(hass).async_refresh()

    signal_device_updated = f"esphome_{mock_config_entry.entry_id}_on_device_update"
    runtime_data = Mock(
        available=True,
        expected_disconnect=False,
        device_info=mock_device_info,
        signal_device_updated=signal_device_updated,
    )

    with patch(
        "homeassistant.components.esphome.update.DomainData.get_entry_data",
        return_value=runtime_data,
    ):
        assert await hass.config_entries.async_forward_entry_setup(
            mock_config_entry, "update"
        )

    state = hass.states.get("update.none_firmware")
    assert state is not None
    assert state.state == "on"

    expected_disconnect, expected_state = expected_disconnect_state

    runtime_data.available = False
    runtime_data.expected_disconnect = expected_disconnect
    async_dispatcher_send(hass, signal_device_updated)

    state = hass.states.get("update.none_firmware")
    assert state.state == expected_state

    # Deep sleep devices should still be available
    runtime_data.device_info = dataclasses.replace(
        runtime_data.device_info, has_deep_sleep=True
    )

    async_dispatcher_send(hass, signal_device_updated)

    state = hass.states.get("update.none_firmware")
    assert state.state == "on"


async def test_update_entity_dashboard_not_available_startup(
    hass: HomeAssistant,
    stub_reconnect,
    mock_config_entry,
    mock_device_info,
    mock_dashboard,
) -> None:
    """Test ESPHome update entity when dashboard is not available at startup."""
    with patch(
        "homeassistant.components.esphome.update.DomainData.get_entry_data",
        return_value=Mock(available=True, device_info=mock_device_info),
    ), patch(
        "esphome_dashboard_api.ESPHomeDashboardAPI.get_devices",
        side_effect=asyncio.TimeoutError,
    ):
        await async_get_dashboard(hass).async_refresh()
        assert await hass.config_entries.async_forward_entry_setup(
            mock_config_entry, "update"
        )

    # We have a dashboard but it is not available
    state = hass.states.get("update.none_firmware")
    assert state is None

    mock_dashboard["configured"] = [
        {
            "name": "test",
            "current_version": "2023.2.0-dev",
            "configuration": "test.yaml",
        }
    ]
    await async_get_dashboard(hass).async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get("update.none_firmware")
    assert state.state == STATE_ON
    expected_attributes = {
        "latest_version": "2023.2.0-dev",
        "installed_version": "1.0.0",
        "supported_features": UpdateEntityFeature.INSTALL,
    }
    for key, expected_value in expected_attributes.items():
        assert state.attributes.get(key) == expected_value


async def test_update_entity_dashboard_discovered_after_startup_but_update_failed(
    hass: HomeAssistant,
    mock_client: APIClient,
    mock_esphome_device: Callable[
        [APIClient, list[EntityInfo], list[UserService], list[EntityState]],
        Awaitable[MockESPHomeDevice],
    ],
    mock_dashboard,
) -> None:
    """Test ESPHome update entity when dashboard is discovered after startup and the first update fails."""
    with patch(
        "esphome_dashboard_api.ESPHomeDashboardAPI.get_devices",
        side_effect=asyncio.TimeoutError,
    ):
        await async_get_dashboard(hass).async_refresh()
        await hass.async_block_till_done()
        mock_device = await mock_esphome_device(
            mock_client=mock_client,
            entity_info=[],
            user_service=[],
            states=[],
        )
        await hass.async_block_till_done()
    state = hass.states.get("update.test_firmware")
    assert state is None

    await mock_device.mock_disconnect(False)

    mock_dashboard["configured"] = [
        {
            "name": "test",
            "current_version": "2023.2.0-dev",
            "configuration": "test.yaml",
        }
    ]
    # Device goes unavailable, and dashboard becomes available
    await async_get_dashboard(hass).async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get("update.test_firmware")
    assert state is None

    # Finally both are available
    await mock_device.mock_connect()
    await async_get_dashboard(hass).async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("update.test_firmware")
    assert state is not None


async def test_update_entity_not_present_without_dashboard(
    hass: HomeAssistant, stub_reconnect, mock_config_entry, mock_device_info
) -> None:
    """Test ESPHome update entity does not get created if there is no dashboard."""
    with patch(
        "homeassistant.components.esphome.update.DomainData.get_entry_data",
        return_value=Mock(available=True, device_info=mock_device_info),
    ):
        assert await hass.config_entries.async_forward_entry_setup(
            mock_config_entry, "update"
        )

    state = hass.states.get("update.none_firmware")
    assert state is None
