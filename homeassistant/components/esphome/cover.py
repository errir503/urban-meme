"""Support for ESPHome covers."""
from __future__ import annotations

from typing import Any

from aioesphomeapi import APIVersion, CoverInfo, CoverOperation, CoverState, EntityInfo

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.enum import try_parse_enum

from .entity import EsphomeEntity, esphome_state_property, platform_async_setup_entry


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up ESPHome covers based on a config entry."""
    await platform_async_setup_entry(
        hass,
        entry,
        async_add_entities,
        info_type=CoverInfo,
        entity_type=EsphomeCover,
        state_type=CoverState,
    )


class EsphomeCover(EsphomeEntity[CoverInfo, CoverState], CoverEntity):
    """A cover implementation for ESPHome."""

    @callback
    def _on_static_info_update(self, static_info: EntityInfo) -> None:
        """Set attrs from static info."""
        super()._on_static_info_update(static_info)
        static_info = self._static_info
        flags = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        if self._api_version < APIVersion(1, 8) or static_info.supports_stop:
            flags |= CoverEntityFeature.STOP
        if static_info.supports_position:
            flags |= CoverEntityFeature.SET_POSITION
        if static_info.supports_tilt:
            flags |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.SET_TILT_POSITION
            )
        self._attr_supported_features = flags
        self._attr_device_class = try_parse_enum(
            CoverDeviceClass, static_info.device_class
        )
        self._attr_assumed_state = static_info.assumed_state

    @property
    @esphome_state_property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed or not."""
        # Check closed state with api version due to a protocol change
        return self._state.is_closed(self._api_version)

    @property
    @esphome_state_property
    def is_opening(self) -> bool:
        """Return if the cover is opening or not."""
        return self._state.current_operation == CoverOperation.IS_OPENING

    @property
    @esphome_state_property
    def is_closing(self) -> bool:
        """Return if the cover is closing or not."""
        return self._state.current_operation == CoverOperation.IS_CLOSING

    @property
    @esphome_state_property
    def current_cover_position(self) -> int | None:
        """Return current position of cover. 0 is closed, 100 is open."""
        if not self._static_info.supports_position:
            return None
        return round(self._state.position * 100.0)

    @property
    @esphome_state_property
    def current_cover_tilt_position(self) -> int | None:
        """Return current position of cover tilt. 0 is closed, 100 is open."""
        if not self._static_info.supports_tilt:
            return None
        return round(self._state.tilt * 100.0)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self._client.cover_command(key=self._key, position=1.0)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        await self._client.cover_command(key=self._key, position=0.0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self._client.cover_command(key=self._key, stop=True)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        await self._client.cover_command(
            key=self._key, position=kwargs[ATTR_POSITION] / 100
        )

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        """Open the cover tilt."""
        await self._client.cover_command(key=self._key, tilt=1.0)

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        """Close the cover tilt."""
        await self._client.cover_command(key=self._key, tilt=0.0)

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        """Move the cover tilt to a specific position."""
        tilt_position: int = kwargs[ATTR_TILT_POSITION]
        await self._client.cover_command(key=self._key, tilt=tilt_position / 100)
