"""The tests for the Group Switch platform."""
from unittest.mock import patch

import async_timeout

from homeassistant import config as hass_config
from homeassistant.components.group import DOMAIN, SERVICE_RELOAD
from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SERVICE_TOGGLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import get_fixture_path


async def test_default_state(hass):
    """Test switch group default state."""
    hass.states.async_set("switch.tv", "on")
    await async_setup_component(
        hass,
        SWITCH_DOMAIN,
        {
            SWITCH_DOMAIN: {
                "platform": DOMAIN,
                "entities": ["switch.tv", "switch.soundbar"],
                "name": "Multimedia Group",
                "unique_id": "unique_identifier",
                "all": "false",
            }
        },
    )
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()

    state = hass.states.get("switch.multimedia_group")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes.get(ATTR_ENTITY_ID) == ["switch.tv", "switch.soundbar"]

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("switch.multimedia_group")
    assert entry
    assert entry.unique_id == "unique_identifier"


async def test_state_reporting(hass):
    """Test the state reporting."""
    await async_setup_component(
        hass,
        SWITCH_DOMAIN,
        {
            SWITCH_DOMAIN: {
                "platform": DOMAIN,
                "entities": ["switch.test1", "switch.test2"],
                "all": "false",
            }
        },
    )
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()

    hass.states.async_set("switch.test1", STATE_ON)
    hass.states.async_set("switch.test2", STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert hass.states.get("switch.switch_group").state == STATE_ON

    hass.states.async_set("switch.test1", STATE_ON)
    hass.states.async_set("switch.test2", STATE_OFF)
    await hass.async_block_till_done()
    assert hass.states.get("switch.switch_group").state == STATE_ON

    hass.states.async_set("switch.test1", STATE_OFF)
    hass.states.async_set("switch.test2", STATE_OFF)
    await hass.async_block_till_done()
    assert hass.states.get("switch.switch_group").state == STATE_OFF

    hass.states.async_set("switch.test1", STATE_UNAVAILABLE)
    hass.states.async_set("switch.test2", STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert hass.states.get("switch.switch_group").state == STATE_UNAVAILABLE


async def test_state_reporting_all(hass):
    """Test the state reporting."""
    await async_setup_component(
        hass,
        SWITCH_DOMAIN,
        {
            SWITCH_DOMAIN: {
                "platform": DOMAIN,
                "entities": ["switch.test1", "switch.test2"],
                "all": "true",
            }
        },
    )
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()

    hass.states.async_set("switch.test1", STATE_ON)
    hass.states.async_set("switch.test2", STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert hass.states.get("switch.switch_group").state == STATE_UNKNOWN

    hass.states.async_set("switch.test1", STATE_ON)
    hass.states.async_set("switch.test2", STATE_OFF)
    await hass.async_block_till_done()
    assert hass.states.get("switch.switch_group").state == STATE_OFF

    hass.states.async_set("switch.test1", STATE_OFF)
    hass.states.async_set("switch.test2", STATE_OFF)
    await hass.async_block_till_done()
    assert hass.states.get("switch.switch_group").state == STATE_OFF

    hass.states.async_set("switch.test1", STATE_ON)
    hass.states.async_set("switch.test2", STATE_ON)
    await hass.async_block_till_done()
    assert hass.states.get("switch.switch_group").state == STATE_ON

    hass.states.async_set("switch.test1", STATE_UNAVAILABLE)
    hass.states.async_set("switch.test2", STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert hass.states.get("switch.switch_group").state == STATE_UNAVAILABLE


async def test_service_calls(hass, enable_custom_integrations):
    """Test service calls."""
    await async_setup_component(
        hass,
        SWITCH_DOMAIN,
        {
            SWITCH_DOMAIN: [
                {"platform": "demo"},
                {
                    "platform": DOMAIN,
                    "entities": [
                        "switch.ac",
                        "switch.decorative_lights",
                    ],
                    "all": "false",
                },
            ]
        },
    )
    await hass.async_block_till_done()

    group_state = hass.states.get("switch.switch_group")
    assert group_state.state == STATE_ON

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TOGGLE,
        {ATTR_ENTITY_ID: "switch.switch_group"},
        blocking=True,
    )
    assert hass.states.get("switch.ac").state == STATE_OFF
    assert hass.states.get("switch.decorative_lights").state == STATE_OFF

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.switch_group"},
        blocking=True,
    )

    assert hass.states.get("switch.ac").state == STATE_ON
    assert hass.states.get("switch.decorative_lights").state == STATE_ON

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.switch_group"},
        blocking=True,
    )

    assert hass.states.get("switch.ac").state == STATE_OFF
    assert hass.states.get("switch.decorative_lights").state == STATE_OFF


async def test_reload(hass):
    """Test the ability to reload switches."""
    await async_setup_component(
        hass,
        SWITCH_DOMAIN,
        {
            SWITCH_DOMAIN: [
                {"platform": "demo"},
                {
                    "platform": DOMAIN,
                    "entities": [
                        "switch.ac",
                        "switch.decorative_lights",
                    ],
                    "all": "false",
                },
            ]
        },
    )
    await hass.async_block_till_done()

    await hass.async_block_till_done()
    await hass.async_start()

    await hass.async_block_till_done()
    assert hass.states.get("switch.switch_group").state == STATE_ON

    yaml_path = get_fixture_path("configuration.yaml", "group")
    with patch.object(hass_config, "YAML_CONFIG_FILE", yaml_path):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RELOAD,
            {},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert hass.states.get("switch.switch_group") is None
    assert hass.states.get("switch.master_switches_g") is not None
    assert hass.states.get("switch.outside_switches_g") is not None


async def test_reload_with_platform_not_setup(hass):
    """Test the ability to reload switches."""
    hass.states.async_set("switch.something", STATE_ON)
    await async_setup_component(
        hass,
        SWITCH_DOMAIN,
        {
            SWITCH_DOMAIN: [
                {"platform": "demo"},
            ]
        },
    )
    assert await async_setup_component(
        hass,
        "group",
        {
            "group": {
                "group_zero": {"entities": "switch.something", "icon": "mdi:work"},
            }
        },
    )
    await hass.async_block_till_done()

    yaml_path = get_fixture_path("configuration.yaml", "group")
    with patch.object(hass_config, "YAML_CONFIG_FILE", yaml_path):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RELOAD,
            {},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert hass.states.get("switch.switch_group") is None
    assert hass.states.get("switch.master_switches_g") is not None
    assert hass.states.get("switch.outside_switches_g") is not None


async def test_reload_with_base_integration_platform_not_setup(hass):
    """Test the ability to reload switches."""
    assert await async_setup_component(
        hass,
        "group",
        {
            "group": {
                "group_zero": {"entities": "switch.something", "icon": "mdi:work"},
            }
        },
    )
    await hass.async_block_till_done()
    hass.states.async_set("switch.master_switch", STATE_ON)
    hass.states.async_set("switch.master_switch_2", STATE_OFF)

    hass.states.async_set("switch.outside_switch", STATE_OFF)
    hass.states.async_set("switch.outside_switch_2", STATE_OFF)

    yaml_path = get_fixture_path("configuration.yaml", "group")
    with patch.object(hass_config, "YAML_CONFIG_FILE", yaml_path):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RELOAD,
            {},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert hass.states.get("switch.switch_group") is None
    assert hass.states.get("switch.master_switches_g") is not None
    assert hass.states.get("switch.outside_switches_g") is not None
    assert hass.states.get("switch.master_switches_g").state == STATE_ON
    assert hass.states.get("switch.outside_switches_g").state == STATE_OFF


async def test_nested_group(hass):
    """Test nested switch group."""
    await async_setup_component(
        hass,
        SWITCH_DOMAIN,
        {
            SWITCH_DOMAIN: [
                {"platform": "demo"},
                {
                    "platform": DOMAIN,
                    "entities": ["switch.some_group"],
                    "name": "Nested Group",
                    "all": "false",
                },
                {
                    "platform": DOMAIN,
                    "entities": ["switch.ac", "switch.decorative_lights"],
                    "name": "Some Group",
                    "all": "false",
                },
            ]
        },
    )
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()

    state = hass.states.get("switch.some_group")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes.get(ATTR_ENTITY_ID) == [
        "switch.ac",
        "switch.decorative_lights",
    ]

    state = hass.states.get("switch.nested_group")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes.get(ATTR_ENTITY_ID) == ["switch.some_group"]

    # Test controlling the nested group
    async with async_timeout.timeout(0.5):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TOGGLE,
            {ATTR_ENTITY_ID: "switch.nested_group"},
            blocking=True,
        )
    assert hass.states.get("switch.ac").state == STATE_OFF
    assert hass.states.get("switch.decorative_lights").state == STATE_OFF
    assert hass.states.get("switch.some_group").state == STATE_OFF
    assert hass.states.get("switch.nested_group").state == STATE_OFF
