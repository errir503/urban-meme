"""The tests for SleepIQ binary sensor platform."""
from homeassistant.components.binary_sensor import DOMAIN, BinarySensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_ICON,
    STATE_OFF,
    STATE_ON,
)
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


async def test_binary_sensors(hass, mock_asyncsleepiq):
    """Test the SleepIQ binary sensors."""
    await setup_platform(hass, DOMAIN)
    entity_registry = er.async_get(hass)

    state = hass.states.get(
        f"binary_sensor.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_is_in_bed"
    )
    assert state.state == STATE_ON
    assert state.attributes.get(ATTR_ICON) == "mdi:bed"
    assert state.attributes.get(ATTR_DEVICE_CLASS) == BinarySensorDeviceClass.OCCUPANCY
    assert (
        state.attributes.get(ATTR_FRIENDLY_NAME)
        == f"SleepNumber {BED_NAME} {SLEEPER_L_NAME} Is In Bed"
    )

    entity = entity_registry.async_get(
        f"binary_sensor.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_is_in_bed"
    )
    assert entity
    assert entity.unique_id == f"{BED_ID}_{SLEEPER_L_NAME}_is_in_bed"

    state = hass.states.get(
        f"binary_sensor.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_is_in_bed"
    )
    assert state.state == STATE_OFF
    assert state.attributes.get(ATTR_ICON) == "mdi:bed-empty"
    assert state.attributes.get(ATTR_DEVICE_CLASS) == BinarySensorDeviceClass.OCCUPANCY
    assert (
        state.attributes.get(ATTR_FRIENDLY_NAME)
        == f"SleepNumber {BED_NAME} {SLEEPER_R_NAME} Is In Bed"
    )

    entity = entity_registry.async_get(
        f"binary_sensor.sleepnumber_{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_is_in_bed"
    )
    assert entity
    assert entity.unique_id == f"{BED_ID}_{SLEEPER_R_NAME}_is_in_bed"
