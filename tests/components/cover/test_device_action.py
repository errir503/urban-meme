"""The tests for Cover device actions."""
import pytest

import homeassistant.components.automation as automation
from homeassistant.components.cover import DOMAIN, CoverEntityFeature
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.const import CONF_PLATFORM, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryHider
from homeassistant.setup import async_setup_component

from tests.common import (
    MockConfigEntry,
    assert_lists_same,
    async_get_device_automation_capabilities,
    async_get_device_automations,
    async_mock_service,
)
from tests.components.blueprint.conftest import stub_blueprint_populate  # noqa: F401


@pytest.mark.parametrize(
    ("set_state", "features_reg", "features_state", "expected_action_types"),
    [
        (False, 0, 0, []),
        (False, CoverEntityFeature.CLOSE_TILT, 0, ["close_tilt"]),
        (False, CoverEntityFeature.CLOSE, 0, ["close"]),
        (False, CoverEntityFeature.OPEN_TILT, 0, ["open_tilt"]),
        (False, CoverEntityFeature.OPEN, 0, ["open"]),
        (False, CoverEntityFeature.SET_POSITION, 0, ["set_position"]),
        (False, CoverEntityFeature.SET_TILT_POSITION, 0, ["set_tilt_position"]),
        (False, CoverEntityFeature.STOP, 0, ["stop"]),
        (True, 0, 0, []),
        (True, 0, CoverEntityFeature.CLOSE_TILT, ["close_tilt"]),
        (True, 0, CoverEntityFeature.CLOSE, ["close"]),
        (True, 0, CoverEntityFeature.OPEN_TILT, ["open_tilt"]),
        (True, 0, CoverEntityFeature.OPEN, ["open"]),
        (True, 0, CoverEntityFeature.SET_POSITION, ["set_position"]),
        (True, 0, CoverEntityFeature.SET_TILT_POSITION, ["set_tilt_position"]),
        (True, 0, CoverEntityFeature.STOP, ["stop"]),
    ],
)
async def test_get_actions(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    set_state,
    features_reg,
    features_state,
    expected_action_types,
) -> None:
    """Test we get the expected actions from a cover."""
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
        supported_features=features_reg,
    )
    if set_state:
        hass.states.async_set(
            f"{DOMAIN}.test_5678", "attributes", {"supported_features": features_state}
        )
    await hass.async_block_till_done()

    expected_actions = []
    expected_actions += [
        {
            "domain": DOMAIN,
            "type": action,
            "device_id": device_entry.id,
            "entity_id": f"{DOMAIN}.test_5678",
            "metadata": {"secondary": False},
        }
        for action in expected_action_types
    ]
    actions = await async_get_device_automations(
        hass, DeviceAutomationType.ACTION, device_entry.id
    )
    assert_lists_same(actions, expected_actions)


@pytest.mark.parametrize(
    ("hidden_by", "entity_category"),
    (
        (RegistryEntryHider.INTEGRATION, None),
        (RegistryEntryHider.USER, None),
        (None, EntityCategory.CONFIG),
        (None, EntityCategory.DIAGNOSTIC),
    ),
)
async def test_get_actions_hidden_auxiliary(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    hidden_by,
    entity_category,
) -> None:
    """Test we get the expected actions from a hidden or auxiliary entity."""
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
        supported_features=CoverEntityFeature.CLOSE,
    )
    expected_actions = []
    expected_actions += [
        {
            "domain": DOMAIN,
            "type": action,
            "device_id": device_entry.id,
            "entity_id": f"{DOMAIN}.test_5678",
            "metadata": {"secondary": True},
        }
        for action in ["close"]
    ]
    actions = await async_get_device_automations(
        hass, DeviceAutomationType.ACTION, device_entry.id
    )
    assert_lists_same(actions, expected_actions)


async def test_get_action_capabilities(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    enable_custom_integrations: None,
) -> None:
    """Test we get the expected capabilities from a cover action."""
    platform = getattr(hass.components, f"test.{DOMAIN}")
    platform.init(empty=True)
    platform.ENTITIES.append(
        platform.MockCover(
            name="Set position cover",
            is_on=True,
            unique_id="unique_set_pos_cover",
            current_cover_position=50,
            supported_features=CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.OPEN_TILT
            | CoverEntityFeature.CLOSE_TILT
            | CoverEntityFeature.STOP_TILT,
        ),
    )
    ent = platform.ENTITIES[0]
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {CONF_PLATFORM: "test"}})
    await hass.async_block_till_done()

    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
    )
    entity_registry.async_get_or_create(
        DOMAIN, "test", ent.unique_id, device_id=device_entry.id
    )

    actions = await async_get_device_automations(
        hass, DeviceAutomationType.ACTION, device_entry.id
    )
    assert len(actions) == 5  # open, close, open_tilt, close_tilt
    action_types = {action["type"] for action in actions}
    assert action_types == {"open", "close", "stop", "open_tilt", "close_tilt"}
    for action in actions:
        capabilities = await async_get_device_automation_capabilities(
            hass, DeviceAutomationType.ACTION, action
        )
        assert capabilities == {"extra_fields": []}


async def test_get_action_capabilities_set_pos(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    enable_custom_integrations: None,
) -> None:
    """Test we get the expected capabilities from a cover action."""
    platform = getattr(hass.components, f"test.{DOMAIN}")
    platform.init()
    ent = platform.ENTITIES[1]
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {CONF_PLATFORM: "test"}})
    await hass.async_block_till_done()

    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
    )
    entity_registry.async_get_or_create(
        DOMAIN, "test", ent.unique_id, device_id=device_entry.id
    )

    expected_capabilities = {
        "extra_fields": [
            {
                "name": "position",
                "optional": True,
                "type": "integer",
                "default": 0,
                "valueMax": 100,
                "valueMin": 0,
            }
        ]
    }
    actions = await async_get_device_automations(
        hass, DeviceAutomationType.ACTION, device_entry.id
    )
    assert len(actions) == 1  # set_position
    action_types = {action["type"] for action in actions}
    assert action_types == {"set_position"}
    for action in actions:
        capabilities = await async_get_device_automation_capabilities(
            hass, DeviceAutomationType.ACTION, action
        )
        if action["type"] == "set_position":
            assert capabilities == expected_capabilities
        else:
            assert capabilities == {"extra_fields": []}


async def test_get_action_capabilities_set_tilt_pos(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    enable_custom_integrations: None,
) -> None:
    """Test we get the expected capabilities from a cover action."""
    platform = getattr(hass.components, f"test.{DOMAIN}")
    platform.init()
    ent = platform.ENTITIES[3]
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {CONF_PLATFORM: "test"}})
    await hass.async_block_till_done()

    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
    )
    entity_registry.async_get_or_create(
        DOMAIN, "test", ent.unique_id, device_id=device_entry.id
    )

    expected_capabilities = {
        "extra_fields": [
            {
                "name": "position",
                "optional": True,
                "type": "integer",
                "default": 0,
                "valueMax": 100,
                "valueMin": 0,
            }
        ]
    }
    actions = await async_get_device_automations(
        hass, DeviceAutomationType.ACTION, device_entry.id
    )
    assert len(actions) == 3
    action_types = {action["type"] for action in actions}
    assert action_types == {"open", "close", "set_tilt_position"}
    for action in actions:
        capabilities = await async_get_device_automation_capabilities(
            hass, DeviceAutomationType.ACTION, action
        )
        if action["type"] == "set_tilt_position":
            assert capabilities == expected_capabilities
        else:
            assert capabilities == {"extra_fields": []}


async def test_action(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    """Test for cover actions."""
    platform = getattr(hass.components, f"test.{DOMAIN}")
    platform.init()
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {CONF_PLATFORM: "test"}})

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {"platform": "event", "event_type": "test_event_open"},
                    "action": {
                        "domain": DOMAIN,
                        "device_id": "abcdefgh",
                        "entity_id": "cover.entity",
                        "type": "open",
                    },
                },
                {
                    "trigger": {"platform": "event", "event_type": "test_event_close"},
                    "action": {
                        "domain": DOMAIN,
                        "device_id": "abcdefgh",
                        "entity_id": "cover.entity",
                        "type": "close",
                    },
                },
                {
                    "trigger": {"platform": "event", "event_type": "test_event_stop"},
                    "action": {
                        "domain": DOMAIN,
                        "device_id": "abcdefgh",
                        "entity_id": "cover.entity",
                        "type": "stop",
                    },
                },
            ]
        },
    )
    await hass.async_block_till_done()

    open_calls = async_mock_service(hass, "cover", "open_cover")
    close_calls = async_mock_service(hass, "cover", "close_cover")
    stop_calls = async_mock_service(hass, "cover", "stop_cover")

    hass.bus.async_fire("test_event_open")
    await hass.async_block_till_done()
    assert len(open_calls) == 1
    assert len(close_calls) == 0
    assert len(stop_calls) == 0

    hass.bus.async_fire("test_event_close")
    await hass.async_block_till_done()
    assert len(open_calls) == 1
    assert len(close_calls) == 1
    assert len(stop_calls) == 0

    hass.bus.async_fire("test_event_stop")
    await hass.async_block_till_done()
    assert len(open_calls) == 1
    assert len(close_calls) == 1
    assert len(stop_calls) == 1


async def test_action_tilt(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Test for cover tilt actions."""
    platform = getattr(hass.components, f"test.{DOMAIN}")
    platform.init()
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {CONF_PLATFORM: "test"}})

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {"platform": "event", "event_type": "test_event_open"},
                    "action": {
                        "domain": DOMAIN,
                        "device_id": "abcdefgh",
                        "entity_id": "cover.entity",
                        "type": "open_tilt",
                    },
                },
                {
                    "trigger": {"platform": "event", "event_type": "test_event_close"},
                    "action": {
                        "domain": DOMAIN,
                        "device_id": "abcdefgh",
                        "entity_id": "cover.entity",
                        "type": "close_tilt",
                    },
                },
            ]
        },
    )
    await hass.async_block_till_done()

    open_calls = async_mock_service(hass, "cover", "open_cover_tilt")
    close_calls = async_mock_service(hass, "cover", "close_cover_tilt")

    hass.bus.async_fire("test_event_open")
    await hass.async_block_till_done()
    assert len(open_calls) == 1
    assert len(close_calls) == 0

    hass.bus.async_fire("test_event_close")
    await hass.async_block_till_done()
    assert len(open_calls) == 1
    assert len(close_calls) == 1

    hass.bus.async_fire("test_event_stop")
    await hass.async_block_till_done()
    assert len(open_calls) == 1
    assert len(close_calls) == 1


async def test_action_set_position(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Test for cover set position actions."""
    platform = getattr(hass.components, f"test.{DOMAIN}")
    platform.init()
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {CONF_PLATFORM: "test"}})

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "event",
                        "event_type": "test_event_set_pos",
                    },
                    "action": {
                        "domain": DOMAIN,
                        "device_id": "abcdefgh",
                        "entity_id": "cover.entity",
                        "type": "set_position",
                        "position": 25,
                    },
                },
                {
                    "trigger": {
                        "platform": "event",
                        "event_type": "test_event_set_tilt_pos",
                    },
                    "action": {
                        "domain": DOMAIN,
                        "device_id": "abcdefgh",
                        "entity_id": "cover.entity",
                        "type": "set_tilt_position",
                        "position": 75,
                    },
                },
            ]
        },
    )
    await hass.async_block_till_done()

    cover_pos_calls = async_mock_service(hass, "cover", "set_cover_position")
    tilt_pos_calls = async_mock_service(hass, "cover", "set_cover_tilt_position")

    hass.bus.async_fire("test_event_set_pos")
    await hass.async_block_till_done()
    assert len(cover_pos_calls) == 1
    assert cover_pos_calls[0].data["position"] == 25
    assert len(tilt_pos_calls) == 0

    hass.bus.async_fire("test_event_set_tilt_pos")
    await hass.async_block_till_done()
    assert len(cover_pos_calls) == 1
    assert len(tilt_pos_calls) == 1
    assert tilt_pos_calls[0].data["tilt_position"] == 75
