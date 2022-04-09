"""Support for Frontier Silicon Devices (Medion, Hama, Auna,...)."""
from __future__ import annotations

import logging

from afsapi import AFSAPI
import requests
import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.components.media_player.const import MEDIA_TYPE_MUSIC
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    STATE_IDLE,
    STATE_OFF,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 80
DEFAULT_PASSWORD = "1234"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): cv.string,
        vol.Optional(CONF_NAME): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Frontier Silicon platform."""
    if discovery_info is not None:
        async_add_entities(
            [AFSAPIDevice(discovery_info["ssdp_description"], DEFAULT_PASSWORD, None)],
            True,
        )
        return

    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    password = config.get(CONF_PASSWORD)
    name = config.get(CONF_NAME)

    try:
        async_add_entities(
            [AFSAPIDevice(f"http://{host}:{port}/device", password, name)], True
        )
        _LOGGER.debug("FSAPI device %s:%s -> %s", host, port, password)
    except requests.exceptions.RequestException:
        _LOGGER.error(
            "Could not add the FSAPI device at %s:%s -> %s", host, port, password
        )


class AFSAPIDevice(MediaPlayerEntity):
    """Representation of a Frontier Silicon device on the network."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.SEEK
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, device_url, password, name):
        """Initialize the Frontier Silicon API device."""
        self._device_url = device_url
        self._password = password
        self._state = None

        self._name = name
        self._title = None
        self._artist = None
        self._album_name = None
        self._mute = None
        self._source = None
        self._source_list = None
        self._media_image_url = None
        self._max_volume = None
        self._volume_level = None

    # Properties
    @property
    def fs_device(self):
        """
        Create a fresh fsapi session.

        A new session is created for each request in case someone else
        connected to the device in between the updates and invalidated the
        existing session (i.e UNDOK).
        """
        return AFSAPI(self._device_url, self._password)

    @property
    def name(self):
        """Return the device name."""
        return self._name

    @property
    def media_title(self):
        """Title of current playing media."""
        return self._title

    @property
    def media_artist(self):
        """Artist of current playing media, music track only."""
        return self._artist

    @property
    def media_album_name(self):
        """Album name of current playing media, music track only."""
        return self._album_name

    @property
    def media_content_type(self):
        """Content type of current playing media."""
        return MEDIA_TYPE_MUSIC

    @property
    def state(self):
        """Return the state of the player."""
        return self._state

    # source
    @property
    def source_list(self):
        """List of available input sources."""
        return self._source_list

    @property
    def source(self):
        """Name of the current input source."""
        return self._source

    @property
    def media_image_url(self):
        """Image url of current playing media."""
        return self._media_image_url

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._volume_level

    async def async_update(self):
        """Get the latest date and update device state."""
        fs_device = self.fs_device

        if not self._name:
            self._name = await fs_device.get_friendly_name()

        if not self._source_list:
            self._source_list = await fs_device.get_mode_list()

        # The API seems to include 'zero' in the number of steps (e.g. if the range is
        # 0-40 then get_volume_steps returns 41) subtract one to get the max volume.
        # If call to get_volume fails set to 0 and try again next time.
        if not self._max_volume:
            self._max_volume = int(await fs_device.get_volume_steps() or 1) - 1

        if await fs_device.get_power():
            status = await fs_device.get_play_status()
            self._state = {
                "playing": STATE_PLAYING,
                "paused": STATE_PAUSED,
                "stopped": STATE_IDLE,
                "unknown": STATE_UNKNOWN,
                None: STATE_IDLE,
            }.get(status, STATE_UNKNOWN)
        else:
            self._state = STATE_OFF

        if self._state != STATE_OFF:
            info_name = await fs_device.get_play_name()
            info_text = await fs_device.get_play_text()

            self._title = " - ".join(filter(None, [info_name, info_text]))
            self._artist = await fs_device.get_play_artist()
            self._album_name = await fs_device.get_play_album()

            self._source = await fs_device.get_mode()
            self._mute = await fs_device.get_mute()
            self._media_image_url = await fs_device.get_play_graphic()

            volume = await self.fs_device.get_volume()

            # Prevent division by zero if max_volume not known yet
            self._volume_level = float(volume or 0) / (self._max_volume or 1)
        else:
            self._title = None
            self._artist = None
            self._album_name = None

            self._source = None
            self._mute = None
            self._media_image_url = None

            self._volume_level = None

    # Management actions
    # power control
    async def async_turn_on(self):
        """Turn on the device."""
        await self.fs_device.set_power(True)

    async def async_turn_off(self):
        """Turn off the device."""
        await self.fs_device.set_power(False)

    async def async_media_play(self):
        """Send play command."""
        await self.fs_device.play()

    async def async_media_pause(self):
        """Send pause command."""
        await self.fs_device.pause()

    async def async_media_play_pause(self):
        """Send play/pause command."""
        if "playing" in self._state:
            await self.fs_device.pause()
        else:
            await self.fs_device.play()

    async def async_media_stop(self):
        """Send play/pause command."""
        await self.fs_device.pause()

    async def async_media_previous_track(self):
        """Send previous track command (results in rewind)."""
        await self.fs_device.rewind()

    async def async_media_next_track(self):
        """Send next track command (results in fast-forward)."""
        await self.fs_device.forward()

    # mute
    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._mute

    async def async_mute_volume(self, mute):
        """Send mute command."""
        await self.fs_device.set_mute(mute)

    # volume
    async def async_volume_up(self):
        """Send volume up command."""
        volume = await self.fs_device.get_volume()
        volume = int(volume or 0) + 1
        await self.fs_device.set_volume(min(volume, self._max_volume))

    async def async_volume_down(self):
        """Send volume down command."""
        volume = await self.fs_device.get_volume()
        volume = int(volume or 0) - 1
        await self.fs_device.set_volume(max(volume, 0))

    async def async_set_volume_level(self, volume):
        """Set volume command."""
        if self._max_volume:  # Can't do anything sensible if not set
            volume = int(volume * self._max_volume)
            await self.fs_device.set_volume(volume)

    async def async_select_source(self, source):
        """Select input source."""
        await self.fs_device.set_mode(source)
