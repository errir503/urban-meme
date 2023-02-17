"""The tests for Climate device triggers."""
import pytest
import voluptuous_serialize

import homeassistant.components.automation as automation
from homeassistant.components.climate import (
    DOMAIN,
    HVACAction,
    HVACMode,
    const,
    device_trigger,
)
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.const import EntityCategory, UnitOfTemperature
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


@pytest.fixture
def calls(hass):
    """Track calls to a mock service."""
    return async_mock_service(hass, "test", "automation")


async def test_get_triggers(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test we get the expected triggers from a climate device."""
    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
    )
    entity_registry.async_get_or_create(
        DOMAIN, "test", "5678", device_id=device_entry.id
    )
    entity_id = f"{DOMAIN}.test_5678"
    hass.states.async_set(
        entity_id,
        HVACMode.COOL,
        {
            const.ATTR_HVAC_ACTION: HVACAction.IDLE,
            const.ATTR_CURRENT_HUMIDITY: 23,
            const.ATTR_CURRENT_TEMPERATURE: 18,
        },
    )
    expected_triggers = [
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": trigger,
            "device_id": device_entry.id,
            "entity_id": entity_id,
            "metadata": {"secondary": False},
        }
        for trigger in [
            "hvac_mode_changed",
            "current_temperature_changed",
            "current_humidity_changed",
        ]
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
    entity_id = f"{DOMAIN}.test_5678"
    hass.states.async_set(
        entity_id,
        HVACMode.COOL,
        {
            const.ATTR_HVAC_ACTION: HVACAction.IDLE,
            const.ATTR_CURRENT_HUMIDITY: 23,
            const.ATTR_CURRENT_TEMPERATURE: 18,
        },
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
        for trigger in [
            "hvac_mode_changed",
            "current_temperature_changed",
            "current_humidity_changed",
        ]
    ]
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_entry.id
    )
    assert_lists_same(triggers, expected_triggers)


async def test_if_fires_on_state_change(hass: HomeAssistant, calls) -> None:
    """Test for turn_on and turn_off triggers firing."""
    hass.states.async_set(
        "climate.entity",
        HVACMode.COOL,
        {
            const.ATTR_HVAC_ACTION: HVACAction.IDLE,
            const.ATTR_CURRENT_HUMIDITY: 23,
            const.ATTR_CURRENT_TEMPERATURE: 18,
        },
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
                        "entity_id": "climate.entity",
                        "type": "hvac_mode_changed",
                        "to": HVACMode.AUTO,
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {"some": "hvac_mode_changed"},
                    },
                },
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": "",
                        "entity_id": "climate.entity",
                        "type": "current_temperature_changed",
                        "above": 20,
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {"some": "current_temperature_changed"},
                    },
                },
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": "",
                        "entity_id": "climate.entity",
                        "type": "current_humidity_changed",
                        "below": 10,
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {"some": "current_humidity_changed"},
                    },
                },
            ]
        },
    )

    # Fake that the HVAC mode is changing
    hass.states.async_set(
        "climate.entity",
        HVACMode.AUTO,
        {
            const.ATTR_HVAC_ACTION: HVACAction.COOLING,
            const.ATTR_CURRENT_HUMIDITY: 23,
            const.ATTR_CURRENT_TEMPERATURE: 18,
        },
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["some"] == "hvac_mode_changed"

    # Fake that the temperature is changing
    hass.states.async_set(
        "climate.entity",
        HVACMode.AUTO,
        {
            const.ATTR_HVAC_ACTION: HVACAction.COOLING,
            const.ATTR_CURRENT_HUMIDITY: 23,
            const.ATTR_CURRENT_TEMPERATURE: 23,
        },
    )
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert calls[1].data["some"] == "current_temperature_changed"

    # Fake that the humidity is changing
    hass.states.async_set(
        "climate.entity",
        HVACMode.AUTO,
        {
            const.ATTR_HVAC_ACTION: HVACAction.COOLING,
            const.ATTR_CURRENT_HUMIDITY: 7,
            const.ATTR_CURRENT_TEMPERATURE: 23,
        },
    )
    await hass.async_block_till_done()
    assert len(calls) == 3
    assert calls[2].data["some"] == "current_humidity_changed"


async def test_get_trigger_capabilities_hvac_mode(hass: HomeAssistant) -> None:
    """Test we get the expected capabilities from a climate trigger."""
    capabilities = await device_trigger.async_get_trigger_capabilities(
        hass,
        {
            "platform": "device",
            "domain": "climate",
            "type": "hvac_mode_changed",
            "entity_id": "climate.upstairs",
            "to": "heat",
        },
    )
    assert capabilities and "extra_fields" in capabilities

    assert voluptuous_serialize.convert(
        capabilities["extra_fields"], custom_serializer=cv.custom_serializer
    ) == [
        {
            "name": "to",
            "options": [
                ("off", "off"),
                ("heat", "heat"),
                ("cool", "cool"),
                ("heat_cool", "heat_cool"),
                ("auto", "auto"),
                ("dry", "dry"),
                ("fan_only", "fan_only"),
            ],
            "required": True,
            "type": "select",
        },
        {"name": "for", "optional": True, "type": "positive_time_period_dict"},
    ]


@pytest.mark.parametrize(
    "type", ["current_temperature_changed", "current_humidity_changed"]
)
async def test_get_trigger_capabilities_temp_humid(hass: HomeAssistant, type) -> None:
    """Test we get the expected capabilities from a climate trigger."""
    capabilities = await device_trigger.async_get_trigger_capabilities(
        hass,
        {
            "platform": "device",
            "domain": "climate",
            "type": "current_temperature_changed",
            "entity_id": "climate.upstairs",
            "above": "23",
        },
    )

    assert capabilities and "extra_fields" in capabilities

    assert voluptuous_serialize.convert(
        capabilities["extra_fields"], custom_serializer=cv.custom_serializer
    ) == [
        {
            "description": {"suffix": UnitOfTemperature.CELSIUS},
            "name": "above",
            "optional": True,
            "type": "float",
        },
        {
            "description": {"suffix": UnitOfTemperature.CELSIUS},
            "name": "below",
            "optional": True,
            "type": "float",
        },
        {"name": "for", "optional": True, "type": "positive_time_period_dict"},
    ]
