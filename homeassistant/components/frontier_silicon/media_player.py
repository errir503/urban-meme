"""Support for Frontier Silicon Devices (Medion, Hama, Auna,...)."""
from __future__ import annotations

import logging

from afsapi import AFSAPI, ConnectionError as FSConnectionError, PlayState
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
    STATE_OPENING,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DEFAULT_PIN, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_PASSWORD, default=DEFAULT_PIN): cv.string,
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
        webfsapi_url = await AFSAPI.get_webfsapi_endpoint(
            discovery_info["ssdp_description"]
        )
        afsapi = AFSAPI(webfsapi_url, DEFAULT_PIN)

        name = await afsapi.get_friendly_name()
        async_add_entities(
            [AFSAPIDevice(name, afsapi)],
            True,
        )
        return

    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    password = config.get(CONF_PASSWORD)
    name = config.get(CONF_NAME)

    try:
        webfsapi_url = await AFSAPI.get_webfsapi_endpoint(
            f"http://{host}:{port}/device"
        )
        afsapi = AFSAPI(webfsapi_url, password)
        async_add_entities([AFSAPIDevice(name, afsapi)], True)
    except FSConnectionError:
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

    def __init__(self, name: str | None, afsapi: AFSAPI) -> None:
        """Initialize the Frontier Silicon API device."""
        self.fs_device = afsapi

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, afsapi.webfsapi_endpoint)},
            name=name,
        )

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

        self.__modes_by_label = None

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
        afsapi = self.fs_device
        try:
            if await afsapi.get_power():
                status = await afsapi.get_play_status()
                self._state = {
                    PlayState.PLAYING: STATE_PLAYING,
                    PlayState.PAUSED: STATE_PAUSED,
                    PlayState.STOPPED: STATE_IDLE,
                    PlayState.LOADING: STATE_OPENING,
                    None: STATE_IDLE,
                }.get(status, STATE_UNKNOWN)
            else:
                self._state = STATE_OFF
        except FSConnectionError:
            if self._attr_available:
                _LOGGER.warning(
                    "Could not connect to %s. Did it go offline?",
                    self._name or afsapi.webfsapi_endpoint,
                )
                self._state = STATE_UNAVAILABLE
                self._attr_available = False
        else:
            if not self._attr_available:
                _LOGGER.info(
                    "Reconnected to %s",
                    self._name or afsapi.webfsapi_endpoint,
                )

                self._attr_available = True
            if not self._name:
                self._name = await afsapi.get_friendly_name()

            if not self._source_list:
                self.__modes_by_label = {
                    mode.label: mode.key for mode in await afsapi.get_modes()
                }
                self._source_list = list(self.__modes_by_label.keys())

            # The API seems to include 'zero' in the number of steps (e.g. if the range is
            # 0-40 then get_volume_steps returns 41) subtract one to get the max volume.
            # If call to get_volume fails set to 0 and try again next time.
            if not self._max_volume:
                self._max_volume = int(await afsapi.get_volume_steps() or 1) - 1

        if self._state not in [STATE_OFF, STATE_UNAVAILABLE]:
            info_name = await afsapi.get_play_name()
            info_text = await afsapi.get_play_text()

            self._title = " - ".join(filter(None, [info_name, info_text]))
            self._artist = await afsapi.get_play_artist()
            self._album_name = await afsapi.get_play_album()

            self._source = (await afsapi.get_mode()).label
            self._mute = await afsapi.get_mute()
            self._media_image_url = await afsapi.get_play_graphic()

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
        await self.fs_device.set_power(True)
        await self.fs_device.set_mode(self.__modes_by_label.get(source))
