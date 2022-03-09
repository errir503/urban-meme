"""The tests for SleepIQ number platform."""
from homeassistant.components.number import DOMAIN
from homeassistant.components.number.const import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME, ATTR_ICON
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


async def test_firmness(hass, mock_asyncsleepiq):
    """Test the SleepIQ firmness number values for a bed with two sides."""
    entry = await setup_platform(hass, DOMAIN)
    entity_registry = er.async_get(hass)

    state = hass.states.get(
        f"number.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_firmness"
    )
    assert state.state == "40.0"
    assert state.attributes.get(ATTR_ICON) == "mdi:bed"
    assert (
        state.attributes.get(ATTR_FRIENDLY_NAME)
        == f"SleepNumber {BED_NAME} {SLEEPER_L_NAME} Firmness"
    )

    entry = entity_registry.async_get(
        f"number.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_firmness"
    )
    assert entry
    assert entry.unique_id == f"{BED_ID}_{SLEEPER_L_NAME}_firmness"

    state = hass.states.get(
        f"number.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_firmness"
    )
    assert state.state == "80.0"
    assert state.attributes.get(ATTR_ICON) == "mdi:bed"
    assert (
        state.attributes.get(ATTR_FRIENDLY_NAME)
        == f"SleepNumber {BED_NAME} {SLEEPER_R_NAME} Firmness"
    )

    entry = entity_registry.async_get(
        f"number.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_firmness"
    )
    assert entry
    assert entry.unique_id == f"{BED_ID}_{SLEEPER_R_NAME}_firmness"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: f"number.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_firmness",
            ATTR_VALUE: 42,
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    mock_asyncsleepiq.beds[BED_ID].sleepers[0].set_sleepnumber.assert_called_once()
    mock_asyncsleepiq.beds[BED_ID].sleepers[0].set_sleepnumber.assert_called_with(42)
