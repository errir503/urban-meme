"""Numeric derivative of data coming from a source sensor over time."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, DecimalException
import logging

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_SOURCE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    TIME_DAYS,
    TIME_HOURS,
    TIME_MINUTES,
    TIME_SECONDS,
)
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

# mypy: allow-untyped-defs, no-check-untyped-defs

_LOGGER = logging.getLogger(__name__)

ATTR_SOURCE_ID = "source"

CONF_ROUND_DIGITS = "round"
CONF_UNIT_PREFIX = "unit_prefix"
CONF_UNIT_TIME = "unit_time"
CONF_UNIT = "unit"
CONF_TIME_WINDOW = "time_window"

# SI Metric prefixes
UNIT_PREFIXES = {
    None: 1,
    "n": 1e-9,
    "µ": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
}

# SI Time prefixes
UNIT_TIME = {
    TIME_SECONDS: 1,
    TIME_MINUTES: 60,
    TIME_HOURS: 60 * 60,
    TIME_DAYS: 24 * 60 * 60,
}

ICON = "mdi:chart-line"

DEFAULT_ROUND = 3
DEFAULT_TIME_WINDOW = 0

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Required(CONF_SOURCE): cv.entity_id,
        vol.Optional(CONF_ROUND_DIGITS, default=DEFAULT_ROUND): vol.Coerce(int),
        vol.Optional(CONF_UNIT_PREFIX, default=None): vol.In(UNIT_PREFIXES),
        vol.Optional(CONF_UNIT_TIME, default=TIME_HOURS): vol.In(UNIT_TIME),
        vol.Optional(CONF_UNIT): cv.string,
        vol.Optional(CONF_TIME_WINDOW, default=DEFAULT_TIME_WINDOW): cv.time_period,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the derivative sensor."""
    derivative = DerivativeSensor(
        source_entity=config[CONF_SOURCE],
        name=config.get(CONF_NAME),
        round_digits=config[CONF_ROUND_DIGITS],
        unit_prefix=config[CONF_UNIT_PREFIX],
        unit_time=config[CONF_UNIT_TIME],
        unit_of_measurement=config.get(CONF_UNIT),
        time_window=config[CONF_TIME_WINDOW],
    )

    async_add_entities([derivative])


class DerivativeSensor(RestoreEntity, SensorEntity):
    """Representation of an derivative sensor."""

    def __init__(
        self,
        source_entity,
        name,
        round_digits,
        unit_prefix,
        unit_time,
        unit_of_measurement,
        time_window,
    ):
        """Initialize the derivative sensor."""
        self._sensor_source_id = source_entity
        self._round_digits = round_digits
        self._state = 0
        self._state_list = (
            []
        )  # List of tuples with (timestamp_start, timestamp_end, derivative)

        self._name = name if name is not None else f"{source_entity} derivative"

        if unit_of_measurement is None:
            final_unit_prefix = "" if unit_prefix is None else unit_prefix
            self._unit_template = f"{final_unit_prefix}{{}}/{unit_time}"
            # we postpone the definition of unit_of_measurement to later
            self._unit_of_measurement = None
        else:
            self._unit_of_measurement = unit_of_measurement

        self._unit_prefix = UNIT_PREFIXES[unit_prefix]
        self._unit_time = UNIT_TIME[unit_time]
        self._time_window = time_window.total_seconds()

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            try:
                self._state = Decimal(state.state)
            except SyntaxError as err:
                _LOGGER.warning("Could not restore last state: %s", err)

        @callback
        def calc_derivative(event):
            """Handle the sensor state changes."""
            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")
            if (
                old_state is None
                or old_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
                or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
            ):
                return

            if self._unit_of_measurement is None:
                unit = new_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                self._unit_of_measurement = self._unit_template.format(
                    "" if unit is None else unit
                )

            # filter out all derivatives older than `time_window` from our window list
            self._state_list = [
                (time_start, time_end, state)
                for time_start, time_end, state in self._state_list
                if (new_state.last_updated - time_end).total_seconds()
                < self._time_window
            ]

            try:
                elapsed_time = (
                    new_state.last_updated - old_state.last_updated
                ).total_seconds()
                delta_value = Decimal(new_state.state) - Decimal(old_state.state)
                new_derivative = (
                    delta_value
                    / Decimal(elapsed_time)
                    / Decimal(self._unit_prefix)
                    * Decimal(self._unit_time)
                )

            except ValueError as err:
                _LOGGER.warning("While calculating derivative: %s", err)
            except DecimalException as err:
                _LOGGER.warning(
                    "Invalid state (%s > %s): %s", old_state.state, new_state.state, err
                )
            except AssertionError as err:
                _LOGGER.error("Could not calculate derivative: %s", err)

            # add latest derivative to the window list
            self._state_list.append(
                (old_state.last_updated, new_state.last_updated, new_derivative)
            )

            def calculate_weight(start, end, now):
                window_start = now - timedelta(seconds=self._time_window)
                if start < window_start:
                    weight = (end - window_start).total_seconds() / self._time_window
                else:
                    weight = (end - start).total_seconds() / self._time_window
                return weight

            # If outside of time window just report derivative (is the same as modeling it in the window),
            # otherwise take the weighted average with the previous derivatives
            if elapsed_time > self._time_window:
                derivative = new_derivative
            else:
                derivative = 0
                for (start, end, value) in self._state_list:
                    weight = calculate_weight(start, end, new_state.last_updated)
                    derivative = derivative + (value * Decimal(weight))

            self._state = derivative
            self.async_write_ha_state()

        async_track_state_change_event(
            self.hass, [self._sensor_source_id], calc_derivative
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return round(self._state, self._round_digits)

    @property
    def native_unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._unit_of_measurement

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        return {ATTR_SOURCE_ID: self._sensor_source_id}

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return ICON
