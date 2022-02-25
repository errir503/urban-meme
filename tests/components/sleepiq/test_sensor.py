"""The tests for SleepIQ sensor platform."""
from homeassistant.components.sensor import DOMAIN
from homeassistant.const import ATTR_FRIENDLY_NAME, ATTR_ICON
from homeassistant.helpers import entity_registry as er

from tests.components.sleepiq.conftest import (
    BED_ID,
    BED_NAME,
    BED_NAME_LOWER,
    SLEEPER_L_NAME,
    SLEEPER_L_NAME_LOWER,
    SLEEPER_R_NAME,
    SLEEPER_R_NAME_LOWER,
    setup_platform,
)


async def test_sensors(hass, mock_asyncsleepiq):
    """Test the SleepIQ binary sensors for a bed with two sides."""
    entry = await setup_platform(hass, DOMAIN)
    entity_registry = er.async_get(hass)

    state = hass.states.get(
        f"sensor.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_sleepnumber"
    )
    assert state.state == "40"
    assert state.attributes.get(ATTR_ICON) == "mdi:bed"
    assert (
        state.attributes.get(ATTR_FRIENDLY_NAME)
        == f"SleepNumber {BED_NAME} {SLEEPER_L_NAME} SleepNumber"
    )

    entry = entity_registry.async_get(
        f"sensor.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_sleepnumber"
    )
    assert entry
    assert entry.unique_id == f"{BED_ID}_{SLEEPER_L_NAME}_sleep_number"

    state = hass.states.get(
        f"sensor.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_sleepnumber"
    )
    assert state.state == "80"
    assert state.attributes.get(ATTR_ICON) == "mdi:bed"
    assert (
        state.attributes.get(ATTR_FRIENDLY_NAME)
        == f"SleepNumber {BED_NAME} {SLEEPER_R_NAME} SleepNumber"
    )

    entry = entity_registry.async_get(
        f"sensor.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_sleepnumber"
    )
    assert entry
    assert entry.unique_id == f"{BED_ID}_{SLEEPER_R_NAME}_sleep_number"
