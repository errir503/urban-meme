"""Test the Logitech Harmony Hub activity switches."""
from datetime import timedelta

from homeassistant.components.harmony.const import DOMAIN
from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import utcnow

from .const import ENTITY_PLAY_MUSIC, ENTITY_REMOTE, ENTITY_WATCH_TV, HUB_NAME

from tests.common import MockConfigEntry, async_fire_time_changed


async def test_connection_state_changes(
    harmony_client,
    mock_hc,
    hass: HomeAssistant,
    mock_write_config,
    entity_registry: er.EntityRegistry,
) -> None:
    """Ensure connection changes are reflected in the switch states."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "192.0.2.0", CONF_NAME: HUB_NAME}
    )

    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # check if switch entities are disabled by default
    assert not hass.states.get(ENTITY_WATCH_TV)
    assert not hass.states.get(ENTITY_PLAY_MUSIC)

    # enable switch entities
    entity_registry.async_update_entity(ENTITY_WATCH_TV, disabled_by=None)
    entity_registry.async_update_entity(ENTITY_PLAY_MUSIC, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # mocks start with current activity == Watch TV
    assert hass.states.is_state(ENTITY_WATCH_TV, STATE_ON)
    assert hass.states.is_state(ENTITY_PLAY_MUSIC, STATE_OFF)

    harmony_client.mock_disconnection()
    await hass.async_block_till_done()

    # Entities do not immediately show as unavailable
    assert hass.states.is_state(ENTITY_WATCH_TV, STATE_ON)
    assert hass.states.is_state(ENTITY_PLAY_MUSIC, STATE_OFF)

    future_time = utcnow() + timedelta(seconds=10)
    async_fire_time_changed(hass, future_time)
    await hass.async_block_till_done()
    assert hass.states.is_state(ENTITY_WATCH_TV, STATE_UNAVAILABLE)
    assert hass.states.is_state(ENTITY_PLAY_MUSIC, STATE_UNAVAILABLE)

    harmony_client.mock_reconnection()
    await hass.async_block_till_done()

    assert hass.states.is_state(ENTITY_WATCH_TV, STATE_ON)
    assert hass.states.is_state(ENTITY_PLAY_MUSIC, STATE_OFF)

    harmony_client.mock_disconnection()
    harmony_client.mock_reconnection()
    future_time = utcnow() + timedelta(seconds=10)
    async_fire_time_changed(hass, future_time)

    await hass.async_block_till_done()
    assert hass.states.is_state(ENTITY_WATCH_TV, STATE_ON)
    assert hass.states.is_state(ENTITY_PLAY_MUSIC, STATE_OFF)


async def test_switch_toggles(
    mock_hc, hass: HomeAssistant, mock_write_config, entity_registry: er.EntityRegistry
) -> None:
    """Ensure calls to the switch modify the harmony state."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "192.0.2.0", CONF_NAME: HUB_NAME}
    )

    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # enable switch entities
    entity_registry.async_update_entity(ENTITY_WATCH_TV, disabled_by=None)
    entity_registry.async_update_entity(ENTITY_PLAY_MUSIC, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # mocks start with current activity == Watch TV
    assert hass.states.is_state(ENTITY_REMOTE, STATE_ON)
    assert hass.states.is_state(ENTITY_WATCH_TV, STATE_ON)
    assert hass.states.is_state(ENTITY_PLAY_MUSIC, STATE_OFF)

    # turn off watch tv switch
    await _toggle_switch_and_wait(hass, SERVICE_TURN_OFF, ENTITY_WATCH_TV)
    assert hass.states.is_state(ENTITY_REMOTE, STATE_OFF)
    assert hass.states.is_state(ENTITY_WATCH_TV, STATE_OFF)
    assert hass.states.is_state(ENTITY_PLAY_MUSIC, STATE_OFF)

    # turn on play music switch
    await _toggle_switch_and_wait(hass, SERVICE_TURN_ON, ENTITY_PLAY_MUSIC)
    assert hass.states.is_state(ENTITY_REMOTE, STATE_ON)
    assert hass.states.is_state(ENTITY_WATCH_TV, STATE_OFF)
    assert hass.states.is_state(ENTITY_PLAY_MUSIC, STATE_ON)

    # turn on watch tv switch
    await _toggle_switch_and_wait(hass, SERVICE_TURN_ON, ENTITY_WATCH_TV)
    assert hass.states.is_state(ENTITY_REMOTE, STATE_ON)
    assert hass.states.is_state(ENTITY_WATCH_TV, STATE_ON)
    assert hass.states.is_state(ENTITY_PLAY_MUSIC, STATE_OFF)


async def _toggle_switch_and_wait(hass, service_name, entity):
    await hass.services.async_call(
        SWITCH_DOMAIN,
        service_name,
        {ATTR_ENTITY_ID: entity},
        blocking=True,
    )
    await hass.async_block_till_done()
