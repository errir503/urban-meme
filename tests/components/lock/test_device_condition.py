"""The tests for Lock device conditions."""
import pytest

import homeassistant.components.automation as automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.components.lock import DOMAIN
from homeassistant.const import (
    STATE_JAMMED,
    STATE_LOCKED,
    STATE_LOCKING,
    STATE_UNLOCKED,
    STATE_UNLOCKING,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryHider
from homeassistant.setup import async_setup_component

from tests.common import (
    MockConfigEntry,
    assert_lists_same,
    async_get_device_automations,
    async_mock_service,
)
from tests.components.blueprint.conftest import stub_blueprint_populate  # noqa: F401


@pytest.fixture
def calls(hass):
    """Track calls to a mock service."""
    return async_mock_service(hass, "test", "automation")


async def test_get_conditions(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test we get the expected conditions from a lock."""
    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
    )
    entity_registry.async_get_or_create(
        DOMAIN, "test", "5678", device_id=device_entry.id
    )
    expected_conditions = [
        {
            "condition": "device",
            "domain": DOMAIN,
            "type": condition,
            "device_id": device_entry.id,
            "entity_id": f"{DOMAIN}.test_5678",
            "metadata": {"secondary": False},
        }
        for condition in [
            "is_locked",
            "is_unlocked",
            "is_unlocking",
            "is_locking",
            "is_jammed",
        ]
    ]
    conditions = await async_get_device_automations(
        hass, DeviceAutomationType.CONDITION, device_entry.id
    )
    assert_lists_same(conditions, expected_conditions)


@pytest.mark.parametrize(
    ("hidden_by", "entity_category"),
    (
        (RegistryEntryHider.INTEGRATION, None),
        (RegistryEntryHider.USER, None),
        (None, EntityCategory.CONFIG),
        (None, EntityCategory.DIAGNOSTIC),
    ),
)
async def test_get_conditions_hidden_auxiliary(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    hidden_by,
    entity_category,
) -> None:
    """Test we get the expected conditions from a hidden or auxiliary entity."""
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
    expected_conditions = [
        {
            "condition": "device",
            "domain": DOMAIN,
            "type": condition,
            "device_id": device_entry.id,
            "entity_id": f"{DOMAIN}.test_5678",
            "metadata": {"secondary": True},
        }
        for condition in [
            "is_locked",
            "is_unlocked",
            "is_unlocking",
            "is_locking",
            "is_jammed",
        ]
    ]
    conditions = await async_get_device_automations(
        hass, DeviceAutomationType.CONDITION, device_entry.id
    )
    assert_lists_same(conditions, expected_conditions)


async def test_if_state(hass: HomeAssistant, calls) -> None:
    """Test for turn_on and turn_off conditions."""
    hass.states.async_set("lock.entity", STATE_LOCKED)

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {"platform": "event", "event_type": "test_event1"},
                    "condition": [
                        {
                            "condition": "device",
                            "domain": DOMAIN,
                            "device_id": "",
                            "entity_id": "lock.entity",
                            "type": "is_locked",
                        }
                    ],
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": "is_locked - {{ trigger.platform }} - {{ trigger.event.event_type }}"
                        },
                    },
                },
                {
                    "trigger": {"platform": "event", "event_type": "test_event2"},
                    "condition": [
                        {
                            "condition": "device",
                            "domain": DOMAIN,
                            "device_id": "",
                            "entity_id": "lock.entity",
                            "type": "is_unlocked",
                        }
                    ],
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": "is_unlocked - {{ trigger.platform }} - {{ trigger.event.event_type }}"
                        },
                    },
                },
                {
                    "trigger": {"platform": "event", "event_type": "test_event3"},
                    "condition": [
                        {
                            "condition": "device",
                            "domain": DOMAIN,
                            "device_id": "",
                            "entity_id": "lock.entity",
                            "type": "is_unlocking",
                        }
                    ],
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": "is_unlocking - {{ trigger.platform }} - {{ trigger.event.event_type }}"
                        },
                    },
                },
                {
                    "trigger": {"platform": "event", "event_type": "test_event4"},
                    "condition": [
                        {
                            "condition": "device",
                            "domain": DOMAIN,
                            "device_id": "",
                            "entity_id": "lock.entity",
                            "type": "is_locking",
                        }
                    ],
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": "is_locking - {{ trigger.platform }} - {{ trigger.event.event_type }}"
                        },
                    },
                },
                {
                    "trigger": {"platform": "event", "event_type": "test_event5"},
                    "condition": [
                        {
                            "condition": "device",
                            "domain": DOMAIN,
                            "device_id": "",
                            "entity_id": "lock.entity",
                            "type": "is_jammed",
                        }
                    ],
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": "is_jammed - {{ trigger.platform }} - {{ trigger.event.event_type }}"
                        },
                    },
                },
            ]
        },
    )
    hass.bus.async_fire("test_event1")
    hass.bus.async_fire("test_event2")
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["some"] == "is_locked - event - test_event1"

    hass.states.async_set("lock.entity", STATE_UNLOCKED)
    hass.bus.async_fire("test_event1")
    hass.bus.async_fire("test_event2")
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert calls[1].data["some"] == "is_unlocked - event - test_event2"

    hass.states.async_set("lock.entity", STATE_UNLOCKING)
    hass.bus.async_fire("test_event3")
    await hass.async_block_till_done()
    assert len(calls) == 3
    assert calls[2].data["some"] == "is_unlocking - event - test_event3"

    hass.states.async_set("lock.entity", STATE_LOCKING)
    hass.bus.async_fire("test_event4")
    await hass.async_block_till_done()
    assert len(calls) == 4
    assert calls[3].data["some"] == "is_locking - event - test_event4"

    hass.states.async_set("lock.entity", STATE_JAMMED)
    hass.bus.async_fire("test_event5")
    await hass.async_block_till_done()
    assert len(calls) == 5
    assert calls[4].data["some"] == "is_jammed - event - test_event5"
