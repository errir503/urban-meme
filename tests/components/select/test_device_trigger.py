"""The tests for Select device triggers."""
from __future__ import annotations

import pytest
import voluptuous_serialize

from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.components.select import DOMAIN
from homeassistant.components.select.device_trigger import (
    async_get_trigger_capabilities,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
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
    """Test we get the expected triggers from a select."""
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
            "type": "current_option_changed",
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
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    hidden_by,
    entity_category,
) -> None:
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
        for trigger in ["current_option_changed"]
    ]
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_entry.id
    )
    assert_lists_same(triggers, expected_triggers)


async def test_if_fires_on_state_change(hass: HomeAssistant, calls) -> None:
    """Test for turn_on and turn_off triggers firing."""
    hass.states.async_set(
        "select.entity", "option1", {"options": ["option1", "option2", "option3"]}
    )

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
                        "entity_id": "select.entity",
                        "type": "current_option_changed",
                        "to": "option2",
                    },
                    "action": {
                        "service": "test.automation",
                        "data": {
                            "some": (
                                "to - {{ trigger.platform}} - "
                                "{{ trigger.entity_id}} - {{ trigger.from_state.state}} - "
                                "{{ trigger.to_state.state}} - {{ trigger.for }} - "
                                "{{ trigger.id}}"
                            )
                        },
                    },
                },
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": "",
                        "entity_id": "select.entity",
                        "type": "current_option_changed",
                        "from": "option2",
                    },
                    "action": {
                        "service": "test.automation",
                        "data": {
                            "some": (
                                "from - {{ trigger.platform}} - "
                                "{{ trigger.entity_id}} - {{ trigger.from_state.state}} - "
                                "{{ trigger.to_state.state}} - {{ trigger.for }} - "
                                "{{ trigger.id}}"
                            )
                        },
                    },
                },
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": "",
                        "entity_id": "select.entity",
                        "type": "current_option_changed",
                        "from": "option3",
                        "to": "option1",
                    },
                    "action": {
                        "service": "test.automation",
                        "data": {
                            "some": (
                                "from-to - {{ trigger.platform}} - "
                                "{{ trigger.entity_id}} - {{ trigger.from_state.state}} - "
                                "{{ trigger.to_state.state}} - {{ trigger.for }} - "
                                "{{ trigger.id}}"
                            )
                        },
                    },
                },
            ]
        },
    )

    # Test triggering device trigger with a to state
    hass.states.async_set("select.entity", "option2")
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data[
        "some"
    ] == "to - device - {} - option1 - option2 - None - 0".format("select.entity")

    # Test triggering device trigger with a from state
    hass.states.async_set("select.entity", "option3")
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert calls[1].data[
        "some"
    ] == "from - device - {} - option2 - option3 - None - 0".format("select.entity")

    # Test triggering device trigger with both a from and to state
    hass.states.async_set("select.entity", "option1")
    await hass.async_block_till_done()
    assert len(calls) == 3
    assert calls[2].data[
        "some"
    ] == "from-to - device - {} - option3 - option1 - None - 0".format("select.entity")


async def test_get_trigger_capabilities(hass: HomeAssistant) -> None:
    """Test we get the expected capabilities from a select trigger."""
    config = {
        "platform": "device",
        "domain": DOMAIN,
        "type": "current_option_changed",
        "entity_id": "select.test",
        "to": "option1",
    }

    # Test when entity doesn't exists
    capabilities = await async_get_trigger_capabilities(hass, config)
    assert capabilities
    assert "extra_fields" in capabilities
    assert voluptuous_serialize.convert(
        capabilities["extra_fields"], custom_serializer=cv.custom_serializer
    ) == [
        {
            "name": "from",
            "optional": True,
            "type": "select",
            "options": [],
        },
        {
            "name": "to",
            "optional": True,
            "type": "select",
            "options": [],
        },
        {
            "name": "for",
            "optional": True,
            "type": "positive_time_period_dict",
        },
    ]

    # Mock an entity
    hass.states.async_set("select.test", "option1", {"options": ["option1", "option2"]})

    # Test if we get the right capabilities now
    capabilities = await async_get_trigger_capabilities(hass, config)
    assert capabilities
    assert "extra_fields" in capabilities
    assert voluptuous_serialize.convert(
        capabilities["extra_fields"], custom_serializer=cv.custom_serializer
    ) == [
        {
            "name": "from",
            "optional": True,
            "type": "select",
            "options": [("option1", "option1"), ("option2", "option2")],
        },
        {
            "name": "to",
            "optional": True,
            "type": "select",
            "options": [("option1", "option1"), ("option2", "option2")],
        },
        {
            "name": "for",
            "optional": True,
            "type": "positive_time_period_dict",
        },
    ]
