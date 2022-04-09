"""Dune HD implementation of the media player."""
from __future__ import annotations

from typing import Any, Final

from pdunehd import DuneHDPlayer
import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA as PARENT_PLATFORM_SCHEMA,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_PAUSED,
    STATE_PLAYING,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import ATTR_MANUFACTURER, DEFAULT_NAME, DOMAIN

CONF_SOURCES: Final = "sources"

PLATFORM_SCHEMA: Final = PARENT_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_SOURCES): vol.Schema({cv.string: cv.string}),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)

DUNEHD_PLAYER_SUPPORT: Final[int] = (
    MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PLAY
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Dune HD media player platform."""
    host: str = config[CONF_HOST]

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_HOST: host}
        )
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Dune HD entities from a config_entry."""
    unique_id = entry.entry_id

    player: str = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([DuneHDPlayerEntity(player, DEFAULT_NAME, unique_id)], True)


class DuneHDPlayerEntity(MediaPlayerEntity):
    """Implementation of the Dune HD player."""

    def __init__(self, player: DuneHDPlayer, name: str, unique_id: str) -> None:
        """Initialize entity to control Dune HD."""
        self._player = player
        self._name = name
        self._media_title: str | None = None
        self._state: dict[str, Any] = {}
        self._unique_id = unique_id

    def update(self) -> None:
        """Update internal status of the entity."""
        self._state = self._player.update_state()
        self.__update_title()

    @property
    def state(self) -> str | None:
        """Return player state."""
        state = STATE_OFF
        if "playback_position" in self._state:
            state = STATE_PLAYING
        if self._state.get("player_state") in ("playing", "buffering", "photo_viewer"):
            state = STATE_PLAYING
        if int(self._state.get("playback_speed", 1234)) == 0:
            state = STATE_PAUSED
        if self._state.get("player_state") == "navigator":
            state = STATE_ON
        return state

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return len(self._state) > 0

    @property
    def unique_id(self) -> str:
        """Return a unique_id for this entity."""
        return self._unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._unique_id)},
            manufacturer=ATTR_MANUFACTURER,
            name=DEFAULT_NAME,
        )

    @property
    def volume_level(self) -> float:
        """Return the volume level of the media player (0..1)."""
        return int(self._state.get("playback_volume", 0)) / 100

    @property
    def is_volume_muted(self) -> bool:
        """Return a boolean if volume is currently muted."""
        return int(self._state.get("playback_mute", 0)) == 1

    @property
    def supported_features(self) -> int:
        """Flag media player features that are supported."""
        return DUNEHD_PLAYER_SUPPORT

    def volume_up(self) -> None:
        """Volume up media player."""
        self._state = self._player.volume_up()

    def volume_down(self) -> None:
        """Volume down media player."""
        self._state = self._player.volume_down()

    def mute_volume(self, mute: bool) -> None:
        """Mute/unmute player volume."""
        self._state = self._player.mute(mute)

    def turn_off(self) -> None:
        """Turn off media player."""
        self._media_title = None
        self._state = self._player.turn_off()

    def turn_on(self) -> None:
        """Turn off media player."""
        self._state = self._player.turn_on()

    def media_play(self) -> None:
        """Play media player."""
        self._state = self._player.play()

    def media_pause(self) -> None:
        """Pause media player."""
        self._state = self._player.pause()

    @property
    def media_title(self) -> str | None:
        """Return the current media source."""
        self.__update_title()
        if self._media_title:
            return self._media_title
        return None

    def __update_title(self) -> None:
        if self._state.get("player_state") == "bluray_playback":
            self._media_title = "Blu-Ray"
        elif self._state.get("player_state") == "photo_viewer":
            self._media_title = "Photo Viewer"
        elif self._state.get("playback_url"):
            self._media_title = self._state["playback_url"].split("/")[-1]
        else:
            self._media_title = None

    def media_previous_track(self) -> None:
        """Send previous track command."""
        self._state = self._player.previous_track()

    def media_next_track(self) -> None:
        """Send next track command."""
        self._state = self._player.next_track()
