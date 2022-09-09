"""Support for showing random numbers."""
from __future__ import annotations

from random import randrange

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import (
    CONF_MAXIMUM,
    CONF_MINIMUM,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

ATTR_MAXIMUM = "maximum"
ATTR_MINIMUM = "minimum"

DEFAULT_NAME = "Random Sensor"
DEFAULT_MIN = 0
DEFAULT_MAX = 20

ICON = "mdi:hanger"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_MAXIMUM, default=DEFAULT_MAX): cv.positive_int,
        vol.Optional(CONF_MINIMUM, default=DEFAULT_MIN): cv.positive_int,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Random number sensor."""
    name = config.get(CONF_NAME)
    minimum = config.get(CONF_MINIMUM)
    maximum = config.get(CONF_MAXIMUM)
    unit = config.get(CONF_UNIT_OF_MEASUREMENT)

    async_add_entities([RandomSensor(name, minimum, maximum, unit)], True)


class RandomSensor(SensorEntity):
    """Representation of a Random number sensor."""

    def __init__(self, name, minimum, maximum, unit_of_measurement):
        """Initialize the Random sensor."""
        self._name = name
        self._minimum = minimum
        self._maximum = maximum
        self._unit_of_measurement = unit_of_measurement
        self._state = None

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def native_value(self):
        """Return the state of the device."""
        return self._state

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return ICON

    @property
    def native_unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        return self._unit_of_measurement

    @property
    def extra_state_attributes(self):
        """Return the attributes of the sensor."""
        return {ATTR_MAXIMUM: self._maximum, ATTR_MINIMUM: self._minimum}

    async def async_update(self) -> None:
        """Get a new number and updates the states."""

        self._state = randrange(self._minimum, self._maximum + 1)
