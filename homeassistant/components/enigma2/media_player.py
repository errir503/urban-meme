"""Support for Enigma2 media players."""
from __future__ import annotations

from openwebif.api import CreateDevice
import voluptuous as vol

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

ATTR_MEDIA_CURRENTLY_RECORDING = "media_currently_recording"
ATTR_MEDIA_DESCRIPTION = "media_description"
ATTR_MEDIA_END_TIME = "media_end_time"
ATTR_MEDIA_START_TIME = "media_start_time"

CONF_USE_CHANNEL_ICON = "use_channel_icon"
CONF_DEEP_STANDBY = "deep_standby"
CONF_MAC_ADDRESS = "mac_address"
CONF_SOURCE_BOUQUET = "source_bouquet"

DEFAULT_NAME = "Enigma2 Media Player"
DEFAULT_PORT = 80
DEFAULT_SSL = False
DEFAULT_USE_CHANNEL_ICON = False
DEFAULT_USERNAME = "root"
DEFAULT_PASSWORD = "dreambox"
DEFAULT_DEEP_STANDBY = False
DEFAULT_MAC_ADDRESS = ""
DEFAULT_SOURCE_BOUQUET = ""

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): cv.string,
        vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
        vol.Optional(
            CONF_USE_CHANNEL_ICON, default=DEFAULT_USE_CHANNEL_ICON
        ): cv.boolean,
        vol.Optional(CONF_DEEP_STANDBY, default=DEFAULT_DEEP_STANDBY): cv.boolean,
        vol.Optional(CONF_MAC_ADDRESS, default=DEFAULT_MAC_ADDRESS): cv.string,
        vol.Optional(CONF_SOURCE_BOUQUET, default=DEFAULT_SOURCE_BOUQUET): cv.string,
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_devices: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up of an enigma2 media player."""
    if discovery_info:
        # Discovery gives us the streaming service port (8001)
        # which is not useful as OpenWebif never runs on that port.
        # So use the default port instead.
        config[CONF_PORT] = DEFAULT_PORT
        config[CONF_NAME] = discovery_info["hostname"]
        config[CONF_HOST] = discovery_info["host"]
        config[CONF_USERNAME] = DEFAULT_USERNAME
        config[CONF_PASSWORD] = DEFAULT_PASSWORD
        config[CONF_SSL] = DEFAULT_SSL
        config[CONF_USE_CHANNEL_ICON] = DEFAULT_USE_CHANNEL_ICON
        config[CONF_MAC_ADDRESS] = DEFAULT_MAC_ADDRESS
        config[CONF_DEEP_STANDBY] = DEFAULT_DEEP_STANDBY
        config[CONF_SOURCE_BOUQUET] = DEFAULT_SOURCE_BOUQUET

    device = CreateDevice(
        host=config[CONF_HOST],
        port=config.get(CONF_PORT),
        username=config.get(CONF_USERNAME),
        password=config.get(CONF_PASSWORD),
        is_https=config[CONF_SSL],
        prefer_picon=config.get(CONF_USE_CHANNEL_ICON),
        mac_address=config.get(CONF_MAC_ADDRESS),
        turn_off_to_deep=config.get(CONF_DEEP_STANDBY),
        source_bouquet=config.get(CONF_SOURCE_BOUQUET),
    )

    add_devices([Enigma2Device(config[CONF_NAME], device)], True)


class Enigma2Device(MediaPlayerEntity):
    """Representation of an Enigma2 box."""

    _attr_media_content_type = MediaType.TVSHOW
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, name, device):
        """Initialize the Enigma2 device."""
        self._name = name
        self.e2_box = device

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID for this entity."""
        return self.e2_box.mac_address

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the device."""
        if self.e2_box.is_recording_playback:
            return MediaPlayerState.PLAYING
        return MediaPlayerState.OFF if self.e2_box.in_standby else MediaPlayerState.ON

    @property
    def available(self) -> bool:
        """Return True if the device is available."""
        return not self.e2_box.is_offline

    def turn_off(self) -> None:
        """Turn off media player."""
        self.e2_box.turn_off()

    def turn_on(self) -> None:
        """Turn the media player on."""
        self.e2_box.turn_on()

    @property
    def media_title(self):
        """Title of current playing media."""
        return self.e2_box.current_service_channel_name

    @property
    def media_series_title(self):
        """Return the title of current episode of TV show."""
        return self.e2_box.current_programme_name

    @property
    def media_channel(self):
        """Channel of current playing media."""
        return self.e2_box.current_service_channel_name

    @property
    def media_content_id(self):
        """Service Ref of current playing media."""
        return self.e2_box.current_service_ref

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self.e2_box.muted

    @property
    def media_image_url(self):
        """Picon url for the channel."""
        return self.e2_box.picon_url

    def set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        self.e2_box.set_volume(int(volume * 100))

    def volume_up(self) -> None:
        """Volume up the media player."""
        self.e2_box.set_volume(int(self.e2_box.volume * 100) + 5)

    def volume_down(self) -> None:
        """Volume down media player."""
        self.e2_box.set_volume(int(self.e2_box.volume * 100) - 5)

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self.e2_box.volume

    def media_stop(self) -> None:
        """Send stop command."""
        self.e2_box.set_stop()

    def media_play(self) -> None:
        """Play media."""
        self.e2_box.toggle_play_pause()

    def media_pause(self) -> None:
        """Pause the media player."""
        self.e2_box.toggle_play_pause()

    def media_next_track(self) -> None:
        """Send next track command."""
        self.e2_box.set_channel_up()

    def media_previous_track(self) -> None:
        """Send next track command."""
        self.e2_box.set_channel_down()

    def mute_volume(self, mute: bool) -> None:
        """Mute or unmute."""
        self.e2_box.mute_volume()

    @property
    def source(self):
        """Return the current input source."""
        return self.e2_box.current_service_channel_name

    @property
    def source_list(self):
        """List of available input sources."""
        return self.e2_box.source_list

    def select_source(self, source: str) -> None:
        """Select input source."""
        self.e2_box.select_source(self.e2_box.sources[source])

    def update(self) -> None:
        """Update state of the media_player."""
        self.e2_box.update()

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes.

        isRecording:        Is the box currently recording.
        currservice_fulldescription: Full program description.
        currservice_begin:  is in the format '21:00'.
        currservice_end:    is in the format '21:00'.
        """
        if self.e2_box.in_standby:
            return {}
        return {
            ATTR_MEDIA_CURRENTLY_RECORDING: self.e2_box.status_info["isRecording"],
            ATTR_MEDIA_DESCRIPTION: self.e2_box.status_info[
                "currservice_fulldescription"
            ],
            ATTR_MEDIA_START_TIME: self.e2_box.status_info["currservice_begin"],
            ATTR_MEDIA_END_TIME: self.e2_box.status_info["currservice_end"],
        }
