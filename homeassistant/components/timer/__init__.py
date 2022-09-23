"""Support for Timers."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging

import voluptuous as vol

from homeassistant.const import (
    ATTR_EDITABLE,
    ATTR_ENTITY_ID,
    CONF_ICON,
    CONF_ID,
    CONF_NAME,
    SERVICE_RELOAD,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import collection
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.restore_state import RestoreEntity
import homeassistant.helpers.service
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

DOMAIN = "timer"
ENTITY_ID_FORMAT = DOMAIN + ".{}"

DEFAULT_DURATION = 0
DEFAULT_RESTORE = False

ATTR_DURATION = "duration"
ATTR_REMAINING = "remaining"
ATTR_FINISHES_AT = "finishes_at"
ATTR_RESTORE = "restore"
ATTR_FINISHED_AT = "finished_at"

CONF_DURATION = "duration"
CONF_RESTORE = "restore"

STATUS_IDLE = "idle"
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"

EVENT_TIMER_FINISHED = "timer.finished"
EVENT_TIMER_CANCELLED = "timer.cancelled"
EVENT_TIMER_STARTED = "timer.started"
EVENT_TIMER_RESTARTED = "timer.restarted"
EVENT_TIMER_PAUSED = "timer.paused"

SERVICE_START = "start"
SERVICE_PAUSE = "pause"
SERVICE_CANCEL = "cancel"
SERVICE_FINISH = "finish"

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

STORAGE_FIELDS = {
    vol.Required(CONF_NAME): cv.string,
    vol.Optional(CONF_ICON): cv.icon,
    vol.Optional(CONF_DURATION, default=DEFAULT_DURATION): cv.time_period,
    vol.Optional(CONF_RESTORE, default=DEFAULT_RESTORE): cv.boolean,
}


def _format_timedelta(delta: timedelta):
    total_seconds = delta.total_seconds()
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02}:{int(seconds):02}"


def _none_to_empty_dict(value):
    if value is None:
        return {}
    return value


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: cv.schema_with_slug_keys(
            vol.All(
                _none_to_empty_dict,
                {
                    vol.Optional(CONF_NAME): cv.string,
                    vol.Optional(CONF_ICON): cv.icon,
                    vol.Optional(CONF_DURATION, default=DEFAULT_DURATION): vol.All(
                        cv.time_period, _format_timedelta
                    ),
                    vol.Optional(CONF_RESTORE, default=DEFAULT_RESTORE): cv.boolean,
                },
            )
        )
    },
    extra=vol.ALLOW_EXTRA,
)

RELOAD_SERVICE_SCHEMA = vol.Schema({})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up an input select."""
    component = EntityComponent[Timer](_LOGGER, DOMAIN, hass)
    id_manager = collection.IDManager()

    yaml_collection = collection.YamlCollection(
        logging.getLogger(f"{__name__}.yaml_collection"), id_manager
    )
    collection.sync_entity_lifecycle(
        hass, DOMAIN, DOMAIN, component, yaml_collection, Timer
    )

    storage_collection = TimerStorageCollection(
        Store(hass, STORAGE_VERSION, STORAGE_KEY),
        logging.getLogger(f"{__name__}.storage_collection"),
        id_manager,
    )
    collection.sync_entity_lifecycle(
        hass, DOMAIN, DOMAIN, component, storage_collection, Timer
    )

    await yaml_collection.async_load(
        [{CONF_ID: id_, **cfg} for id_, cfg in config.get(DOMAIN, {}).items()]
    )
    await storage_collection.async_load()

    collection.StorageCollectionWebsocket(
        storage_collection, DOMAIN, DOMAIN, STORAGE_FIELDS, STORAGE_FIELDS
    ).async_setup(hass)

    async def reload_service_handler(service_call: ServiceCall) -> None:
        """Reload yaml entities."""
        conf = await component.async_prepare_reload(skip_reset=True)
        if conf is None:
            conf = {DOMAIN: {}}
        await yaml_collection.async_load(
            [{CONF_ID: id_, **cfg} for id_, cfg in conf.get(DOMAIN, {}).items()]
        )

    homeassistant.helpers.service.async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_RELOAD,
        reload_service_handler,
        schema=RELOAD_SERVICE_SCHEMA,
    )
    component.async_register_entity_service(
        SERVICE_START,
        {vol.Optional(ATTR_DURATION, default=DEFAULT_DURATION): cv.time_period},
        "async_start",
    )
    component.async_register_entity_service(SERVICE_PAUSE, {}, "async_pause")
    component.async_register_entity_service(SERVICE_CANCEL, {}, "async_cancel")
    component.async_register_entity_service(SERVICE_FINISH, {}, "async_finish")

    return True


class TimerStorageCollection(collection.StorageCollection):
    """Timer storage based collection."""

    CREATE_UPDATE_SCHEMA = vol.Schema(STORAGE_FIELDS)

    async def _process_create_data(self, data: dict) -> dict:
        """Validate the config is valid."""
        data = self.CREATE_UPDATE_SCHEMA(data)
        # make duration JSON serializeable
        data[CONF_DURATION] = _format_timedelta(data[CONF_DURATION])
        return data

    @callback
    def _get_suggested_id(self, info: dict) -> str:
        """Suggest an ID based on the config."""
        return info[CONF_NAME]

    async def _update_data(self, data: dict, update_data: dict) -> dict:
        """Return a new updated data object."""
        data = {CONF_ID: data[CONF_ID]} | self.CREATE_UPDATE_SCHEMA(update_data)
        # make duration JSON serializeable
        if CONF_DURATION in update_data:
            data[CONF_DURATION] = _format_timedelta(data[CONF_DURATION])
        return data


class Timer(collection.CollectionEntity, RestoreEntity):
    """Representation of a timer."""

    editable: bool

    def __init__(self, config: ConfigType) -> None:
        """Initialize a timer."""
        self._config: dict = config
        self._state: str = STATUS_IDLE
        self._duration = cv.time_period_str(config[CONF_DURATION])
        self._remaining: timedelta | None = None
        self._end: datetime | None = None
        self._listener: Callable[[], None] | None = None
        self._restore: bool = self._config.get(CONF_RESTORE, DEFAULT_RESTORE)

        self._attr_should_poll = False
        self._attr_force_update = True

    @classmethod
    def from_storage(cls, config: ConfigType) -> Timer:
        """Return entity instance initialized from storage."""
        timer = cls(config)
        timer.editable = True
        return timer

    @classmethod
    def from_yaml(cls, config: ConfigType) -> Timer:
        """Return entity instance initialized from yaml."""
        timer = cls(config)
        timer.entity_id = ENTITY_ID_FORMAT.format(config[CONF_ID])
        timer.editable = False
        return timer

    @property
    def name(self):
        """Return name of the timer."""
        return self._config.get(CONF_NAME)

    @property
    def icon(self):
        """Return the icon to be used for this entity."""
        return self._config.get(CONF_ICON)

    @property
    def state(self):
        """Return the current value of the timer."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            ATTR_DURATION: _format_timedelta(self._duration),
            ATTR_EDITABLE: self.editable,
        }
        if self._end is not None:
            attrs[ATTR_FINISHES_AT] = self._end.isoformat()
        if self._remaining is not None:
            attrs[ATTR_REMAINING] = _format_timedelta(self._remaining)
        if self._restore:
            attrs[ATTR_RESTORE] = self._restore

        return attrs

    @property
    def unique_id(self) -> str | None:
        """Return unique id for the entity."""
        return self._config[CONF_ID]

    async def async_added_to_hass(self):
        """Call when entity is about to be added to Home Assistant."""
        # If we don't need to restore a previous state or no previous state exists,
        # start at idle
        if not self._restore or (state := await self.async_get_last_state()) is None:
            self._state = STATUS_IDLE
            return

        # Begin restoring state
        self._state = state.state
        self._duration = cv.time_period(state.attributes[ATTR_DURATION])

        # Nothing more to do if the timer is idle
        if self._state == STATUS_IDLE:
            return

        # If the timer was paused, we restore the remaining time
        if self._state == STATUS_PAUSED:
            self._remaining = cv.time_period(state.attributes[ATTR_REMAINING])
            return
        # If we get here, the timer must have been active so we need to decide what
        # to do based on end time and the current time
        end = cv.datetime(state.attributes[ATTR_FINISHES_AT])
        # If there is time remaining in the timer, restore the remaining time then
        # start the timer
        if (remaining := end - dt_util.utcnow().replace(microsecond=0)) > timedelta(0):
            self._remaining = remaining
            self._state = STATUS_PAUSED
            self.async_start()
        # If the timer ended before now, finish the timer. The event will indicate
        # when the timer was expected to fire.
        else:
            self._end = end
            self.async_finish()

    @callback
    def async_start(self, duration: timedelta | None = None):
        """Start a timer."""
        if self._listener:
            self._listener()
            self._listener = None

        event = EVENT_TIMER_STARTED
        if self._state in (STATUS_ACTIVE, STATUS_PAUSED):
            event = EVENT_TIMER_RESTARTED

        self._state = STATUS_ACTIVE
        start = dt_util.utcnow().replace(microsecond=0)

        # Set remaining to new value if needed
        if duration:
            self._remaining = self._duration = duration
        elif not self._remaining:
            self._remaining = self._duration

        self._end = start + self._remaining

        self.hass.bus.async_fire(event, {ATTR_ENTITY_ID: self.entity_id})

        self._listener = async_track_point_in_utc_time(
            self.hass, self._async_finished, self._end
        )
        self.async_write_ha_state()

    @callback
    def async_pause(self):
        """Pause a timer."""
        if self._listener is None:
            return

        self._listener()
        self._listener = None
        self._remaining = self._end - dt_util.utcnow().replace(microsecond=0)
        self._state = STATUS_PAUSED
        self._end = None
        self.hass.bus.async_fire(EVENT_TIMER_PAUSED, {ATTR_ENTITY_ID: self.entity_id})
        self.async_write_ha_state()

    @callback
    def async_cancel(self):
        """Cancel a timer."""
        if self._listener:
            self._listener()
            self._listener = None
        self._state = STATUS_IDLE
        self._end = None
        self._remaining = None
        self.hass.bus.async_fire(
            EVENT_TIMER_CANCELLED, {ATTR_ENTITY_ID: self.entity_id}
        )
        self.async_write_ha_state()

    @callback
    def async_finish(self):
        """Reset and updates the states, fire finished event."""
        if self._state != STATUS_ACTIVE:
            return

        if self._listener:
            self._listener()
            self._listener = None
        end = self._end
        self._state = STATUS_IDLE
        self._end = None
        self._remaining = None
        self.hass.bus.async_fire(
            EVENT_TIMER_FINISHED,
            {ATTR_ENTITY_ID: self.entity_id, ATTR_FINISHED_AT: end.isoformat()},
        )
        self.async_write_ha_state()

    @callback
    def _async_finished(self, time):
        """Reset and updates the states, fire finished event."""
        if self._state != STATUS_ACTIVE:
            return

        self._listener = None
        self._state = STATUS_IDLE
        end = self._end
        self._end = None
        self._remaining = None
        self.hass.bus.async_fire(
            EVENT_TIMER_FINISHED,
            {ATTR_ENTITY_ID: self.entity_id, ATTR_FINISHED_AT: end.isoformat()},
        )
        self.async_write_ha_state()

    async def async_update_config(self, config: ConfigType) -> None:
        """Handle when the config is updated."""
        self._config = config
        self._duration = cv.time_period_str(config[CONF_DURATION])
        self._restore = config.get(CONF_RESTORE, DEFAULT_RESTORE)
        self.async_write_ha_state()
