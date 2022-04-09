"""Arcam media player."""
import logging

from arcam.fmj import SourceCodes
from arcam.fmj.state import State

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.components.media_player.const import (
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_MUSIC,
    MEDIA_TYPE_MUSIC,
)
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .config_flow import get_entry_client
from .const import (
    DOMAIN,
    EVENT_TURN_ON,
    SIGNAL_CLIENT_DATA,
    SIGNAL_CLIENT_STARTED,
    SIGNAL_CLIENT_STOPPED,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the configuration entry."""

    client = get_entry_client(hass, config_entry)

    async_add_entities(
        [
            ArcamFmj(
                config_entry.title,
                State(client, zone),
                config_entry.unique_id or config_entry.entry_id,
            )
            for zone in (1, 2)
        ],
        True,
    )


class ArcamFmj(MediaPlayerEntity):
    """Representation of a media device."""

    _attr_should_poll = False

    def __init__(
        self,
        device_name,
        state: State,
        uuid: str,
    ):
        """Initialize device."""
        self._state = state
        self._device_name = device_name
        self._attr_name = f"{device_name} - Zone: {state.zn}"
        self._uuid = uuid
        self._attr_supported_features = (
            MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.BROWSE_MEDIA
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.TURN_ON
        )
        if state.zn == 1:
            self._attr_supported_features |= MediaPlayerEntityFeature.SELECT_SOUND_MODE
        self._attr_unique_id = f"{uuid}-{state.zn}"
        self._attr_entity_registry_enabled_default = state.zn == 1

    @property
    def state(self):
        """Return the state of the device."""
        if self._state.get_power():
            return STATE_ON
        return STATE_OFF

    @property
    def device_info(self):
        """Return a device description for device registry."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self._uuid),
                (DOMAIN, self._state.client.host, self._state.client.port),
            },
            manufacturer="Arcam",
            model="Arcam FMJ AVR",
            name=self._device_name,
        )

    async def async_added_to_hass(self):
        """Once registered, add listener for events."""
        await self._state.start()
        await self._state.update()

        @callback
        def _data(host):
            if host == self._state.client.host:
                self.async_write_ha_state()

        @callback
        def _started(host):
            if host == self._state.client.host:
                self.async_schedule_update_ha_state(force_refresh=True)

        @callback
        def _stopped(host):
            if host == self._state.client.host:
                self.async_schedule_update_ha_state(force_refresh=True)

        self.async_on_remove(
            self.hass.helpers.dispatcher.async_dispatcher_connect(
                SIGNAL_CLIENT_DATA, _data
            )
        )

        self.async_on_remove(
            self.hass.helpers.dispatcher.async_dispatcher_connect(
                SIGNAL_CLIENT_STARTED, _started
            )
        )

        self.async_on_remove(
            self.hass.helpers.dispatcher.async_dispatcher_connect(
                SIGNAL_CLIENT_STOPPED, _stopped
            )
        )

    async def async_update(self):
        """Force update of state."""
        _LOGGER.debug("Update state %s", self.name)
        await self._state.update()

    async def async_mute_volume(self, mute):
        """Send mute command."""
        await self._state.set_mute(mute)
        self.async_write_ha_state()

    async def async_select_source(self, source):
        """Select a specific source."""
        try:
            value = SourceCodes[source]
        except KeyError:
            _LOGGER.error("Unsupported source %s", source)
            return

        await self._state.set_source(value)
        self.async_write_ha_state()

    async def async_select_sound_mode(self, sound_mode):
        """Select a specific source."""
        try:
            await self._state.set_decode_mode(sound_mode)
        except (KeyError, ValueError):
            _LOGGER.error("Unsupported sound_mode %s", sound_mode)
            return

        self.async_write_ha_state()

    async def async_set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        await self._state.set_volume(round(volume * 99.0))
        self.async_write_ha_state()

    async def async_volume_up(self):
        """Turn volume up for media player."""
        await self._state.inc_volume()
        self.async_write_ha_state()

    async def async_volume_down(self):
        """Turn volume up for media player."""
        await self._state.dec_volume()
        self.async_write_ha_state()

    async def async_turn_on(self):
        """Turn the media player on."""
        if self._state.get_power() is not None:
            _LOGGER.debug("Turning on device using connection")
            await self._state.set_power(True)
        else:
            _LOGGER.debug("Firing event to turn on device")
            self.hass.bus.async_fire(EVENT_TURN_ON, {ATTR_ENTITY_ID: self.entity_id})

    async def async_turn_off(self):
        """Turn the media player off."""
        await self._state.set_power(False)

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        """Implement the websocket media browsing helper."""
        if media_content_id not in (None, "root"):
            raise BrowseError(
                f"Media not found: {media_content_type} / {media_content_id}"
            )

        presets = self._state.get_preset_details()

        radio = [
            BrowseMedia(
                title=preset.name,
                media_class=MEDIA_CLASS_MUSIC,
                media_content_id=f"preset:{preset.index}",
                media_content_type=MEDIA_TYPE_MUSIC,
                can_play=True,
                can_expand=False,
            )
            for preset in presets.values()
        ]

        root = BrowseMedia(
            title="Arcam FMJ Receiver",
            media_class=MEDIA_CLASS_DIRECTORY,
            media_content_id="root",
            media_content_type="library",
            can_play=False,
            can_expand=True,
            children=radio,
        )

        return root

    async def async_play_media(self, media_type: str, media_id: str, **kwargs) -> None:
        """Play media."""

        if media_id.startswith("preset:"):
            preset = int(media_id[7:])
            await self._state.set_tuner_preset(preset)
        else:
            _LOGGER.error("Media %s is not supported", media_id)
            return

    @property
    def source(self):
        """Return the current input source."""
        if (value := self._state.get_source()) is None:
            return None
        return value.name

    @property
    def source_list(self):
        """List of available input sources."""
        return [x.name for x in self._state.get_source_list()]

    @property
    def sound_mode(self):
        """Name of the current sound mode."""
        if (value := self._state.get_decode_mode()) is None:
            return None
        return value.name

    @property
    def sound_mode_list(self):
        """List of available sound modes."""
        if (values := self._state.get_decode_modes()) is None:
            return None
        return [x.name for x in values]

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        if (value := self._state.get_mute()) is None:
            return None
        return value

    @property
    def volume_level(self):
        """Volume level of device."""
        if (value := self._state.get_volume()) is None:
            return None
        return value / 99.0

    @property
    def media_content_type(self):
        """Content type of current playing media."""
        source = self._state.get_source()
        if source == SourceCodes.DAB:
            value = MEDIA_TYPE_MUSIC
        elif source == SourceCodes.FM:
            value = MEDIA_TYPE_MUSIC
        else:
            value = None
        return value

    @property
    def media_content_id(self):
        """Content type of current playing media."""
        source = self._state.get_source()
        if source in (SourceCodes.DAB, SourceCodes.FM):
            if preset := self._state.get_tuner_preset():
                value = f"preset:{preset}"
            else:
                value = None
        else:
            value = None

        return value

    @property
    def media_channel(self):
        """Channel currently playing."""
        source = self._state.get_source()
        if source == SourceCodes.DAB:
            value = self._state.get_dab_station()
        elif source == SourceCodes.FM:
            value = self._state.get_rds_information()
        else:
            value = None
        return value

    @property
    def media_artist(self):
        """Artist of current playing media, music track only."""
        if self._state.get_source() == SourceCodes.DAB:
            value = self._state.get_dls_pdt()
        else:
            value = None
        return value

    @property
    def media_title(self):
        """Title of current playing media."""
        if (source := self._state.get_source()) is None:
            return None

        if channel := self.media_channel:
            value = f"{source.name} - {channel}"
        else:
            value = source.name
        return value
