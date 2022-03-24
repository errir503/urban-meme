"""Support for repeating alerts when conditions are met."""
from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any, final

import voluptuous as vol

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_MESSAGE,
    ATTR_TITLE,
    DOMAIN as DOMAIN_NOTIFY,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_REPEAT,
    CONF_STATE,
    SERVICE_TOGGLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers import service
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import ToggleEntity
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.dt import now

_LOGGER = logging.getLogger(__name__)

DOMAIN = "alert"

CONF_CAN_ACK = "can_acknowledge"
CONF_NOTIFIERS = "notifiers"
CONF_SKIP_FIRST = "skip_first"
CONF_ALERT_MESSAGE = "message"
CONF_DONE_MESSAGE = "done_message"
CONF_TITLE = "title"
CONF_DATA = "data"

DEFAULT_CAN_ACK = True
DEFAULT_SKIP_FIRST = False

ALERT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Required(CONF_STATE, default=STATE_ON): cv.string,
        vol.Required(CONF_REPEAT): vol.All(
            cv.ensure_list,
            [vol.Coerce(float)],
            # Minimum delay is 1 second = 0.016 minutes
            [vol.Range(min=0.016)],
        ),
        vol.Required(CONF_CAN_ACK, default=DEFAULT_CAN_ACK): cv.boolean,
        vol.Required(CONF_SKIP_FIRST, default=DEFAULT_SKIP_FIRST): cv.boolean,
        vol.Optional(CONF_ALERT_MESSAGE): cv.template,
        vol.Optional(CONF_DONE_MESSAGE): cv.template,
        vol.Optional(CONF_TITLE): cv.template,
        vol.Optional(CONF_DATA): dict,
        vol.Required(CONF_NOTIFIERS): vol.All(cv.ensure_list, [cv.string]),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: cv.schema_with_slug_keys(ALERT_SCHEMA)}, extra=vol.ALLOW_EXTRA
)

ALERT_SERVICE_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids})


def is_on(hass: HomeAssistant, entity_id: str) -> bool:
    """Return if the alert is firing and not acknowledged."""
    return hass.states.is_state(entity_id, STATE_ON)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Alert component."""
    entities: list[Alert] = []

    for object_id, cfg in config[DOMAIN].items():
        if not cfg:
            cfg = {}

        name = cfg[CONF_NAME]
        watched_entity_id = cfg[CONF_ENTITY_ID]
        alert_state = cfg[CONF_STATE]
        repeat = cfg[CONF_REPEAT]
        skip_first = cfg[CONF_SKIP_FIRST]
        message_template = cfg.get(CONF_ALERT_MESSAGE)
        done_message_template = cfg.get(CONF_DONE_MESSAGE)
        notifiers = cfg[CONF_NOTIFIERS]
        can_ack = cfg[CONF_CAN_ACK]
        title_template = cfg.get(CONF_TITLE)
        data = cfg.get(CONF_DATA)

        entities.append(
            Alert(
                hass,
                object_id,
                name,
                watched_entity_id,
                alert_state,
                repeat,
                skip_first,
                message_template,
                done_message_template,
                notifiers,
                can_ack,
                title_template,
                data,
            )
        )

    if not entities:
        return False

    async def async_handle_alert_service(service_call: ServiceCall) -> None:
        """Handle calls to alert services."""
        alert_ids = await service.async_extract_entity_ids(hass, service_call)

        for alert_id in alert_ids:
            for alert in entities:
                if alert.entity_id != alert_id:
                    continue

                alert.async_set_context(service_call.context)
                if service_call.service == SERVICE_TURN_ON:
                    await alert.async_turn_on()
                elif service_call.service == SERVICE_TOGGLE:
                    await alert.async_toggle()
                else:
                    await alert.async_turn_off()

    # Setup service calls
    hass.services.async_register(
        DOMAIN,
        SERVICE_TURN_OFF,
        async_handle_alert_service,
        schema=ALERT_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TURN_ON,
        async_handle_alert_service,
        schema=ALERT_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TOGGLE,
        async_handle_alert_service,
        schema=ALERT_SERVICE_SCHEMA,
    )

    for alert in entities:
        alert.async_write_ha_state()

    return True


class Alert(ToggleEntity):
    """Representation of an alert."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str,
        name: str,
        watched_entity_id: str,
        state: str,
        repeat: list[float],
        skip_first: bool,
        message_template: Template | None,
        done_message_template: Template | None,
        notifiers: list[str],
        can_ack: bool,
        title_template: Template | None,
        data: dict[Any, Any],
    ) -> None:
        """Initialize the alert."""
        self.hass = hass
        self._attr_name = name
        self._alert_state = state
        self._skip_first = skip_first
        self._data = data

        self._message_template = message_template
        if self._message_template is not None:
            self._message_template.hass = hass

        self._done_message_template = done_message_template
        if self._done_message_template is not None:
            self._done_message_template.hass = hass

        self._title_template = title_template
        if self._title_template is not None:
            self._title_template.hass = hass

        self._notifiers = notifiers
        self._can_ack = can_ack

        self._delay = [timedelta(minutes=val) for val in repeat]
        self._next_delay = 0

        self._firing = False
        self._ack = False
        self._cancel: Callable[[], None] | None = None
        self._send_done_message = False
        self.entity_id = f"{DOMAIN}.{entity_id}"

        async_track_state_change_event(
            hass, [watched_entity_id], self.watched_entity_change
        )

    @final  # type: ignore[misc]
    @property
    # pylint: disable=overridden-final-method
    def state(self) -> str:  # type: ignore[override]
        """Return the alert status."""
        if self._firing:
            if self._ack:
                return STATE_OFF
            return STATE_ON
        return STATE_IDLE

    async def watched_entity_change(self, event: Event) -> None:
        """Determine if the alert should start or stop."""
        if (to_state := event.data.get("new_state")) is None:
            return
        _LOGGER.debug("Watched entity (%s) has changed", event.data.get("entity_id"))
        if to_state.state == self._alert_state and not self._firing:
            await self.begin_alerting()
        if to_state.state != self._alert_state and self._firing:
            await self.end_alerting()

    async def begin_alerting(self) -> None:
        """Begin the alert procedures."""
        _LOGGER.debug("Beginning Alert: %s", self._attr_name)
        self._ack = False
        self._firing = True
        self._next_delay = 0

        if not self._skip_first:
            await self._notify()
        else:
            await self._schedule_notify()

        self.async_write_ha_state()

    async def end_alerting(self) -> None:
        """End the alert procedures."""
        _LOGGER.debug("Ending Alert: %s", self._attr_name)
        if self._cancel is not None:
            self._cancel()
            self._cancel = None

        self._ack = False
        self._firing = False
        if self._send_done_message:
            await self._notify_done_message()
        self.async_write_ha_state()

    async def _schedule_notify(self) -> None:
        """Schedule a notification."""
        delay = self._delay[self._next_delay]
        next_msg = now() + delay
        self._cancel = async_track_point_in_time(self.hass, self._notify, next_msg)
        self._next_delay = min(self._next_delay + 1, len(self._delay) - 1)

    async def _notify(self, *args: Any) -> None:
        """Send the alert notification."""
        if not self._firing:
            return

        if not self._ack:
            _LOGGER.info("Alerting: %s", self._attr_name)
            self._send_done_message = True

            if self._message_template is not None:
                message = self._message_template.async_render(parse_result=False)
            else:
                message = self._attr_name

            await self._send_notification_message(message)
        await self._schedule_notify()

    async def _notify_done_message(self) -> None:
        """Send notification of complete alert."""
        _LOGGER.info("Alerting: %s", self._done_message_template)
        self._send_done_message = False

        if self._done_message_template is None:
            return

        message = self._done_message_template.async_render(parse_result=False)

        await self._send_notification_message(message)

    async def _send_notification_message(self, message: Any) -> None:

        msg_payload = {ATTR_MESSAGE: message}

        if self._title_template is not None:
            title = self._title_template.async_render(parse_result=False)
            msg_payload[ATTR_TITLE] = title
        if self._data:
            msg_payload[ATTR_DATA] = self._data

        _LOGGER.debug(msg_payload)

        for target in self._notifiers:
            await self.hass.services.async_call(
                DOMAIN_NOTIFY, target, msg_payload, context=self._context
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Async Unacknowledge alert."""
        _LOGGER.debug("Reset Alert: %s", self._attr_name)
        self._ack = False
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Async Acknowledge alert."""
        _LOGGER.debug("Acknowledged Alert: %s", self._attr_name)
        self._ack = True
        self.async_write_ha_state()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Async toggle alert."""
        if self._ack:
            return await self.async_turn_on()
        return await self.async_turn_off()
