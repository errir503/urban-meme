"""MediaPlayer platform for Roon integration."""
from __future__ import annotations

import logging
from typing import Any

from roonapi import split_media_path
import voluptuous as vol

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEVICE_DEFAULT_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import convert
from homeassistant.util.dt import utcnow

from .const import DOMAIN
from .media_browser import browse_media

_LOGGER = logging.getLogger(__name__)

SERVICE_TRANSFER = "transfer"

ATTR_TRANSFER = "transfer_id"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Roon MediaPlayer from Config Entry."""
    roon_server = hass.data[DOMAIN][config_entry.entry_id]
    media_players = set()

    # Register entity services
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_TRANSFER,
        {vol.Required(ATTR_TRANSFER): cv.entity_id},
        "async_transfer",
    )

    @callback
    def async_update_media_player(player_data):
        """Add or update Roon MediaPlayer."""
        dev_id = player_data["dev_id"]
        if dev_id not in media_players:
            # new player!
            media_player = RoonDevice(roon_server, player_data)
            media_players.add(dev_id)
            async_add_entities([media_player])
        else:
            # update existing player
            async_dispatcher_send(
                hass, f"room_media_player_update_{dev_id}", player_data
            )

    # start listening for players to be added or changed by the server component
    async_dispatcher_connect(hass, "roon_media_player", async_update_media_player)


class RoonDevice(MediaPlayerEntity):
    """Representation of an Roon device."""

    _attr_should_poll = False
    _attr_supported_features = (
        MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.GROUPING
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.SHUFFLE_SET
        | MediaPlayerEntityFeature.SEEK
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.VOLUME_STEP
    )

    def __init__(self, server, player_data):
        """Initialize Roon device object."""
        self._remove_signal_status = None
        self._server = server
        self._available = True
        self._last_position_update = None
        self._supports_standby = False
        self._state = MediaPlayerState.IDLE
        self._unique_id = None
        self._zone_id = None
        self._output_id = None
        self._name = DEVICE_DEFAULT_NAME
        self._media_title = None
        self._media_album_name = None
        self._media_artist = None
        self._media_position = 0
        self._media_duration = 0
        self._is_volume_muted = False
        self._volume_step = 0
        self._shuffle = False
        self._media_image_url = None
        self._volume_level = 0
        self.update_data(player_data)

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"room_media_player_update_{self.unique_id}",
                self.async_update_callback,
            )
        )
        self._server.add_player_id(self.entity_id, self.name)

    @callback
    def async_update_callback(self, player_data):
        """Handle device updates."""
        self.update_data(player_data)
        self.async_write_ha_state()

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def group_members(self):
        """Return the grouped players."""

        roon_names = self._server.roonapi.grouped_zone_names(self._output_id)
        return [self._server.entity_id(roon_name) for roon_name in roon_names]

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        if self.player_data.get("source_controls"):
            dev_model = self.player_data["source_controls"][0].get("display_name")
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=self.name,
            manufacturer="RoonLabs",
            model=dev_model,
            via_device=(DOMAIN, self._server.roon_id),
        )

    def update_data(self, player_data=None):
        """Update session object."""
        if player_data:
            self.player_data = player_data
        if not self.player_data["is_available"]:
            # this player was removed
            self._available = False
            self._state = MediaPlayerState.OFF
        else:
            self._available = True
            # determine player state
            self.update_state()
            if self.state == MediaPlayerState.PLAYING:
                self._last_position_update = utcnow()

    @classmethod
    def _parse_volume(cls, player_data):
        """Parse volume data to determine volume levels and mute state."""
        volume = {
            "level": 0,
            "step": 0,
            "muted": False,
        }

        try:
            volume_data = player_data["volume"]
            volume_muted = volume_data["is_muted"]
            volume_step = convert(volume_data["step"], int, 0)

            if volume_data["type"] == "db":
                level = convert(volume_data["value"], float, 0.0) / 80 * 100 + 100
            else:
                level = convert(volume_data["value"], float, 0.0)

            volume_level = convert(level, int, 0) / 100
        except KeyError:
            # catch KeyError
            pass
        else:
            volume["muted"] = volume_muted
            volume["step"] = volume_step
            volume["level"] = volume_level

        return volume

    def _parse_now_playing(self, player_data):
        """Parse now playing data to determine title, artist, position, duration and artwork."""
        now_playing = {
            "title": None,
            "artist": None,
            "album": None,
            "position": 0,
            "duration": 0,
            "image": None,
        }
        now_playing_data = None

        try:
            now_playing_data = player_data["now_playing"]
            media_title = now_playing_data["three_line"]["line1"]
            media_artist = now_playing_data["three_line"]["line2"]
            media_album_name = now_playing_data["three_line"]["line3"]
            media_position = convert(now_playing_data["seek_position"], int, 0)
            media_duration = convert(now_playing_data.get("length"), int, 0)
            image_id = now_playing_data.get("image_key")
        except KeyError:
            # catch KeyError
            pass
        else:
            now_playing["title"] = media_title
            now_playing["artist"] = media_artist
            now_playing["album"] = media_album_name
            now_playing["position"] = media_position
            now_playing["duration"] = media_duration
            if image_id:
                now_playing["image"] = self._server.roonapi.get_image(image_id)

        return now_playing

    def update_state(self):
        """Update the power state and player state."""

        new_state = ""
        # power state from source control (if supported)
        if "source_controls" in self.player_data:
            for source in self.player_data["source_controls"]:
                if source["supports_standby"] and source["status"] != "indeterminate":
                    self._supports_standby = True
                    if source["status"] in ["standby", "deselected"]:
                        new_state = MediaPlayerState.OFF
                    break
        # determine player state
        if not new_state:
            if self.player_data["state"] == "playing":
                new_state = MediaPlayerState.PLAYING
            elif self.player_data["state"] == "loading":
                new_state = MediaPlayerState.PLAYING
            elif self.player_data["state"] == "stopped":
                new_state = MediaPlayerState.IDLE
            elif self.player_data["state"] == "paused":
                new_state = MediaPlayerState.PAUSED
            else:
                new_state = MediaPlayerState.IDLE
        self._state = new_state
        self._unique_id = self.player_data["dev_id"]
        self._zone_id = self.player_data["zone_id"]
        self._output_id = self.player_data["output_id"]
        self._shuffle = self.player_data["settings"]["shuffle"]
        self._name = self.player_data["display_name"]

        volume = RoonDevice._parse_volume(self.player_data)
        self._is_volume_muted = volume["muted"]
        self._volume_step = volume["step"]
        self._is_volume_muted = volume["muted"]
        self._volume_level = volume["level"]

        now_playing = self._parse_now_playing(self.player_data)
        self._media_title = now_playing["title"]
        self._media_artist = now_playing["artist"]
        self._media_album_name = now_playing["album"]
        self._media_position = now_playing["position"]
        self._media_duration = now_playing["duration"]
        self._media_image_url = now_playing["image"]

    @property
    def media_position_updated_at(self):
        """When was the position of the current playing media valid."""
        # Returns value from homeassistant.util.dt.utcnow().
        return self._last_position_update

    @property
    def unique_id(self):
        """Return the id of this roon client."""
        return self._unique_id

    @property
    def zone_id(self):
        """Return current session Id."""
        return self._zone_id

    @property
    def output_id(self):
        """Return current session Id."""
        return self._output_id

    @property
    def name(self):
        """Return device name."""
        return self._name

    @property
    def media_title(self):
        """Return title currently playing."""
        return self._media_title

    @property
    def media_album_name(self):
        """Album name of current playing media (Music track only)."""
        return self._media_album_name

    @property
    def media_artist(self):
        """Artist of current playing media (Music track only)."""
        return self._media_artist

    @property
    def media_album_artist(self):
        """Album artist of current playing media (Music track only)."""
        return self._media_artist

    @property
    def media_image_url(self):
        """Image url of current playing media."""
        return self._media_image_url

    @property
    def media_position(self):
        """Return position currently playing."""
        return self._media_position

    @property
    def media_duration(self):
        """Return total runtime length."""
        return self._media_duration

    @property
    def volume_level(self):
        """Return current volume level."""
        return self._volume_level

    @property
    def is_volume_muted(self):
        """Return mute state."""
        return self._is_volume_muted

    @property
    def volume_step(self):
        """.Return volume step size."""
        return self._volume_step

    @property
    def supports_standby(self):
        """Return power state of source controls."""
        return self._supports_standby

    @property
    def state(self):
        """Return current playstate of the device."""
        return self._state

    @property
    def shuffle(self):
        """Boolean if shuffle is enabled."""
        return self._shuffle

    def media_play(self) -> None:
        """Send play command to device."""
        self._server.roonapi.playback_control(self.output_id, "play")

    def media_pause(self) -> None:
        """Send pause command to device."""
        self._server.roonapi.playback_control(self.output_id, "pause")

    def media_play_pause(self) -> None:
        """Toggle play command to device."""
        self._server.roonapi.playback_control(self.output_id, "playpause")

    def media_stop(self) -> None:
        """Send stop command to device."""
        self._server.roonapi.playback_control(self.output_id, "stop")

    def media_next_track(self) -> None:
        """Send next track command to device."""
        self._server.roonapi.playback_control(self.output_id, "next")

    def media_previous_track(self) -> None:
        """Send previous track command to device."""
        self._server.roonapi.playback_control(self.output_id, "previous")

    def media_seek(self, position: float) -> None:
        """Send seek command to device."""
        self._server.roonapi.seek(self.output_id, position)
        # Seek doesn't cause an async update - so force one
        self._media_position = position
        self.schedule_update_ha_state()

    def set_volume_level(self, volume: float) -> None:
        """Send new volume_level to device."""
        volume = int(volume * 100)
        self._server.roonapi.change_volume(self.output_id, volume)

    def mute_volume(self, mute=True):
        """Send mute/unmute to device."""
        self._server.roonapi.mute(self.output_id, mute)

    def volume_up(self) -> None:
        """Send new volume_level to device."""
        self._server.roonapi.change_volume(self.output_id, 3, "relative")

    def volume_down(self) -> None:
        """Send new volume_level to device."""
        self._server.roonapi.change_volume(self.output_id, -3, "relative")

    def turn_on(self) -> None:
        """Turn on device (if supported)."""
        if not (self.supports_standby and "source_controls" in self.player_data):
            self.media_play()
            return
        for source in self.player_data["source_controls"]:
            if source["supports_standby"] and source["status"] != "indeterminate":
                self._server.roonapi.convenience_switch(
                    self.output_id, source["control_key"]
                )
                return

    def turn_off(self) -> None:
        """Turn off device (if supported)."""
        if not (self.supports_standby and "source_controls" in self.player_data):
            self.media_stop()
            return

        for source in self.player_data["source_controls"]:
            if source["supports_standby"] and source["status"] != "indeterminate":
                self._server.roonapi.standby(self.output_id, source["control_key"])
                return

    def set_shuffle(self, shuffle: bool) -> None:
        """Set shuffle state."""
        self._server.roonapi.shuffle(self.output_id, shuffle)

    def play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        """Send the play_media command to the media player."""

        _LOGGER.debug("Playback request for %s / %s", media_type, media_id)
        if media_type in ("library", "track"):
            # media_id is a roon browser id
            self._server.roonapi.play_id(self.zone_id, media_id)
        else:
            # media_id is a path matching the Roon menu structure
            path_list = split_media_path(media_id)
            if not self._server.roonapi.play_media(self.zone_id, path_list):
                _LOGGER.error(
                    "Playback request for %s / %s / %s was unsuccessful",
                    media_type,
                    media_id,
                    path_list,
                )

    def join_players(self, group_members: list[str]) -> None:
        """Join `group_members` as a player group with the current player."""

        zone_data = self._server.roonapi.zone_by_output_id(self._output_id)
        if zone_data is None:
            _LOGGER.error("No zone data for %s", self.name)
            return

        sync_available = {}
        for zone in self._server.zones.values():
            for output in zone["outputs"]:
                if (
                    zone["display_name"] != self.name
                    and output["output_id"]
                    in self.player_data["can_group_with_output_ids"]
                    and zone["display_name"] not in sync_available
                ):
                    sync_available[zone["display_name"]] = output["output_id"]

        names = []
        for entity_id in group_members:
            name = self._server.roon_name(entity_id)
            if name is None:
                _LOGGER.error("No roon player found for %s", entity_id)
                return
            if name not in sync_available:
                _LOGGER.error(
                    "Can't join player %s with %s because it's not in the join available list %s",
                    name,
                    self.name,
                    list(sync_available),
                )
                return
            names.append(name)

        _LOGGER.debug("Joining %s to %s", names, self.name)
        self._server.roonapi.group_outputs(
            [self._output_id] + [sync_available[name] for name in names]
        )

    def unjoin_player(self) -> None:
        """Remove this player from any group."""

        if not self._server.roonapi.is_grouped(self._output_id):
            _LOGGER.error(
                "Can't unjoin player %s because it's not in a group",
                self.name,
            )
            return

        self._server.roonapi.ungroup_outputs([self._output_id])

    async def async_transfer(self, transfer_id):
        """Transfer playback from this roon player to another."""

        name = self._server.roon_name(transfer_id)
        if name is None:
            _LOGGER.error("No roon player found for %s", transfer_id)
            return

        zone_ids = {
            output["display_name"]: output["zone_id"]
            for output in self._server.zones.values()
            if output["display_name"] != self.name
        }

        if (transfer_id := zone_ids.get(name)) is None:
            _LOGGER.error(
                "Can't transfer from %s to %s because destination is not known %s",
                self.name,
                transfer_id,
                list(zone_ids),
            )

        _LOGGER.debug("Transferring from %s to %s", self.name, name)
        await self.hass.async_add_executor_job(
            self._server.roonapi.transfer_zone, self._zone_id, transfer_id
        )

    async def async_browse_media(
        self, media_content_type: str | None = None, media_content_id: str | None = None
    ) -> BrowseMedia:
        """Implement the websocket media browsing helper."""
        return await self.hass.async_add_executor_job(
            browse_media,
            self.zone_id,
            self._server,
            media_content_type,
            media_content_id,
        )
