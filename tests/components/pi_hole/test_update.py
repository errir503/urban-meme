"""Test pi_hole component."""

from homeassistant.components import pi_hole
from homeassistant.const import STATE_ON, STATE_UNKNOWN
from homeassistant.setup import async_setup_component

from . import _create_mocked_hole, _patch_config_flow_hole, _patch_init_hole


async def test_update(hass):
    """Tests update entity."""
    mocked_hole = _create_mocked_hole()
    with _patch_config_flow_hole(mocked_hole), _patch_init_hole(mocked_hole):
        assert await async_setup_component(
            hass, pi_hole.DOMAIN, {pi_hole.DOMAIN: [{"host": "pi.hole"}]}
        )

    await hass.async_block_till_done()

    state = hass.states.get("update.pi_hole_core_update_available")
    assert state.name == "Pi-Hole Core Update Available"
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == "v5.5"
    assert state.attributes["latest_version"] == "v5.6"
    assert (
        state.attributes["release_url"]
        == "https://github.com/pi-hole/pi-hole/releases/tag/v5.6"
    )

    state = hass.states.get("update.pi_hole_ftl_update_available")
    assert state.name == "Pi-Hole FTL Update Available"
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == "v5.10"
    assert state.attributes["latest_version"] == "v5.11"
    assert (
        state.attributes["release_url"]
        == "https://github.com/pi-hole/FTL/releases/tag/v5.11"
    )

    state = hass.states.get("update.pi_hole_web_update_available")
    assert state.name == "Pi-Hole Web Update Available"
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == "v5.7"
    assert state.attributes["latest_version"] == "v5.8"
    assert (
        state.attributes["release_url"]
        == "https://github.com/pi-hole/AdminLTE/releases/tag/v5.8"
    )


async def test_update_no_versions(hass):
    """Tests update entity when no version data available."""
    mocked_hole = _create_mocked_hole(has_versions=False)
    with _patch_config_flow_hole(mocked_hole), _patch_init_hole(mocked_hole):
        assert await async_setup_component(
            hass, pi_hole.DOMAIN, {pi_hole.DOMAIN: [{"host": "pi.hole"}]}
        )

    await hass.async_block_till_done()

    state = hass.states.get("update.pi_hole_core_update_available")
    assert state.name == "Pi-Hole Core Update Available"
    assert state.state == STATE_UNKNOWN
    assert state.attributes["installed_version"] is None
    assert state.attributes["latest_version"] is None
    assert state.attributes["release_url"] is None

    state = hass.states.get("update.pi_hole_ftl_update_available")
    assert state.name == "Pi-Hole FTL Update Available"
    assert state.state == STATE_UNKNOWN
    assert state.attributes["installed_version"] is None
    assert state.attributes["latest_version"] is None
    assert state.attributes["release_url"] is None

    state = hass.states.get("update.pi_hole_web_update_available")
    assert state.name == "Pi-Hole Web Update Available"
    assert state.state == STATE_UNKNOWN
    assert state.attributes["installed_version"] is None
    assert state.attributes["latest_version"] is None
    assert state.attributes["release_url"] is None
