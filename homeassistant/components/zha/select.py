"""Support for ZHA controls using the select platform."""
from __future__ import annotations

from enum import Enum
import functools
import logging

from zigpy.zcl.clusters.general import OnOff
from zigpy.zcl.clusters.security import IasWd

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .core import discovery
from .core.const import (
    CHANNEL_IAS_WD,
    CHANNEL_ON_OFF,
    DATA_ZHA,
    SIGNAL_ADD_ENTITIES,
    Strobe,
)
from .core.registries import ZHA_ENTITIES
from .core.typing import ChannelType, ZhaDeviceType
from .entity import ZhaEntity

CONFIG_DIAGNOSTIC_MATCH = functools.partial(
    ZHA_ENTITIES.config_diagnostic_match, Platform.SELECT
)
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Zigbee Home Automation siren from config entry."""
    entities_to_create = hass.data[DATA_ZHA][Platform.SELECT]

    unsub = async_dispatcher_connect(
        hass,
        SIGNAL_ADD_ENTITIES,
        functools.partial(
            discovery.async_add_entities,
            async_add_entities,
            entities_to_create,
        ),
    )
    config_entry.async_on_unload(unsub)


class ZHAEnumSelectEntity(ZhaEntity, SelectEntity):
    """Representation of a ZHA select entity."""

    _attr_entity_category = EntityCategory.CONFIG
    _enum: Enum = None

    def __init__(
        self,
        unique_id: str,
        zha_device: ZhaDeviceType,
        channels: list[ChannelType],
        **kwargs,
    ) -> None:
        """Init this select entity."""
        self._attr_name = self._enum.__name__
        self._attr_options = [entry.name.replace("_", " ") for entry in self._enum]
        self._channel: ChannelType = channels[0]
        super().__init__(unique_id, zha_device, channels, **kwargs)

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        option = self._channel.data_cache.get(self._attr_name)
        if option is None:
            return None
        return option.name.replace("_", " ")

    async def async_select_option(self, option: str | int) -> None:
        """Change the selected option."""
        self._channel.data_cache[self._attr_name] = self._enum[option.replace(" ", "_")]
        self.async_write_ha_state()

    @callback
    def async_restore_last_state(self, last_state) -> None:
        """Restore previous state."""
        if last_state.state and last_state.state != STATE_UNKNOWN:
            self._channel.data_cache[self._attr_name] = self._enum[
                last_state.state.replace(" ", "_")
            ]


class ZHANonZCLSelectEntity(ZHAEnumSelectEntity):
    """Representation of a ZHA select entity with no ZCL interaction."""

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return True


@CONFIG_DIAGNOSTIC_MATCH(channel_names=CHANNEL_IAS_WD)
class ZHADefaultToneSelectEntity(
    ZHANonZCLSelectEntity, id_suffix=IasWd.Warning.WarningMode.__name__
):
    """Representation of a ZHA default siren tone select entity."""

    _enum: Enum = IasWd.Warning.WarningMode


@CONFIG_DIAGNOSTIC_MATCH(channel_names=CHANNEL_IAS_WD)
class ZHADefaultSirenLevelSelectEntity(
    ZHANonZCLSelectEntity, id_suffix=IasWd.Warning.SirenLevel.__name__
):
    """Representation of a ZHA default siren level select entity."""

    _enum: Enum = IasWd.Warning.SirenLevel


@CONFIG_DIAGNOSTIC_MATCH(channel_names=CHANNEL_IAS_WD)
class ZHADefaultStrobeLevelSelectEntity(
    ZHANonZCLSelectEntity, id_suffix=IasWd.StrobeLevel.__name__
):
    """Representation of a ZHA default siren strobe level select entity."""

    _enum: Enum = IasWd.StrobeLevel


@CONFIG_DIAGNOSTIC_MATCH(channel_names=CHANNEL_IAS_WD)
class ZHADefaultStrobeSelectEntity(ZHANonZCLSelectEntity, id_suffix=Strobe.__name__):
    """Representation of a ZHA default siren strobe select entity."""

    _enum: Enum = Strobe


class ZCLEnumSelectEntity(ZhaEntity, SelectEntity):
    """Representation of a ZHA ZCL enum select entity."""

    _select_attr: str
    _attr_entity_category = EntityCategory.CONFIG
    _enum: Enum

    @classmethod
    def create_entity(
        cls,
        unique_id: str,
        zha_device: ZhaDeviceType,
        channels: list[ChannelType],
        **kwargs,
    ) -> ZhaEntity | None:
        """Entity Factory.

        Return entity if it is a supported configuration, otherwise return None
        """
        channel = channels[0]
        if (
            cls._select_attr in channel.cluster.unsupported_attributes
            or channel.cluster.get(cls._select_attr) is None
        ):
            _LOGGER.debug(
                "%s is not supported - skipping %s entity creation",
                cls._select_attr,
                cls.__name__,
            )
            return None

        return cls(unique_id, zha_device, channels, **kwargs)

    def __init__(
        self,
        unique_id: str,
        zha_device: ZhaDeviceType,
        channels: list[ChannelType],
        **kwargs,
    ) -> None:
        """Init this select entity."""
        self._attr_options = [entry.name.replace("_", " ") for entry in self._enum]
        self._channel: ChannelType = channels[0]
        super().__init__(unique_id, zha_device, channels, **kwargs)

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        option = self._channel.cluster.get(self._select_attr)
        if option is None:
            return None
        option = self._enum(option)
        return option.name.replace("_", " ")

    async def async_select_option(self, option: str | int) -> None:
        """Change the selected option."""
        await self._channel.cluster.write_attributes(
            {self._select_attr: self._enum[option.replace(" ", "_")]}
        )
        self.async_write_ha_state()


@CONFIG_DIAGNOSTIC_MATCH(channel_names=CHANNEL_ON_OFF)
class ZHAStartupOnOffSelectEntity(
    ZCLEnumSelectEntity, id_suffix=OnOff.StartUpOnOff.__name__
):
    """Representation of a ZHA startup onoff select entity."""

    _select_attr = "start_up_on_off"
    _enum: Enum = OnOff.StartUpOnOff
