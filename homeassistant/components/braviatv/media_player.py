"""Media player support for Bravia TV integration."""
from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import BraviaTVEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia TV Media Player from a config_entry."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    unique_id = config_entry.unique_id
    assert unique_id is not None

    async_add_entities(
        [BraviaTVMediaPlayer(coordinator, unique_id, config_entry.title)]
    )


class BraviaTVMediaPlayer(BraviaTVEntity, MediaPlayerEntity):
    """Representation of a Bravia TV Media Player."""

    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_supported_features = (
        MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.STOP
    )

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the device."""
        if self.coordinator.is_on:
            return (
                MediaPlayerState.PLAYING
                if self.coordinator.playing
                else MediaPlayerState.PAUSED
            )
        return MediaPlayerState.OFF

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        return self.coordinator.source

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        return self.coordinator.source_list

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        return self.coordinator.volume_level

    @property
    def is_volume_muted(self) -> bool:
        """Boolean if volume is currently muted."""
        return self.coordinator.volume_muted

    @property
    def media_title(self) -> str | None:
        """Title of current playing media."""
        return self.coordinator.media_title

    @property
    def media_content_id(self) -> str | None:
        """Content ID of current playing media."""
        return self.coordinator.media_content_id

    @property
    def media_content_type(self) -> MediaType | None:
        """Content type of current playing media."""
        return self.coordinator.media_content_type

    @property
    def media_duration(self) -> int | None:
        """Duration of current playing media in seconds."""
        return self.coordinator.media_duration

    async def async_turn_on(self) -> None:
        """Turn the device on."""
        await self.coordinator.async_turn_on()

    async def async_turn_off(self) -> None:
        """Turn the device off."""
        await self.coordinator.async_turn_off()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self.coordinator.async_set_volume_level(volume)

    async def async_volume_up(self) -> None:
        """Send volume up command."""
        await self.coordinator.async_volume_up()

    async def async_volume_down(self) -> None:
        """Send volume down command."""
        await self.coordinator.async_volume_down()

    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute command."""
        await self.coordinator.async_volume_mute(mute)

    async def async_select_source(self, source: str) -> None:
        """Set the input source."""
        await self.coordinator.async_select_source(source)

    async def async_media_play(self) -> None:
        """Send play command."""
        await self.coordinator.async_media_play()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self.coordinator.async_media_pause()

    async def async_media_stop(self) -> None:
        """Send media stop command to media player."""
        await self.coordinator.async_media_stop()

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self.coordinator.async_media_next_track()

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        await self.coordinator.async_media_previous_track()
