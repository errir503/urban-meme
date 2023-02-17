"""The tests for Device Tracker device triggers."""
import pytest
import voluptuous_serialize

import homeassistant.components.automation as automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.components.device_tracker import DOMAIN, device_trigger
import homeassistant.components.zone as zone
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.entity_registry import RegistryEntryHider
from homeassistant.setup import async_setup_component

from tests.common import (
    MockConfigEntry,
    assert_lists_same,
    async_get_device_automations,
    async_mock_service,
)
from tests.components.blueprint.conftest import stub_blueprint_populate  # noqa: F401

AWAY_LATITUDE = 32.881011
AWAY_LONGITUDE = -117.234758

HOME_LATITUDE = 32.880837
HOME_LONGITUDE = -117.237561


@pytest.fixture
def calls(hass):
    """Track calls to a mock service."""
    return async_mock_service(hass, "test", "automation")


@pytest.fixture(autouse=True)
def setup_zone(hass):
    """Create test zone."""
    hass.loop.run_until_complete(
        async_setup_component(
            hass,
            zone.DOMAIN,
            {
                "zone": {
                    "name": "test",
                    "latitude": HOME_LATITUDE,
                    "longitude": HOME_LONGITUDE,
                    "radius": 250,
                }
            },
        )
    )


async def test_get_triggers(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test we get the expected triggers from a device_tracker."""
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
            "type": trigger,
            "device_id": device_entry.id,
            "entity_id": f"{DOMAIN}.test_5678",
            "metadata": {"secondary": False},
        }
        for trigger in ["leaves", "enters"]
    ]
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_entry.id
    )
    assert_lists_same(triggers, expected_triggers)


@pytest.mark.parametrize(
    ("hidden_by", "entity_category"),
    (
        (RegistryEntryHider.INTEGRATION, None),
        (RegistryEntryHider.USER, None),
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
        for trigger in ["leaves", "enters"]
    ]
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_entry.id
    )
    assert_lists_same(triggers, expected_triggers)


async def test_if_fires_on_zone_change(hass: HomeAssistant, calls) -> None:
    """Test for enter and leave triggers firing."""
    hass.states.async_set(
        "device_tracker.entity",
        "state",
        {"latitude": AWAY_LATITUDE, "longitude": AWAY_LONGITUDE},
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
                        "entity_id": "device_tracker.entity",
                        "type": "enters",
                        "zone": "zone.test",
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": (
                                "enter "
                                "- {{ trigger.platform }} "
                                "- {{ trigger.entity_id }} "
                                "- {{ "
                                "    trigger.from_state.attributes.longitude|round(3) "
                                "  }} "
                                "- {{ trigger.to_state.attributes.longitude|round(3) }}"
                            )
                        },
                    },
                },
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": "",
                        "entity_id": "device_tracker.entity",
                        "type": "leaves",
                        "zone": "zone.test",
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": (
                                "leave "
                                "- {{ trigger.platform }} "
                                "- {{ trigger.entity_id }} "
                                "- {{ "
                                "    trigger.from_state.attributes.longitude|round(3) "
                                "  }} "
                                "- {{ trigger.to_state.attributes.longitude|round(3)}}"
                            )
                        },
                    },
                },
            ]
        },
    )

    # Fake that the entity is entering.
    hass.states.async_set(
        "device_tracker.entity",
        "state",
        {"latitude": HOME_LATITUDE, "longitude": HOME_LONGITUDE},
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["some"] == "enter - device - {} - -117.235 - -117.238".format(
        "device_tracker.entity"
    )

    # Fake that the entity is leaving.
    hass.states.async_set(
        "device_tracker.entity",
        "state",
        {"latitude": AWAY_LATITUDE, "longitude": AWAY_LONGITUDE},
    )
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert calls[1].data["some"] == "leave - device - {} - -117.238 - -117.235".format(
        "device_tracker.entity"
    )


async def test_get_trigger_capabilities(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test we get the expected capabilities from a device_tracker trigger."""
    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
    )
    entity_registry.async_get_or_create(
        DOMAIN, "test", "5678", device_id=device_entry.id
    )
    capabilities = await device_trigger.async_get_trigger_capabilities(
        hass,
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": "enters",
            "device_id": device_entry.id,
            "entity_id": f"{DOMAIN}.test_5678",
        },
    )
    assert capabilities and "extra_fields" in capabilities

    assert voluptuous_serialize.convert(
        capabilities["extra_fields"], custom_serializer=cv.custom_serializer
    ) == [
        {
            "name": "zone",
            "required": True,
            "type": "select",
            "options": [("zone.test", "test"), ("zone.home", "test home")],
        }
    ]
