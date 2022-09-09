"""Support for RESTful switches."""
from __future__ import annotations

import asyncio
from http import HTTPStatus
import logging
from typing import Any

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.components.switch import (
    DEVICE_CLASSES_SCHEMA,
    PLATFORM_SCHEMA,
    SwitchEntity,
)
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_HEADERS,
    CONF_METHOD,
    CONF_PARAMS,
    CONF_PASSWORD,
    CONF_RESOURCE,
    CONF_TIMEOUT,
    CONF_UNIQUE_ID,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, template
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.template_entity import (
    TEMPLATE_ENTITY_BASE_SCHEMA,
    TemplateEntity,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)
CONF_BODY_OFF = "body_off"
CONF_BODY_ON = "body_on"
CONF_IS_ON_TEMPLATE = "is_on_template"
CONF_STATE_RESOURCE = "state_resource"

DEFAULT_METHOD = "post"
DEFAULT_BODY_OFF = "OFF"
DEFAULT_BODY_ON = "ON"
DEFAULT_NAME = "REST Switch"
DEFAULT_TIMEOUT = 10
DEFAULT_VERIFY_SSL = True

SUPPORT_REST_METHODS = ["post", "put", "patch"]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        **TEMPLATE_ENTITY_BASE_SCHEMA.schema,
        vol.Required(CONF_RESOURCE): cv.url,
        vol.Optional(CONF_STATE_RESOURCE): cv.url,
        vol.Optional(CONF_HEADERS): {cv.string: cv.template},
        vol.Optional(CONF_PARAMS): {cv.string: cv.template},
        vol.Optional(CONF_BODY_OFF, default=DEFAULT_BODY_OFF): cv.template,
        vol.Optional(CONF_BODY_ON, default=DEFAULT_BODY_ON): cv.template,
        vol.Optional(CONF_IS_ON_TEMPLATE): cv.template,
        vol.Optional(CONF_METHOD, default=DEFAULT_METHOD): vol.All(
            vol.Lower, vol.In(SUPPORT_REST_METHODS)
        ),
        vol.Optional(CONF_DEVICE_CLASS): DEVICE_CLASSES_SCHEMA,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
        vol.Inclusive(CONF_USERNAME, "authentication"): cv.string,
        vol.Inclusive(CONF_PASSWORD, "authentication"): cv.string,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the RESTful switch."""
    resource = config.get(CONF_RESOURCE)
    unique_id = config.get(CONF_UNIQUE_ID)

    try:
        switch = RestSwitch(hass, config, unique_id)

        req = await switch.get_device_state(hass)
        if req.status >= HTTPStatus.BAD_REQUEST:
            _LOGGER.error("Got non-ok response from resource: %s", req.status)
        else:
            async_add_entities([switch])
    except (TypeError, ValueError):
        _LOGGER.error(
            "Missing resource or schema in configuration. "
            "Add http:// or https:// to your URL"
        )
    except (asyncio.TimeoutError, aiohttp.ClientError):
        _LOGGER.error("No route to resource/endpoint: %s", resource)


class RestSwitch(TemplateEntity, SwitchEntity):
    """Representation of a switch that can be toggled using REST."""

    def __init__(
        self,
        hass,
        config,
        unique_id,
    ):
        """Initialize the REST switch."""
        TemplateEntity.__init__(
            self,
            hass,
            config=config,
            fallback_name=DEFAULT_NAME,
            unique_id=unique_id,
        )

        self._state = None

        auth = None
        if username := config.get(CONF_USERNAME):
            auth = aiohttp.BasicAuth(username, password=config[CONF_PASSWORD])

        self._resource = config.get(CONF_RESOURCE)
        self._state_resource = config.get(CONF_STATE_RESOURCE) or self._resource
        self._method = config.get(CONF_METHOD)
        self._headers = config.get(CONF_HEADERS)
        self._params = config.get(CONF_PARAMS)
        self._auth = auth
        self._body_on = config.get(CONF_BODY_ON)
        self._body_off = config.get(CONF_BODY_OFF)
        self._is_on_template = config.get(CONF_IS_ON_TEMPLATE)
        self._timeout = config.get(CONF_TIMEOUT)
        self._verify_ssl = config.get(CONF_VERIFY_SSL)

        self._attr_device_class = config.get(CONF_DEVICE_CLASS)

        if (is_on_template := self._is_on_template) is not None:
            is_on_template.hass = hass
        if (body_on := self._body_on) is not None:
            body_on.hass = hass
        if (body_off := self._body_off) is not None:
            body_off.hass = hass

        template.attach(hass, self._headers)
        template.attach(hass, self._params)

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        body_on_t = self._body_on.async_render(parse_result=False)

        try:
            req = await self.set_device_state(body_on_t)

            if req.status == HTTPStatus.OK:
                self._state = True
            else:
                _LOGGER.error(
                    "Can't turn on %s. Is resource/endpoint offline?", self._resource
                )
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error("Error while switching on %s", self._resource)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        body_off_t = self._body_off.async_render(parse_result=False)

        try:
            req = await self.set_device_state(body_off_t)
            if req.status == HTTPStatus.OK:
                self._state = False
            else:
                _LOGGER.error(
                    "Can't turn off %s. Is resource/endpoint offline?", self._resource
                )
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error("Error while switching off %s", self._resource)

    async def set_device_state(self, body):
        """Send a state update to the device."""
        websession = async_get_clientsession(self.hass, self._verify_ssl)

        rendered_headers = template.render_complex(self._headers, parse_result=False)
        rendered_params = template.render_complex(self._params)

        async with async_timeout.timeout(self._timeout):
            req = await getattr(websession, self._method)(
                self._resource,
                auth=self._auth,
                data=bytes(body, "utf-8"),
                headers=rendered_headers,
                params=rendered_params,
            )
            return req

    async def async_update(self) -> None:
        """Get the current state, catching errors."""
        try:
            await self.get_device_state(self.hass)
        except asyncio.TimeoutError:
            _LOGGER.exception("Timed out while fetching data")
        except aiohttp.ClientError as err:
            _LOGGER.exception("Error while fetching data: %s", err)

    async def get_device_state(self, hass):
        """Get the latest data from REST API and update the state."""
        websession = async_get_clientsession(hass, self._verify_ssl)

        rendered_headers = template.render_complex(self._headers, parse_result=False)
        rendered_params = template.render_complex(self._params)

        async with async_timeout.timeout(self._timeout):
            req = await websession.get(
                self._state_resource,
                auth=self._auth,
                headers=rendered_headers,
                params=rendered_params,
            )
            text = await req.text()

        if self._is_on_template is not None:
            text = self._is_on_template.async_render_with_possible_json_value(
                text, "None"
            )
            text = text.lower()
            if text == "true":
                self._state = True
            elif text == "false":
                self._state = False
            else:
                self._state = None
        else:
            if text == self._body_on.template:
                self._state = True
            elif text == self._body_off.template:
                self._state = False
            else:
                self._state = None

        return req
