"""The tests for the Switch component."""
import pytest

from homeassistant import core
from homeassistant.components import switch
from homeassistant.const import CONF_PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from . import common

from tests.common import MockUser


@pytest.fixture(autouse=True)
def entities(hass):
    """Initialize the test switch."""
    platform = getattr(hass.components, "test.switch")
    platform.init()
    return platform.ENTITIES


async def test_methods(
    hass: HomeAssistant, entities, enable_custom_integrations: None
) -> None:
    """Test is_on, turn_on, turn_off methods."""
    switch_1, switch_2, switch_3 = entities
    assert await async_setup_component(
        hass, switch.DOMAIN, {switch.DOMAIN: {CONF_PLATFORM: "test"}}
    )
    await hass.async_block_till_done()
    assert switch.is_on(hass, switch_1.entity_id)
    assert not switch.is_on(hass, switch_2.entity_id)
    assert not switch.is_on(hass, switch_3.entity_id)

    await common.async_turn_off(hass, switch_1.entity_id)
    await common.async_turn_on(hass, switch_2.entity_id)

    assert not switch.is_on(hass, switch_1.entity_id)
    assert switch.is_on(hass, switch_2.entity_id)

    # Turn all off
    await common.async_turn_off(hass)

    assert not switch.is_on(hass, switch_1.entity_id)
    assert not switch.is_on(hass, switch_2.entity_id)
    assert not switch.is_on(hass, switch_3.entity_id)

    # Turn all on
    await common.async_turn_on(hass)

    assert switch.is_on(hass, switch_1.entity_id)
    assert switch.is_on(hass, switch_2.entity_id)
    assert switch.is_on(hass, switch_3.entity_id)


async def test_switch_context(
    hass: HomeAssistant,
    entities,
    hass_admin_user: MockUser,
    enable_custom_integrations: None,
) -> None:
    """Test that switch context works."""
    assert await async_setup_component(hass, "switch", {"switch": {"platform": "test"}})

    await hass.async_block_till_done()

    state = hass.states.get("switch.ac")
    assert state is not None

    await hass.services.async_call(
        "switch",
        "toggle",
        {"entity_id": state.entity_id},
        True,
        core.Context(user_id=hass_admin_user.id),
    )

    state2 = hass.states.get("switch.ac")
    assert state2 is not None
    assert state.state != state2.state
    assert state2.context.user_id == hass_admin_user.id
