"""The tests for Button device triggers."""
from __future__ import annotations

import pytest

from homeassistant.components import automation
from homeassistant.components.button import DOMAIN
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import (
    MockConfigEntry,
    assert_lists_same,
    async_get_device_automations,
    async_mock_service,
)


@pytest.fixture
def calls(hass: HomeAssistant) -> list[ServiceCall]:
    """Track calls to a mock service."""
    return async_mock_service(hass, "test", "automation")


async def test_get_triggers(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test we get the expected triggers from a button."""
    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
    )
    entity_registry.async_get_or_create(
        DOMAIN, "test", "5678", device_id=device_entry.id
    )
    expected_triggers = [
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": "pressed",
            "device_id": device_entry.id,
            "entity_id": f"{DOMAIN}.test_5678",
            "metadata": {"secondary": False},
        }
    ]
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_entry.id
    )
    assert_lists_same(triggers, expected_triggers)


@pytest.mark.parametrize(
    ("hidden_by", "entity_category"),
    (
        (er.RegistryEntryHider.INTEGRATION, None),
        (er.RegistryEntryHider.USER, None),
        (None, EntityCategory.CONFIG),
        (None, EntityCategory.DIAGNOSTIC),
    ),
)
async def test_get_triggers_hidden_auxiliary(
    hass,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    hidden_by: er.RegistryEntryHider | None,
    entity_category: EntityCategory | None,
):
    """Test we get the expected triggers from a hidden or auxiliary entity."""
    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
    )
    entity_registry.async_get_or_create(
        DOMAIN,
        "test",
        "5678",
        device_id=device_entry.id,
        entity_category=entity_category,
        hidden_by=hidden_by,
    )
    expected_triggers = [
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": trigger,
            "device_id": device_entry.id,
            "entity_id": f"{DOMAIN}.test_5678",
            "metadata": {"secondary": True},
        }
        for trigger in ["pressed"]
    ]
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_entry.id
    )
    assert_lists_same(triggers, expected_triggers)


async def test_if_fires_on_state_change(hass: HomeAssistant, calls) -> None:
    """Test for turn_on and turn_off triggers firing."""
    hass.states.async_set("button.entity", "unknown")

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": "",
                        "entity_id": "button.entity",
                        "type": "pressed",
                    },
                    "action": {
                        "service": "test.automation",
                        "data": {
                            "some": (
                                "to - {{ trigger.platform }} "
                                "- {{ trigger.entity_id }} "
                                "- {{ trigger.from_state.state }} "
                                "- {{ trigger.to_state.state }} "
                                "- {{ trigger.for }} "
                                "- {{ trigger.id }}"
                            )
                        },
                    },
                }
            ]
        },
    )

    # Test triggering device trigger with a to state
    hass.states.async_set("button.entity", "2021-01-01T23:59:59+00:00")
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data[
        "some"
    ] == "to - device - {} - unknown - 2021-01-01T23:59:59+00:00 - None - 0".format(
        "button.entity"
    )
