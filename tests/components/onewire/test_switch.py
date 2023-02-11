"""Tests for 1-Wire switches."""
from collections.abc import Generator
import logging
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_STATE,
    SERVICE_TOGGLE,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.config_validation import ensure_list

from . import (
    check_and_enable_disabled_entities,
    check_device_registry,
    check_entities,
    setup_owproxy_mock_devices,
)
from .const import ATTR_DEVICE_INFO, ATTR_UNKNOWN_DEVICE, MOCK_OWPROXY_DEVICES


@pytest.fixture(autouse=True)
def override_platforms() -> Generator[None, None, None]:
    """Override PLATFORMS."""
    with patch("homeassistant.components.onewire.PLATFORMS", [Platform.SWITCH]):
        yield


async def test_switches(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    owproxy: MagicMock,
    device_id: str,
    caplog: pytest.LogCaptureFixture,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test for 1-Wire switch.

    This test forces all entities to be enabled.
    """
    mock_device = MOCK_OWPROXY_DEVICES[device_id]
    expected_entities = mock_device.get(Platform.SWITCH, [])
    expected_devices = ensure_list(mock_device.get(ATTR_DEVICE_INFO))

    setup_owproxy_mock_devices(owproxy, Platform.SWITCH, [device_id])
    with caplog.at_level(logging.WARNING, logger="homeassistant.components.onewire"):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        if mock_device.get(ATTR_UNKNOWN_DEVICE):
            assert "Ignoring unknown device family/type" in caplog.text
        else:
            assert "Ignoring unknown device family/type" not in caplog.text

    check_device_registry(device_registry, expected_devices)
    assert len(entity_registry.entities) == len(expected_entities)
    check_and_enable_disabled_entities(entity_registry, expected_entities)

    setup_owproxy_mock_devices(owproxy, Platform.SWITCH, [device_id])
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    check_entities(hass, entity_registry, expected_entities)

    # Test TOGGLE service
    for expected_entity in expected_entities:
        entity_id = expected_entity[ATTR_ENTITY_ID]

        if expected_entity[ATTR_STATE] == STATE_ON:
            owproxy.return_value.read.side_effect = [b"         0"]
            expected_entity[ATTR_STATE] = STATE_OFF
        elif expected_entity[ATTR_STATE] == STATE_OFF:
            owproxy.return_value.read.side_effect = [b"         1"]
            expected_entity[ATTR_STATE] = STATE_ON

        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TOGGLE,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()

        state = hass.states.get(entity_id)
        assert state.state == expected_entity[ATTR_STATE]
