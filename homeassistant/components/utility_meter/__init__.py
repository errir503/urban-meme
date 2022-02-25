"""Support for tracking consumption over given periods of time."""
from datetime import timedelta
import logging

from croniter import croniter
import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_TARIFF,
    CONF_CRON_PATTERN,
    CONF_METER,
    CONF_METER_DELTA_VALUES,
    CONF_METER_NET_CONSUMPTION,
    CONF_METER_OFFSET,
    CONF_METER_TYPE,
    CONF_SOURCE_SENSOR,
    CONF_TARIFF,
    CONF_TARIFF_ENTITY,
    CONF_TARIFFS,
    DATA_TARIFF_SENSORS,
    DATA_UTILITY,
    DOMAIN,
    METER_TYPES,
    SERVICE_RESET,
    SERVICE_SELECT_NEXT_TARIFF,
    SERVICE_SELECT_TARIFF,
    SIGNAL_RESET_METER,
)

_LOGGER = logging.getLogger(__name__)

TARIFF_ICON = "mdi:clock-outline"

ATTR_TARIFFS = "tariffs"

DEFAULT_OFFSET = timedelta(hours=0)


def validate_cron_pattern(pattern):
    """Check that the pattern is well-formed."""
    if croniter.is_valid(pattern):
        return pattern
    raise vol.Invalid("Invalid pattern")


def period_or_cron(config):
    """Check that if cron pattern is used, then meter type and offsite must be removed."""
    if CONF_CRON_PATTERN in config and CONF_METER_TYPE in config:
        raise vol.Invalid(f"Use <{CONF_CRON_PATTERN}> or <{CONF_METER_TYPE}>")
    if (
        CONF_CRON_PATTERN in config
        and CONF_METER_OFFSET in config
        and config[CONF_METER_OFFSET] != DEFAULT_OFFSET
    ):
        raise vol.Invalid(
            f"When <{CONF_CRON_PATTERN}> is used <{CONF_METER_OFFSET}> has no meaning"
        )
    return config


def max_28_days(config):
    """Check that time period does not include more then 28 days."""
    if config.days >= 28:
        raise vol.Invalid(
            "Unsupported offset of more then 28 days, please use a cron pattern."
        )

    return config


METER_CONFIG_SCHEMA = vol.Schema(
    vol.All(
        {
            vol.Required(CONF_SOURCE_SENSOR): cv.entity_id,
            vol.Optional(CONF_NAME): cv.string,
            vol.Optional(CONF_METER_TYPE): vol.In(METER_TYPES),
            vol.Optional(CONF_METER_OFFSET, default=DEFAULT_OFFSET): vol.All(
                cv.time_period, cv.positive_timedelta, max_28_days
            ),
            vol.Optional(CONF_METER_DELTA_VALUES, default=False): cv.boolean,
            vol.Optional(CONF_METER_NET_CONSUMPTION, default=False): cv.boolean,
            vol.Optional(CONF_TARIFFS, default=[]): vol.All(
                cv.ensure_list, [cv.string]
            ),
            vol.Optional(CONF_CRON_PATTERN): validate_cron_pattern,
        },
        period_or_cron,
    )
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({cv.slug: METER_CONFIG_SCHEMA})}, extra=vol.ALLOW_EXTRA
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up an Utility Meter."""
    component = EntityComponent(_LOGGER, DOMAIN, hass)
    hass.data[DATA_UTILITY] = {}
    register_services = False

    for meter, conf in config[DOMAIN].items():
        _LOGGER.debug("Setup %s.%s", DOMAIN, meter)

        hass.data[DATA_UTILITY][meter] = conf
        hass.data[DATA_UTILITY][meter][DATA_TARIFF_SENSORS] = []

        if not conf[CONF_TARIFFS]:
            # only one entity is required
            name = conf.get(CONF_NAME, meter)
            hass.async_create_task(
                discovery.async_load_platform(
                    hass,
                    SENSOR_DOMAIN,
                    DOMAIN,
                    {name: {CONF_METER: meter, CONF_NAME: name}},
                    config,
                )
            )
        else:
            # create tariff selection
            await component.async_add_entities(
                [TariffSelect(meter, list(conf[CONF_TARIFFS]))]
            )
            hass.data[DATA_UTILITY][meter][CONF_TARIFF_ENTITY] = "{}.{}".format(
                DOMAIN, meter
            )

            # add one meter for each tariff
            tariff_confs = {}
            for tariff in conf[CONF_TARIFFS]:
                name = f"{meter} {tariff}"
                tariff_confs[name] = {
                    CONF_METER: meter,
                    CONF_NAME: name,
                    CONF_TARIFF: tariff,
                }

            hass.async_create_task(
                discovery.async_load_platform(
                    hass, SENSOR_DOMAIN, DOMAIN, tariff_confs, config
                )
            )
            register_services = True

    if register_services:
        component.async_register_entity_service(SERVICE_RESET, {}, "async_reset_meters")

        component.async_register_entity_service(
            SERVICE_SELECT_TARIFF,
            {vol.Required(ATTR_TARIFF): cv.string},
            "async_select_tariff",
        )

        component.async_register_entity_service(
            SERVICE_SELECT_NEXT_TARIFF, {}, "async_next_tariff"
        )

    return True


class TariffSelect(RestoreEntity):
    """Representation of a Tariff selector."""

    def __init__(self, name, tariffs):
        """Initialize a tariff selector."""
        self._name = name
        self._current_tariff = None
        self._tariffs = tariffs
        self._icon = TARIFF_ICON

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        state = await self.async_get_last_state()
        if not state or state.state not in self._tariffs:
            self._current_tariff = self._tariffs[0]
        else:
            self._current_tariff = state.state

    @property
    def should_poll(self):
        """If entity should be polled."""
        return False

    @property
    def name(self):
        """Return the name of the select input."""
        return self._name

    @property
    def icon(self):
        """Return the icon to be used for this entity."""
        return self._icon

    @property
    def state(self):
        """Return the state of the component."""
        return self._current_tariff

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {ATTR_TARIFFS: self._tariffs}

    async def async_reset_meters(self):
        """Reset all sensors of this meter."""
        _LOGGER.debug("reset meter %s", self.entity_id)
        async_dispatcher_send(self.hass, SIGNAL_RESET_METER, self.entity_id)

    async def async_select_tariff(self, tariff):
        """Select new option."""
        if tariff not in self._tariffs:
            _LOGGER.warning(
                "Invalid tariff: %s (possible tariffs: %s)",
                tariff,
                ", ".join(self._tariffs),
            )
            return
        self._current_tariff = tariff
        self.async_write_ha_state()

    async def async_next_tariff(self):
        """Offset current index."""
        current_index = self._tariffs.index(self._current_tariff)
        new_index = (current_index + 1) % len(self._tariffs)
        self._current_tariff = self._tariffs[new_index]
        self.async_write_ha_state()
