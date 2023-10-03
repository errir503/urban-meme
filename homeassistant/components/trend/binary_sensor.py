"""A sensor that monitors trends in other components."""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
import logging
import math
from typing import Any

import numpy as np
import voluptuous as vol

from homeassistant.components.binary_sensor import (
    DEVICE_CLASSES_SCHEMA,
    ENTITY_ID_FORMAT,
    PLATFORM_SCHEMA,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    CONF_ATTRIBUTE,
    CONF_DEVICE_CLASS,
    CONF_ENTITY_ID,
    CONF_FRIENDLY_NAME,
    CONF_SENSORS,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
)
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType, EventType
from homeassistant.util.dt import utcnow

from . import PLATFORMS
from .const import (
    ATTR_GRADIENT,
    ATTR_INVERT,
    ATTR_MIN_GRADIENT,
    ATTR_SAMPLE_COUNT,
    ATTR_SAMPLE_DURATION,
    CONF_INVERT,
    CONF_MAX_SAMPLES,
    CONF_MIN_GRADIENT,
    CONF_SAMPLE_DURATION,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_ATTRIBUTE): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): DEVICE_CLASSES_SCHEMA,
        vol.Optional(CONF_FRIENDLY_NAME): cv.string,
        vol.Optional(CONF_INVERT, default=False): cv.boolean,
        vol.Optional(CONF_MAX_SAMPLES, default=2): cv.positive_int,
        vol.Optional(CONF_MIN_GRADIENT, default=0.0): vol.Coerce(float),
        vol.Optional(CONF_SAMPLE_DURATION, default=0): cv.positive_int,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_SENSORS): cv.schema_with_slug_keys(SENSOR_SCHEMA)}
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the trend sensors."""
    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)

    sensors = []

    for device_id, device_config in config[CONF_SENSORS].items():
        entity_id = device_config[ATTR_ENTITY_ID]
        attribute = device_config.get(CONF_ATTRIBUTE)
        device_class = device_config.get(CONF_DEVICE_CLASS)
        friendly_name = device_config.get(ATTR_FRIENDLY_NAME, device_id)
        invert = device_config[CONF_INVERT]
        max_samples = device_config[CONF_MAX_SAMPLES]
        min_gradient = device_config[CONF_MIN_GRADIENT]
        sample_duration = device_config[CONF_SAMPLE_DURATION]

        sensors.append(
            SensorTrend(
                hass,
                device_id,
                friendly_name,
                entity_id,
                attribute,
                device_class,
                invert,
                max_samples,
                min_gradient,
                sample_duration,
            )
        )
    if not sensors:
        _LOGGER.error("No sensors added")
        return

    async_add_entities(sensors)


class SensorTrend(BinarySensorEntity, RestoreEntity):
    """Representation of a trend Sensor."""

    _attr_should_poll = False
    _gradient = 0.0
    _state: bool | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        friendly_name: str,
        entity_id: str,
        attribute: str,
        device_class: BinarySensorDeviceClass,
        invert: bool,
        max_samples: int,
        min_gradient: float,
        sample_duration: int,
    ) -> None:
        """Initialize the sensor."""
        self._hass = hass
        self.entity_id = generate_entity_id(ENTITY_ID_FORMAT, device_id, hass=hass)
        self._attr_name = friendly_name
        self._attr_device_class = device_class
        self._entity_id = entity_id
        self._attribute = attribute
        self._invert = invert
        self._sample_duration = sample_duration
        self._min_gradient = min_gradient
        self.samples: deque = deque(maxlen=max_samples)

    @property
    def is_on(self) -> bool | None:
        """Return true if sensor is on."""
        return self._state

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the state attributes of the sensor."""
        return {
            ATTR_ENTITY_ID: self._entity_id,
            ATTR_FRIENDLY_NAME: self._attr_name,
            ATTR_GRADIENT: self._gradient,
            ATTR_INVERT: self._invert,
            ATTR_MIN_GRADIENT: self._min_gradient,
            ATTR_SAMPLE_COUNT: len(self.samples),
            ATTR_SAMPLE_DURATION: self._sample_duration,
        }

    async def async_added_to_hass(self) -> None:
        """Complete device setup after being added to hass."""

        @callback
        def trend_sensor_state_listener(
            event: EventType[EventStateChangedData],
        ) -> None:
            """Handle state changes on the observed device."""
            if (new_state := event.data["new_state"]) is None:
                return
            try:
                if self._attribute:
                    state = new_state.attributes.get(self._attribute)
                else:
                    state = new_state.state
                if state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                    sample = (new_state.last_updated.timestamp(), float(state))  # type: ignore[arg-type]
                    self.samples.append(sample)
                    self.async_schedule_update_ha_state(True)
            except (ValueError, TypeError) as ex:
                _LOGGER.error(ex)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._entity_id], trend_sensor_state_listener
            )
        )

        if not (state := await self.async_get_last_state()):
            return
        if state.state == STATE_UNKNOWN:
            return
        self._state = state.state == STATE_ON

    async def async_update(self) -> None:
        """Get the latest data and update the states."""
        # Remove outdated samples
        if self._sample_duration > 0:
            cutoff = utcnow().timestamp() - self._sample_duration
            while self.samples and self.samples[0][0] < cutoff:
                self.samples.popleft()

        if len(self.samples) < 2:
            return

        # Calculate gradient of linear trend
        await self.hass.async_add_executor_job(self._calculate_gradient)

        # Update state
        self._state = (
            abs(self._gradient) > abs(self._min_gradient)
            and math.copysign(self._gradient, self._min_gradient) == self._gradient
        )

        if self._invert:
            self._state = not self._state

    def _calculate_gradient(self) -> None:
        """Compute the linear trend gradient of the current samples.

        This need run inside executor.
        """
        timestamps = np.array([t for t, _ in self.samples])
        values = np.array([s for _, s in self.samples])
        coeffs = np.polyfit(timestamps, values, 1)
        self._gradient = coeffs[0]
