"""Support for displaying collected data over SNMP."""
from __future__ import annotations

from datetime import timedelta
import logging
import sys

import voluptuous as vol

from homeassistant.components.sensor import CONF_STATE_CLASS, PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_HOST,
    CONF_ICON,
    CONF_NAME,
    CONF_PORT,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_USERNAME,
    CONF_VALUE_TEMPLATE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.template import Template
from homeassistant.helpers.trigger_template_entity import (
    CONF_AVAILABILITY,
    CONF_PICTURE,
    TEMPLATE_SENSOR_BASE_SCHEMA,
    ManualTriggerSensorEntity,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    CONF_ACCEPT_ERRORS,
    CONF_AUTH_KEY,
    CONF_AUTH_PROTOCOL,
    CONF_BASEOID,
    CONF_COMMUNITY,
    CONF_DEFAULT_VALUE,
    CONF_PRIV_KEY,
    CONF_PRIV_PROTOCOL,
    CONF_VERSION,
    DEFAULT_AUTH_PROTOCOL,
    DEFAULT_COMMUNITY,
    DEFAULT_HOST,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_PRIV_PROTOCOL,
    DEFAULT_TIMEOUT,
    DEFAULT_VERSION,
    MAP_AUTH_PROTOCOLS,
    MAP_PRIV_PROTOCOLS,
    SNMP_VERSIONS,
)

if sys.version_info < (3, 12):
    from pysnmp.error import PySnmpError
    import pysnmp.hlapi.asyncio as hlapi
    from pysnmp.hlapi.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        Udp6TransportTarget,
        UdpTransportTarget,
        UsmUserData,
        getCmd,
    )

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=10)

TRIGGER_ENTITY_OPTIONS = (
    CONF_AVAILABILITY,
    CONF_DEVICE_CLASS,
    CONF_ICON,
    CONF_PICTURE,
    CONF_UNIQUE_ID,
    CONF_STATE_CLASS,
    CONF_UNIT_OF_MEASUREMENT,
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_BASEOID): cv.string,
        vol.Optional(CONF_ACCEPT_ERRORS, default=False): cv.boolean,
        vol.Optional(CONF_COMMUNITY, default=DEFAULT_COMMUNITY): cv.string,
        vol.Optional(CONF_DEFAULT_VALUE): cv.string,
        vol.Optional(CONF_HOST, default=DEFAULT_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
        vol.Optional(CONF_VERSION, default=DEFAULT_VERSION): vol.In(SNMP_VERSIONS),
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_AUTH_KEY): cv.string,
        vol.Optional(CONF_AUTH_PROTOCOL, default=DEFAULT_AUTH_PROTOCOL): vol.In(
            MAP_AUTH_PROTOCOLS
        ),
        vol.Optional(CONF_PRIV_KEY): cv.string,
        vol.Optional(CONF_PRIV_PROTOCOL, default=DEFAULT_PRIV_PROTOCOL): vol.In(
            MAP_PRIV_PROTOCOLS
        ),
    }
).extend(TEMPLATE_SENSOR_BASE_SCHEMA.schema)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the SNMP sensor."""
    if sys.version_info >= (3, 12):
        raise HomeAssistantError(
            "SNMP is not supported on Python 3.12. Please use Python 3.11."
        )
    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    community = config.get(CONF_COMMUNITY)
    baseoid = config.get(CONF_BASEOID)
    version = config[CONF_VERSION]
    username = config.get(CONF_USERNAME)
    authkey = config.get(CONF_AUTH_KEY)
    authproto = config[CONF_AUTH_PROTOCOL]
    privkey = config.get(CONF_PRIV_KEY)
    privproto = config[CONF_PRIV_PROTOCOL]
    accept_errors = config.get(CONF_ACCEPT_ERRORS)
    default_value = config.get(CONF_DEFAULT_VALUE)

    try:
        # Try IPv4 first.
        target = UdpTransportTarget((host, port), timeout=DEFAULT_TIMEOUT)
    except PySnmpError:
        # Then try IPv6.
        try:
            target = Udp6TransportTarget((host, port), timeout=DEFAULT_TIMEOUT)
        except PySnmpError as err:
            _LOGGER.error("Invalid SNMP host: %s", err)
            return

    if version == "3":
        if not authkey:
            authproto = "none"
        if not privkey:
            privproto = "none"

        request_args = [
            SnmpEngine(),
            UsmUserData(
                username,
                authKey=authkey or None,
                privKey=privkey or None,
                authProtocol=getattr(hlapi, MAP_AUTH_PROTOCOLS[authproto]),
                privProtocol=getattr(hlapi, MAP_PRIV_PROTOCOLS[privproto]),
            ),
            target,
            ContextData(),
        ]
    else:
        request_args = [
            SnmpEngine(),
            CommunityData(community, mpModel=SNMP_VERSIONS[version]),
            target,
            ContextData(),
        ]
    get_result = await getCmd(*request_args, ObjectType(ObjectIdentity(baseoid)))
    errindication, _, _, _ = get_result

    if errindication and not accept_errors:
        _LOGGER.error("Please check the details in the configuration file")
        return

    name = config.get(CONF_NAME, Template(DEFAULT_NAME, hass))
    trigger_entity_config = {CONF_NAME: name}
    for key in TRIGGER_ENTITY_OPTIONS:
        if key not in config:
            continue
        trigger_entity_config[key] = config[key]

    value_template: Template | None = config.get(CONF_VALUE_TEMPLATE)
    if value_template is not None:
        value_template.hass = hass

    data = SnmpData(request_args, baseoid, accept_errors, default_value)
    async_add_entities([SnmpSensor(hass, data, trigger_entity_config, value_template)])


class SnmpSensor(ManualTriggerSensorEntity):
    """Representation of a SNMP sensor."""

    _attr_should_poll = True

    def __init__(
        self,
        hass: HomeAssistant,
        data: SnmpData,
        config: ConfigType,
        value_template: Template | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(hass, config)
        self.data = data
        self._state = None
        self._value_template = value_template

    async def async_added_to_hass(self) -> None:
        """Handle adding to Home Assistant."""
        await super().async_added_to_hass()
        await self.async_update()

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        await self.data.async_update()

        raw_value = self.data.value

        if (value := self.data.value) is None:
            value = STATE_UNKNOWN
        elif self._value_template is not None:
            value = self._value_template.async_render_with_possible_json_value(
                value, STATE_UNKNOWN
            )

        self._attr_native_value = value
        self._process_manual_data(raw_value)


class SnmpData:
    """Get the latest data and update the states."""

    def __init__(self, request_args, baseoid, accept_errors, default_value) -> None:
        """Initialize the data object."""
        self._request_args = request_args
        self._baseoid = baseoid
        self._accept_errors = accept_errors
        self._default_value = default_value
        self.value = None

    async def async_update(self):
        """Get the latest data from the remote SNMP capable host."""

        get_result = await getCmd(
            *self._request_args, ObjectType(ObjectIdentity(self._baseoid))
        )
        errindication, errstatus, errindex, restable = get_result

        if errindication and not self._accept_errors:
            _LOGGER.error("SNMP error: %s", errindication)
        elif errstatus and not self._accept_errors:
            _LOGGER.error(
                "SNMP error: %s at %s",
                errstatus.prettyPrint(),
                errindex and restable[-1][int(errindex) - 1] or "?",
            )
        elif (errindication or errstatus) and self._accept_errors:
            self.value = self._default_value
        else:
            for resrow in restable:
                self.value = resrow[-1].prettyPrint()
