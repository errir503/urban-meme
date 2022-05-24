"""Test the UniFi Protect button platform."""
# pylint: disable=protected-access
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pyunifiprotect.data.devices import Chime

from homeassistant.components.unifiprotect.const import DEFAULT_ATTRIBUTION
from homeassistant.const import ATTR_ATTRIBUTION, ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import MockEntityFixture, assert_entity_counts, enable_entity


@pytest.fixture(name="chime")
async def chime_fixture(
    hass: HomeAssistant, mock_entry: MockEntityFixture, mock_chime: Chime
):
    """Fixture for a single camera for testing the button platform."""

    chime_obj = mock_chime.copy(deep=True)
    chime_obj._api = mock_entry.api
    chime_obj.name = "Test Chime"

    mock_entry.api.bootstrap.chimes = {
        chime_obj.id: chime_obj,
    }

    await hass.config_entries.async_setup(mock_entry.entry.entry_id)
    await hass.async_block_till_done()

    assert_entity_counts(hass, Platform.BUTTON, 3, 2)

    return chime_obj


async def test_reboot_button(
    hass: HomeAssistant,
    mock_entry: MockEntityFixture,
    chime: Chime,
):
    """Test button entity."""

    mock_entry.api.reboot_device = AsyncMock()

    unique_id = f"{chime.id}_reboot"
    entity_id = "button.test_chime_reboot_device"

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get(entity_id)
    assert entity
    assert entity.disabled
    assert entity.unique_id == unique_id

    await enable_entity(hass, mock_entry.entry.entry_id, entity_id)
    state = hass.states.get(entity_id)
    assert state
    assert state.attributes[ATTR_ATTRIBUTION] == DEFAULT_ATTRIBUTION

    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_entry.api.reboot_device.assert_called_once()


async def test_chime_button(
    hass: HomeAssistant,
    mock_entry: MockEntityFixture,
    chime: Chime,
):
    """Test button entity."""

    mock_entry.api.play_speaker = AsyncMock()

    unique_id = f"{chime.id}_play"
    entity_id = "button.test_chime_play_chime"

    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get(entity_id)
    assert entity
    assert not entity.disabled
    assert entity.unique_id == unique_id

    state = hass.states.get(entity_id)
    assert state
    assert state.attributes[ATTR_ATTRIBUTION] == DEFAULT_ATTRIBUTION

    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_entry.api.play_speaker.assert_called_once()
