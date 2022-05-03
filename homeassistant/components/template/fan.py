"""Support for Template fans."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.fan import (
    ATTR_DIRECTION,
    ATTR_OSCILLATING,
    ATTR_PERCENTAGE,
    ATTR_PRESET_MODE,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    ENTITY_ID_FORMAT,
    FanEntity,
    FanEntityFeature,
)
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_FRIENDLY_NAME,
    CONF_UNIQUE_ID,
    CONF_VALUE_TEMPLATE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import TemplateError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.script import Script
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN
from .template_entity import (
    TEMPLATE_ENTITY_AVAILABILITY_SCHEMA_LEGACY,
    TemplateEntity,
    rewrite_common_legacy_to_modern_conf,
)

_LOGGER = logging.getLogger(__name__)

CONF_FANS = "fans"
CONF_SPEED_COUNT = "speed_count"
CONF_PRESET_MODES = "preset_modes"
CONF_PERCENTAGE_TEMPLATE = "percentage_template"
CONF_PRESET_MODE_TEMPLATE = "preset_mode_template"
CONF_OSCILLATING_TEMPLATE = "oscillating_template"
CONF_DIRECTION_TEMPLATE = "direction_template"
CONF_ON_ACTION = "turn_on"
CONF_OFF_ACTION = "turn_off"
CONF_SET_PERCENTAGE_ACTION = "set_percentage"
CONF_SET_SPEED_ACTION = "set_speed"
CONF_SET_OSCILLATING_ACTION = "set_oscillating"
CONF_SET_DIRECTION_ACTION = "set_direction"
CONF_SET_PRESET_MODE_ACTION = "set_preset_mode"

_VALID_STATES = [STATE_ON, STATE_OFF]
_VALID_DIRECTIONS = [DIRECTION_FORWARD, DIRECTION_REVERSE]

FAN_SCHEMA = vol.All(
    cv.deprecated(CONF_ENTITY_ID),
    vol.Schema(
        {
            vol.Optional(CONF_FRIENDLY_NAME): cv.string,
            vol.Required(CONF_VALUE_TEMPLATE): cv.template,
            vol.Optional(CONF_PERCENTAGE_TEMPLATE): cv.template,
            vol.Optional(CONF_PRESET_MODE_TEMPLATE): cv.template,
            vol.Optional(CONF_OSCILLATING_TEMPLATE): cv.template,
            vol.Optional(CONF_DIRECTION_TEMPLATE): cv.template,
            vol.Required(CONF_ON_ACTION): cv.SCRIPT_SCHEMA,
            vol.Required(CONF_OFF_ACTION): cv.SCRIPT_SCHEMA,
            vol.Optional(CONF_SET_PERCENTAGE_ACTION): cv.SCRIPT_SCHEMA,
            vol.Optional(CONF_SET_PRESET_MODE_ACTION): cv.SCRIPT_SCHEMA,
            vol.Optional(CONF_SET_OSCILLATING_ACTION): cv.SCRIPT_SCHEMA,
            vol.Optional(CONF_SET_DIRECTION_ACTION): cv.SCRIPT_SCHEMA,
            vol.Optional(CONF_SPEED_COUNT): vol.Coerce(int),
            vol.Optional(CONF_PRESET_MODES): cv.ensure_list,
            vol.Optional(CONF_ENTITY_ID): cv.entity_ids,
            vol.Optional(CONF_UNIQUE_ID): cv.string,
        }
    ).extend(TEMPLATE_ENTITY_AVAILABILITY_SCHEMA_LEGACY.schema),
)

PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_FANS): cv.schema_with_slug_keys(FAN_SCHEMA)}
)


async def _async_create_entities(hass, config):
    """Create the Template Fans."""
    fans = []

    for object_id, entity_config in config[CONF_FANS].items():

        entity_config = rewrite_common_legacy_to_modern_conf(entity_config)

        unique_id = entity_config.get(CONF_UNIQUE_ID)

        fans.append(
            TemplateFan(
                hass,
                object_id,
                entity_config,
                unique_id,
            )
        )

    return fans


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the template fans."""
    async_add_entities(await _async_create_entities(hass, config))


class TemplateFan(TemplateEntity, FanEntity):
    """A template fan component."""

    def __init__(
        self,
        hass,
        object_id,
        config,
        unique_id,
    ):
        """Initialize the fan."""
        super().__init__(
            hass, config=config, fallback_name=object_id, unique_id=unique_id
        )
        self.hass = hass
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, object_id, hass=hass
        )
        friendly_name = self._attr_name

        self._template = config[CONF_VALUE_TEMPLATE]
        self._percentage_template = config.get(CONF_PERCENTAGE_TEMPLATE)
        self._preset_mode_template = config.get(CONF_PRESET_MODE_TEMPLATE)
        self._oscillating_template = config.get(CONF_OSCILLATING_TEMPLATE)
        self._direction_template = config.get(CONF_DIRECTION_TEMPLATE)
        self._supported_features = 0

        self._on_script = Script(hass, config[CONF_ON_ACTION], friendly_name, DOMAIN)
        self._off_script = Script(hass, config[CONF_OFF_ACTION], friendly_name, DOMAIN)

        self._set_speed_script = None
        if set_speed_action := config.get(CONF_SET_SPEED_ACTION):
            self._set_speed_script = Script(
                hass, set_speed_action, friendly_name, DOMAIN
            )

        self._set_percentage_script = None
        if set_percentage_action := config.get(CONF_SET_PERCENTAGE_ACTION):
            self._set_percentage_script = Script(
                hass, set_percentage_action, friendly_name, DOMAIN
            )

        self._set_preset_mode_script = None
        if set_preset_mode_action := config.get(CONF_SET_PRESET_MODE_ACTION):
            self._set_preset_mode_script = Script(
                hass, set_preset_mode_action, friendly_name, DOMAIN
            )

        self._set_oscillating_script = None
        if set_oscillating_action := config.get(CONF_SET_OSCILLATING_ACTION):
            self._set_oscillating_script = Script(
                hass, set_oscillating_action, friendly_name, DOMAIN
            )

        self._set_direction_script = None
        if set_direction_action := config.get(CONF_SET_DIRECTION_ACTION):
            self._set_direction_script = Script(
                hass, set_direction_action, friendly_name, DOMAIN
            )

        self._state = STATE_OFF
        self._percentage = None
        self._preset_mode = None
        self._oscillating = None
        self._direction = None

        # Number of valid speeds
        self._speed_count = config.get(CONF_SPEED_COUNT)

        # List of valid preset modes
        self._preset_modes = config.get(CONF_PRESET_MODES)

        if self._percentage_template:
            self._supported_features |= FanEntityFeature.SET_SPEED
        if self._preset_mode_template and self._preset_modes:
            self._supported_features |= FanEntityFeature.PRESET_MODE
        if self._oscillating_template:
            self._supported_features |= FanEntityFeature.OSCILLATE
        if self._direction_template:
            self._supported_features |= FanEntityFeature.DIRECTION

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return self._supported_features

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return self._speed_count or 100

    @property
    def preset_modes(self) -> list[str]:
        """Get the list of available preset modes."""
        return self._preset_modes

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._state == STATE_ON

    @property
    def preset_mode(self):
        """Return the current preset mode."""
        return self._preset_mode

    @property
    def percentage(self):
        """Return the current speed percentage."""
        return self._percentage

    @property
    def oscillating(self):
        """Return the oscillation state."""
        return self._oscillating

    @property
    def current_direction(self):
        """Return the oscillation state."""
        return self._direction

    async def async_turn_on(
        self,
        percentage: int = None,
        preset_mode: str = None,
        **kwargs,
    ) -> None:
        """Turn on the fan."""
        await self._on_script.async_run(
            {
                ATTR_PERCENTAGE: percentage,
                ATTR_PRESET_MODE: preset_mode,
            },
            context=self._context,
        )
        self._state = STATE_ON

        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        await self._off_script.async_run(context=self._context)
        self._state = STATE_OFF

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the percentage speed of the fan."""
        self._state = STATE_OFF if percentage == 0 else STATE_ON
        self._percentage = percentage
        self._preset_mode = None

        if self._set_percentage_script:
            await self._set_percentage_script.async_run(
                {ATTR_PERCENTAGE: self._percentage}, context=self._context
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset_mode of the fan."""
        if self.preset_modes and preset_mode not in self.preset_modes:
            _LOGGER.error(
                "Received invalid preset_mode: %s for entity %s. Expected: %s",
                preset_mode,
                self.entity_id,
                self.preset_modes,
            )
            return

        self._state = STATE_ON
        self._preset_mode = preset_mode
        self._percentage = None

        if self._set_preset_mode_script:
            await self._set_preset_mode_script.async_run(
                {ATTR_PRESET_MODE: self._preset_mode}, context=self._context
            )

    async def async_oscillate(self, oscillating: bool) -> None:
        """Set oscillation of the fan."""
        if self._set_oscillating_script is None:
            return

        self._oscillating = oscillating
        await self._set_oscillating_script.async_run(
            {ATTR_OSCILLATING: oscillating}, context=self._context
        )

    async def async_set_direction(self, direction: str) -> None:
        """Set the direction of the fan."""
        if self._set_direction_script is None:
            return

        if direction in _VALID_DIRECTIONS:
            self._direction = direction
            await self._set_direction_script.async_run(
                {ATTR_DIRECTION: direction}, context=self._context
            )
        else:
            _LOGGER.error(
                "Received invalid direction: %s for entity %s. Expected: %s",
                direction,
                self.entity_id,
                ", ".join(_VALID_DIRECTIONS),
            )

    @callback
    def _update_state(self, result):
        super()._update_state(result)
        if isinstance(result, TemplateError):
            self._state = None
            return

        # Validate state
        if result in _VALID_STATES:
            self._state = result
        elif result in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = None
        else:
            _LOGGER.error(
                "Received invalid fan is_on state: %s for entity %s. Expected: %s",
                result,
                self.entity_id,
                ", ".join(_VALID_STATES),
            )
            self._state = None

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.add_template_attribute("_state", self._template, None, self._update_state)
        if self._preset_mode_template is not None:
            self.add_template_attribute(
                "_preset_mode",
                self._preset_mode_template,
                None,
                self._update_preset_mode,
                none_on_template_error=True,
            )
        if self._percentage_template is not None:
            self.add_template_attribute(
                "_percentage",
                self._percentage_template,
                None,
                self._update_percentage,
                none_on_template_error=True,
            )
        if self._oscillating_template is not None:
            self.add_template_attribute(
                "_oscillating",
                self._oscillating_template,
                None,
                self._update_oscillating,
                none_on_template_error=True,
            )
        if self._direction_template is not None:
            self.add_template_attribute(
                "_direction",
                self._direction_template,
                None,
                self._update_direction,
                none_on_template_error=True,
            )
        await super().async_added_to_hass()

    @callback
    def _update_percentage(self, percentage):
        # Validate percentage
        try:
            percentage = int(float(percentage))
        except ValueError:
            _LOGGER.error(
                "Received invalid percentage: %s for entity %s",
                percentage,
                self.entity_id,
            )
            self._percentage = 0
            self._preset_mode = None
            return

        if 0 <= percentage <= 100:
            self._percentage = percentage
            self._preset_mode = None
        else:
            _LOGGER.error(
                "Received invalid percentage: %s for entity %s",
                percentage,
                self.entity_id,
            )
            self._percentage = 0
            self._preset_mode = None

    @callback
    def _update_preset_mode(self, preset_mode):
        # Validate preset mode
        preset_mode = str(preset_mode)

        if self.preset_modes and preset_mode in self.preset_modes:
            self._percentage = None
            self._preset_mode = preset_mode
        elif preset_mode in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._percentage = None
            self._preset_mode = None
        else:
            _LOGGER.error(
                "Received invalid preset_mode: %s for entity %s. Expected: %s",
                preset_mode,
                self.entity_id,
                self.preset_mode,
            )
            self._percentage = None
            self._preset_mode = None

    @callback
    def _update_oscillating(self, oscillating):
        # Validate osc
        if oscillating == "True" or oscillating is True:
            self._oscillating = True
        elif oscillating == "False" or oscillating is False:
            self._oscillating = False
        elif oscillating in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._oscillating = None
        else:
            _LOGGER.error(
                "Received invalid oscillating: %s for entity %s. Expected: True/False",
                oscillating,
                self.entity_id,
            )
            self._oscillating = None

    @callback
    def _update_direction(self, direction):
        # Validate direction
        if direction in _VALID_DIRECTIONS:
            self._direction = direction
        elif direction in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._direction = None
        else:
            _LOGGER.error(
                "Received invalid direction: %s for entity %s. Expected: %s",
                direction,
                self.entity_id,
                ", ".join(_VALID_DIRECTIONS),
            )
            self._direction = None
