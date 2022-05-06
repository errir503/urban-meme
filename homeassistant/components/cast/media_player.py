"""Provide functionality to interact with Cast devices on the network."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
import json
import logging

import pychromecast
from pychromecast.controllers.homeassistant import HomeAssistantController
from pychromecast.controllers.media import (
    MEDIA_PLAYER_ERROR_CODES,
    MEDIA_PLAYER_STATE_BUFFERING,
    MEDIA_PLAYER_STATE_PLAYING,
    MEDIA_PLAYER_STATE_UNKNOWN,
)
from pychromecast.controllers.multizone import MultizoneManager
from pychromecast.controllers.receiver import VOLUME_CONTROL_TYPE_FIXED
from pychromecast.quick_play import quick_play
from pychromecast.socket_client import (
    CONNECTION_STATUS_CONNECTED,
    CONNECTION_STATUS_DISCONNECTED,
)
import voluptuous as vol
import yarl

from homeassistant.components import media_source, zeroconf
from homeassistant.components.media_player import (
    BrowseError,
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    async_process_play_media_url,
)
from homeassistant.components.media_player.const import (
    ATTR_MEDIA_EXTRA,
    MEDIA_CLASS_DIRECTORY,
    MEDIA_TYPE_MOVIE,
    MEDIA_TYPE_MUSIC,
    MEDIA_TYPE_TVSHOW,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CAST_APP_ID_HOMEASSISTANT_LOVELACE,
    EVENT_HOMEASSISTANT_STOP,
    STATE_BUFFERING,
    STATE_IDLE,
    STATE_OFF,
    STATE_PAUSED,
    STATE_PLAYING,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.network import NoURLAvailableError, get_url, is_hass_url
import homeassistant.util.dt as dt_util
from homeassistant.util.logging import async_create_catching_coro

from .const import (
    ADDED_CAST_DEVICES_KEY,
    CAST_MULTIZONE_MANAGER_KEY,
    CONF_IGNORE_CEC,
    CONF_UUID,
    DOMAIN as CAST_DOMAIN,
    SIGNAL_CAST_DISCOVERED,
    SIGNAL_CAST_REMOVED,
    SIGNAL_HASS_CAST_SHOW_VIEW,
)
from .discovery import setup_internal_discovery
from .helpers import (
    CastStatusListener,
    ChromecastInfo,
    ChromeCastZeroconf,
    PlaylistError,
    PlaylistSupported,
    parse_playlist,
)

_LOGGER = logging.getLogger(__name__)

APP_IDS_UNRELIABLE_MEDIA_INFO = ("Netflix",)

CAST_SPLASH = "https://www.home-assistant.io/images/cast/splash.png"

ENTITY_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(CONF_UUID): cv.string,
            vol.Optional(CONF_IGNORE_CEC): vol.All(cv.ensure_list, [cv.string]),
        }
    ),
)


@callback
def _async_create_cast_device(hass: HomeAssistant, info: ChromecastInfo):
    """Create a CastDevice entity or dynamic group from the chromecast object.

    Returns None if the cast device has already been added.
    """
    _LOGGER.debug("_async_create_cast_device: %s", info)
    if info.uuid is None:
        _LOGGER.error("_async_create_cast_device uuid none: %s", info)
        return None

    # Found a cast with UUID
    added_casts = hass.data[ADDED_CAST_DEVICES_KEY]
    if info.uuid in added_casts:
        # Already added this one, the entity will take care of moved hosts
        # itself
        return None
    # -> New cast device
    added_casts.add(info.uuid)

    if info.is_dynamic_group:
        # This is a dynamic group, do not add it but connect to the service.
        group = DynamicCastGroup(hass, info)
        group.async_setup()
        return None

    return CastMediaPlayerEntity(hass, info)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cast from a config entry."""
    hass.data.setdefault(ADDED_CAST_DEVICES_KEY, set())

    # Import CEC IGNORE attributes
    pychromecast.IGNORE_CEC += config_entry.data.get(CONF_IGNORE_CEC) or []

    wanted_uuids = config_entry.data.get(CONF_UUID) or None

    @callback
    def async_cast_discovered(discover: ChromecastInfo) -> None:
        """Handle discovery of a new chromecast."""
        # If wanted_uuids is set, we're only accepting specific cast devices identified
        # by UUID
        if wanted_uuids is not None and str(discover.uuid) not in wanted_uuids:
            # UUID not matching, ignore.
            return

        cast_device = _async_create_cast_device(hass, discover)
        if cast_device is not None:
            async_add_entities([cast_device])

    async_dispatcher_connect(hass, SIGNAL_CAST_DISCOVERED, async_cast_discovered)
    ChromeCastZeroconf.set_zeroconf(await zeroconf.async_get_instance(hass))
    hass.async_add_executor_job(setup_internal_discovery, hass, config_entry)


class CastDevice:
    """Representation of a Cast device or dynamic group on the network.

    This class is the holder of the pychromecast.Chromecast object and its
    socket client. It therefore handles all reconnects and audio groups changing
    "elected leader" itself.
    """

    _mz_only: bool

    def __init__(self, hass: HomeAssistant, cast_info: ChromecastInfo) -> None:
        """Initialize the cast device."""

        self.hass: HomeAssistant = hass
        self._cast_info = cast_info
        self._chromecast: pychromecast.Chromecast | None = None
        self.mz_mgr = None
        self._status_listener: CastStatusListener | None = None
        self._add_remove_handler: Callable[[], None] | None = None
        self._del_remove_handler: Callable[[], None] | None = None
        self._name: str | None = None

    def _async_setup(self, name: str) -> None:
        """Create chromecast object."""
        self._name = name
        self._add_remove_handler = async_dispatcher_connect(
            self.hass, SIGNAL_CAST_DISCOVERED, self._async_cast_discovered
        )
        self._del_remove_handler = async_dispatcher_connect(
            self.hass, SIGNAL_CAST_REMOVED, self._async_cast_removed
        )
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_stop)
        # asyncio.create_task is used to avoid delaying startup wrapup if the device
        # is discovered already during startup but then fails to respond
        asyncio.create_task(
            async_create_catching_coro(self._async_connect_to_chromecast())
        )

    async def _async_tear_down(self) -> None:
        """Disconnect chromecast object and remove listeners."""
        await self._async_disconnect()
        if self._cast_info.uuid is not None:
            # Remove the entity from the added casts so that it can dynamically
            # be re-added again.
            self.hass.data[ADDED_CAST_DEVICES_KEY].remove(self._cast_info.uuid)
        if self._add_remove_handler:
            self._add_remove_handler()
            self._add_remove_handler = None
        if self._del_remove_handler:
            self._del_remove_handler()
            self._del_remove_handler = None

    async def _async_connect_to_chromecast(self):
        """Set up the chromecast object."""
        _LOGGER.debug(
            "[%s %s] Connecting to cast device by service %s",
            self._name,
            self._cast_info.friendly_name,
            self._cast_info.cast_info.services,
        )
        chromecast = await self.hass.async_add_executor_job(
            pychromecast.get_chromecast_from_cast_info,
            self._cast_info.cast_info,
            ChromeCastZeroconf.get_zeroconf(),
        )
        self._chromecast = chromecast

        if CAST_MULTIZONE_MANAGER_KEY not in self.hass.data:
            self.hass.data[CAST_MULTIZONE_MANAGER_KEY] = MultizoneManager()

        self.mz_mgr = self.hass.data[CAST_MULTIZONE_MANAGER_KEY]

        self._status_listener = CastStatusListener(
            self, chromecast, self.mz_mgr, self._mz_only
        )
        self._chromecast.start()

    async def _async_disconnect(self):
        """Disconnect Chromecast object if it is set."""
        if self._chromecast is not None:
            _LOGGER.debug(
                "[%s %s] Disconnecting from chromecast socket",
                self._name,
                self._cast_info.friendly_name,
            )
            await self.hass.async_add_executor_job(self._chromecast.disconnect)

        self._invalidate()

    def _invalidate(self):
        """Invalidate some attributes."""
        self._chromecast = None
        self.mz_mgr = None
        if self._status_listener is not None:
            self._status_listener.invalidate()
            self._status_listener = None

    async def _async_cast_discovered(self, discover: ChromecastInfo):
        """Handle discovery of new Chromecast."""
        if self._cast_info.uuid != discover.uuid:
            # Discovered is not our device.
            return

        _LOGGER.debug("Discovered chromecast with same UUID: %s", discover)
        self._cast_info = discover

    async def _async_cast_removed(self, discover: ChromecastInfo):
        """Handle removal of Chromecast."""

    async def _async_stop(self, event):
        """Disconnect socket on Home Assistant stop."""
        await self._async_disconnect()


class CastMediaPlayerEntity(CastDevice, MediaPlayerEntity):
    """Representation of a Cast device on the network."""

    _attr_should_poll = False
    _attr_media_image_remotely_accessible = True
    _mz_only = False

    def __init__(self, hass: HomeAssistant, cast_info: ChromecastInfo) -> None:
        """Initialize the cast device."""

        CastDevice.__init__(self, hass, cast_info)

        self.cast_status = None
        self.media_status = None
        self.media_status_received = None
        self.mz_media_status: dict[str, pychromecast.controllers.media.MediaStatus] = {}
        self.mz_media_status_received: dict[str, datetime] = {}
        self._attr_available = False
        self._hass_cast_controller: HomeAssistantController | None = None

        self._cast_view_remove_handler = None
        self._attr_unique_id = str(cast_info.uuid)
        self._attr_name = cast_info.friendly_name
        self._attr_device_info = DeviceInfo(
            identifiers={(CAST_DOMAIN, str(cast_info.uuid).replace("-", ""))},
            manufacturer=str(cast_info.cast_info.manufacturer),
            model=cast_info.cast_info.model_name,
            name=str(cast_info.friendly_name),
        )

    async def async_added_to_hass(self):
        """Create chromecast object when added to hass."""
        self._async_setup(self.entity_id)

        self._cast_view_remove_handler = async_dispatcher_connect(
            self.hass, SIGNAL_HASS_CAST_SHOW_VIEW, self._handle_signal_show_view
        )

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect Chromecast object when removed."""
        await self._async_tear_down()

        if self._cast_view_remove_handler:
            self._cast_view_remove_handler()
            self._cast_view_remove_handler = None

    async def _async_connect_to_chromecast(self):
        """Set up the chromecast object."""
        await super()._async_connect_to_chromecast()

        self._attr_available = False
        self.cast_status = self._chromecast.status
        self.media_status = self._chromecast.media_controller.status
        self.async_write_ha_state()

    async def _async_disconnect(self):
        """Disconnect Chromecast object if it is set."""
        await super()._async_disconnect()

        self._attr_available = False
        self.async_write_ha_state()

    def _invalidate(self):
        """Invalidate some attributes."""
        super()._invalidate()

        self.cast_status = None
        self.media_status = None
        self.media_status_received = None
        self.mz_media_status = {}
        self.mz_media_status_received = {}
        self._hass_cast_controller = None

    # ========== Callbacks ==========
    def new_cast_status(self, cast_status):
        """Handle updates of the cast status."""
        self.cast_status = cast_status
        self._attr_volume_level = cast_status.volume_level if cast_status else None
        self._attr_is_volume_muted = (
            cast_status.volume_muted if self.cast_status else None
        )
        self.schedule_update_ha_state()

    def new_media_status(self, media_status):
        """Handle updates of the media status."""
        if (
            media_status
            and media_status.player_is_idle
            and media_status.idle_reason == "ERROR"
        ):
            external_url = None
            internal_url = None
            tts_base_url = None
            url_description = ""
            if "tts" in self.hass.config.components:
                # pylint: disable=[import-outside-toplevel]
                from homeassistant.components import tts

                with suppress(KeyError):  # base_url not configured
                    tts_base_url = tts.get_base_url(self.hass)

            with suppress(NoURLAvailableError):  # external_url not configured
                external_url = get_url(self.hass, allow_internal=False)

            with suppress(NoURLAvailableError):  # internal_url not configured
                internal_url = get_url(self.hass, allow_external=False)

            if media_status.content_id:
                if tts_base_url and media_status.content_id.startswith(tts_base_url):
                    url_description = f" from tts.base_url ({tts_base_url})"
                if external_url and media_status.content_id.startswith(external_url):
                    url_description = f" from external_url ({external_url})"
                if internal_url and media_status.content_id.startswith(internal_url):
                    url_description = f" from internal_url ({internal_url})"

            _LOGGER.error(
                "Failed to cast media %s%s. Please make sure the URL is: "
                "Reachable from the cast device and either a publicly resolvable "
                "hostname or an IP address",
                media_status.content_id,
                url_description,
            )

        self.media_status = media_status
        self.media_status_received = dt_util.utcnow()
        self.schedule_update_ha_state()

    def load_media_failed(self, item, error_code):
        """Handle load media failed."""
        _LOGGER.debug(
            "[%s %s] Load media failed with code %s(%s) for item %s",
            self.entity_id,
            self._cast_info.friendly_name,
            error_code,
            MEDIA_PLAYER_ERROR_CODES.get(error_code, "unknown code"),
            item,
        )

    def new_connection_status(self, connection_status):
        """Handle updates of connection status."""
        _LOGGER.debug(
            "[%s %s] Received cast device connection status: %s",
            self.entity_id,
            self._cast_info.friendly_name,
            connection_status.status,
        )
        if connection_status.status == CONNECTION_STATUS_DISCONNECTED:
            self._attr_available = False
            self._invalidate()
            self.schedule_update_ha_state()
            return

        new_available = connection_status.status == CONNECTION_STATUS_CONNECTED
        if new_available != self.available:
            # Connection status callbacks happen often when disconnected.
            # Only update state when availability changed to put less pressure
            # on state machine.
            _LOGGER.debug(
                "[%s %s] Cast device availability changed: %s",
                self.entity_id,
                self._cast_info.friendly_name,
                connection_status.status,
            )
            self._attr_available = new_available
            self.schedule_update_ha_state()

    def multizone_new_media_status(self, group_uuid, media_status):
        """Handle updates of audio group media status."""
        _LOGGER.debug(
            "[%s %s] Multizone %s media status: %s",
            self.entity_id,
            self._cast_info.friendly_name,
            group_uuid,
            media_status,
        )
        self.mz_media_status[group_uuid] = media_status
        self.mz_media_status_received[group_uuid] = dt_util.utcnow()
        self.schedule_update_ha_state()

    # ========== Service Calls ==========
    def _media_controller(self):
        """
        Return media controller.

        First try from our own cast, then groups which our cast is a member in.
        """
        media_status = self.media_status
        media_controller = self._chromecast.media_controller

        if (
            media_status is None
            or media_status.player_state == MEDIA_PLAYER_STATE_UNKNOWN
        ):
            groups = self.mz_media_status
            for k, val in groups.items():
                if val and val.player_state != MEDIA_PLAYER_STATE_UNKNOWN:
                    media_controller = self.mz_mgr.get_multizone_mediacontroller(k)
                    break

        return media_controller

    def turn_on(self):
        """Turn on the cast device."""

        if not self._chromecast.is_idle:
            # Already turned on
            return

        if self._chromecast.app_id is not None:
            # Quit the previous app before starting splash screen or media player
            self._chromecast.quit_app()

        # The only way we can turn the Chromecast is on is by launching an app
        if self._chromecast.cast_type == pychromecast.const.CAST_TYPE_CHROMECAST:
            app_data = {"media_id": CAST_SPLASH, "media_type": "image/png"}
            quick_play(self._chromecast, "default_media_receiver", app_data)
        else:
            self._chromecast.start_app(pychromecast.config.APP_MEDIA_RECEIVER)

    def turn_off(self):
        """Turn off the cast device."""
        self._chromecast.quit_app()

    def mute_volume(self, mute):
        """Mute the volume."""
        self._chromecast.set_volume_muted(mute)

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        self._chromecast.set_volume(volume)

    def media_play(self):
        """Send play command."""
        media_controller = self._media_controller()
        media_controller.play()

    def media_pause(self):
        """Send pause command."""
        media_controller = self._media_controller()
        media_controller.pause()

    def media_stop(self):
        """Send stop command."""
        media_controller = self._media_controller()
        media_controller.stop()

    def media_previous_track(self):
        """Send previous track command."""
        media_controller = self._media_controller()
        media_controller.queue_prev()

    def media_next_track(self):
        """Send next track command."""
        media_controller = self._media_controller()
        media_controller.queue_next()

    def media_seek(self, position):
        """Seek the media to a specific location."""
        media_controller = self._media_controller()
        media_controller.seek(position)

    async def _async_root_payload(self, content_filter):
        """Generate root node."""
        children = []
        # Add media browsers
        for platform in self.hass.data[CAST_DOMAIN]["cast_platform"].values():
            children.extend(
                await platform.async_get_media_browser_root_object(
                    self.hass, self._chromecast.cast_type
                )
            )

        # Add media sources
        try:
            result = await media_source.async_browse_media(
                self.hass, None, content_filter=content_filter
            )
            children.extend(result.children)
        except BrowseError:
            if not children:
                raise

        # If there's only one media source, resolve it
        if len(children) == 1 and children[0].can_expand:
            return await self.async_browse_media(
                children[0].media_content_type,
                children[0].media_content_id,
            )

        return BrowseMedia(
            title="Cast",
            media_class=MEDIA_CLASS_DIRECTORY,
            media_content_id="",
            media_content_type="",
            can_play=False,
            can_expand=True,
            children=sorted(children, key=lambda c: c.title),
        )

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        """Implement the websocket media browsing helper."""
        content_filter = None

        if self._chromecast.cast_type in (
            pychromecast.const.CAST_TYPE_AUDIO,
            pychromecast.const.CAST_TYPE_GROUP,
        ):

            def audio_content_filter(item):
                """Filter non audio content."""
                return item.media_content_type.startswith("audio/")

            content_filter = audio_content_filter

        if media_content_id is None:
            return await self._async_root_payload(content_filter)

        for platform in self.hass.data[CAST_DOMAIN]["cast_platform"].values():
            browse_media = await platform.async_browse_media(
                self.hass,
                media_content_type,
                media_content_id,
                self._chromecast.cast_type,
            )
            if browse_media:
                return browse_media

        return await media_source.async_browse_media(
            self.hass, media_content_id, content_filter=content_filter
        )

    async def async_play_media(self, media_type, media_id, **kwargs):
        """Play a piece of media."""
        # Handle media_source
        if media_source.is_media_source_id(media_id):
            sourced_media = await media_source.async_resolve_media(self.hass, media_id)
            media_type = sourced_media.mime_type
            media_id = sourced_media.url

        extra = kwargs.get(ATTR_MEDIA_EXTRA, {})

        # Handle media supported by a known cast app
        if media_type == CAST_DOMAIN:
            try:
                app_data = json.loads(media_id)
                if metadata := extra.get("metadata"):
                    app_data["metadata"] = metadata
            except json.JSONDecodeError:
                _LOGGER.error("Invalid JSON in media_content_id")
                raise

            # Special handling for passed `app_id` parameter. This will only launch
            # an arbitrary cast app, generally for UX.
            if "app_id" in app_data:
                app_id = app_data.pop("app_id")
                _LOGGER.info("Starting Cast app by ID %s", app_id)
                await self.hass.async_add_executor_job(
                    self._chromecast.start_app, app_id
                )
                if app_data:
                    _LOGGER.warning(
                        "Extra keys %s were ignored. Please use app_name to cast media",
                        app_data.keys(),
                    )
                return

            app_name = app_data.pop("app_name")
            try:
                await self.hass.async_add_executor_job(
                    quick_play, self._chromecast, app_name, app_data
                )
            except NotImplementedError:
                _LOGGER.error("App %s not supported", app_name)
            return

        # Try the cast platforms
        for platform in self.hass.data[CAST_DOMAIN]["cast_platform"].values():
            result = await platform.async_play_media(
                self.hass, self.entity_id, self._chromecast, media_type, media_id
            )
            if result:
                return

        # If media ID is a relative URL, we serve it from HA.
        media_id = async_process_play_media_url(self.hass, media_id)

        # Configure play command for when playing a HLS stream
        if is_hass_url(self.hass, media_id):
            parsed = yarl.URL(media_id)
            if parsed.path.startswith("/api/hls/"):
                extra = {
                    **extra,
                    "stream_type": "LIVE",
                    "media_info": {
                        "hlsVideoSegmentFormat": "fmp4",
                    },
                }
        elif (
            media_id.endswith(".m3u")
            or media_id.endswith(".m3u8")
            or media_id.endswith(".pls")
        ):
            try:
                playlist = await parse_playlist(self.hass, media_id)
                _LOGGER.debug(
                    "[%s %s] Playing item %s from playlist %s",
                    self.entity_id,
                    self._cast_info.friendly_name,
                    playlist[0].url,
                    media_id,
                )
                media_id = playlist[0].url
                if title := playlist[0].title:
                    extra = {
                        **extra,
                        "metadata": {"title": title},
                    }
            except PlaylistSupported as err:
                _LOGGER.debug(
                    "[%s %s] Playlist %s is supported: %s",
                    self.entity_id,
                    self._cast_info.friendly_name,
                    media_id,
                    err,
                )
            except PlaylistError as err:
                _LOGGER.warning(
                    "[%s %s] Failed to parse playlist %s: %s",
                    self.entity_id,
                    self._cast_info.friendly_name,
                    media_id,
                    err,
                )

        # Default to play with the default media receiver
        app_data = {"media_id": media_id, "media_type": media_type, **extra}
        _LOGGER.debug(
            "[%s %s] Playing %s with default_media_receiver",
            self.entity_id,
            self._cast_info.friendly_name,
            app_data,
        )
        await self.hass.async_add_executor_job(
            quick_play, self._chromecast, "default_media_receiver", app_data
        )

    def _media_status(self):
        """
        Return media status.

        First try from our own cast, then groups which our cast is a member in.
        """
        media_status = self.media_status
        media_status_received = self.media_status_received

        if (
            media_status is None
            or media_status.player_state == MEDIA_PLAYER_STATE_UNKNOWN
        ):
            groups = self.mz_media_status
            for k, val in groups.items():
                if val and val.player_state != MEDIA_PLAYER_STATE_UNKNOWN:
                    media_status = val
                    media_status_received = self.mz_media_status_received[k]
                    break

        return (media_status, media_status_received)

    @property
    def state(self):
        """Return the state of the player."""
        # The lovelace app loops media to prevent timing out, don't show that
        if self.app_id == CAST_APP_ID_HOMEASSISTANT_LOVELACE:
            return STATE_PLAYING
        if (media_status := self._media_status()[0]) is not None:
            if media_status.player_state == MEDIA_PLAYER_STATE_PLAYING:
                return STATE_PLAYING
            if media_status.player_state == MEDIA_PLAYER_STATE_BUFFERING:
                return STATE_BUFFERING
            if media_status.player_is_paused:
                return STATE_PAUSED
            if media_status.player_is_idle:
                return STATE_IDLE
        if self.app_id is not None and self.app_id != pychromecast.IDLE_APP_ID:
            if self.app_id in APP_IDS_UNRELIABLE_MEDIA_INFO:
                # Some apps don't report media status, show the player as playing
                return STATE_PLAYING
            return STATE_IDLE
        if self._chromecast is not None and self._chromecast.is_idle:
            return STATE_OFF
        return None

    @property
    def media_content_id(self):
        """Content ID of current playing media."""
        # The lovelace app loops media to prevent timing out, don't show that
        if self.app_id == CAST_APP_ID_HOMEASSISTANT_LOVELACE:
            return None
        media_status = self._media_status()[0]
        return media_status.content_id if media_status else None

    @property
    def media_content_type(self):
        """Content type of current playing media."""
        # The lovelace app loops media to prevent timing out, don't show that
        if self.app_id == CAST_APP_ID_HOMEASSISTANT_LOVELACE:
            return None
        if (media_status := self._media_status()[0]) is None:
            return None
        if media_status.media_is_tvshow:
            return MEDIA_TYPE_TVSHOW
        if media_status.media_is_movie:
            return MEDIA_TYPE_MOVIE
        if media_status.media_is_musictrack:
            return MEDIA_TYPE_MUSIC
        return None

    @property
    def media_duration(self):
        """Duration of current playing media in seconds."""
        # The lovelace app loops media to prevent timing out, don't show that
        if self.app_id == CAST_APP_ID_HOMEASSISTANT_LOVELACE:
            return None
        media_status = self._media_status()[0]
        return media_status.duration if media_status else None

    @property
    def media_image_url(self):
        """Image url of current playing media."""
        if (media_status := self._media_status()[0]) is None:
            return None

        images = media_status.images

        return images[0].url if images and images[0].url else None

    @property
    def media_title(self):
        """Title of current playing media."""
        media_status = self._media_status()[0]
        return media_status.title if media_status else None

    @property
    def media_artist(self):
        """Artist of current playing media (Music track only)."""
        media_status = self._media_status()[0]
        return media_status.artist if media_status else None

    @property
    def media_album_name(self):
        """Album of current playing media (Music track only)."""
        media_status = self._media_status()[0]
        return media_status.album_name if media_status else None

    @property
    def media_album_artist(self):
        """Album artist of current playing media (Music track only)."""
        media_status = self._media_status()[0]
        return media_status.album_artist if media_status else None

    @property
    def media_track(self):
        """Track number of current playing media (Music track only)."""
        media_status = self._media_status()[0]
        return media_status.track if media_status else None

    @property
    def media_series_title(self):
        """Return the title of the series of current playing media."""
        media_status = self._media_status()[0]
        return media_status.series_title if media_status else None

    @property
    def media_season(self):
        """Season of current playing media (TV Show only)."""
        media_status = self._media_status()[0]
        return media_status.season if media_status else None

    @property
    def media_episode(self):
        """Episode of current playing media (TV Show only)."""
        media_status = self._media_status()[0]
        return media_status.episode if media_status else None

    @property
    def app_id(self):
        """Return the ID of the current running app."""
        return self._chromecast.app_id if self._chromecast else None

    @property
    def app_name(self):
        """Name of the current running app."""
        return self._chromecast.app_display_name if self._chromecast else None

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        support = (
            MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.TURN_ON
        )
        media_status = self._media_status()[0]

        if (
            self.cast_status
            and self.cast_status.volume_control_type != VOLUME_CONTROL_TYPE_FIXED
        ):
            support |= (
                MediaPlayerEntityFeature.VOLUME_MUTE
                | MediaPlayerEntityFeature.VOLUME_SET
            )

        if media_status and self.app_id != CAST_APP_ID_HOMEASSISTANT_LOVELACE:
            support |= (
                MediaPlayerEntityFeature.PAUSE
                | MediaPlayerEntityFeature.PLAY
                | MediaPlayerEntityFeature.STOP
            )
            if media_status.supports_queue_next:
                support |= (
                    MediaPlayerEntityFeature.PREVIOUS_TRACK
                    | MediaPlayerEntityFeature.NEXT_TRACK
                )
            if media_status.supports_seek:
                support |= MediaPlayerEntityFeature.SEEK

        if "media_source" in self.hass.config.components:
            support |= MediaPlayerEntityFeature.BROWSE_MEDIA

        return support

    @property
    def media_position(self):
        """Position of current playing media in seconds."""
        # The lovelace app loops media to prevent timing out, don't show that
        if self.app_id == CAST_APP_ID_HOMEASSISTANT_LOVELACE:
            return None
        media_status = self._media_status()[0]
        if media_status is None or not (
            media_status.player_is_playing
            or media_status.player_is_paused
            or media_status.player_is_idle
        ):
            return None
        return media_status.current_time

    @property
    def media_position_updated_at(self):
        """When was the position of the current playing media valid.

        Returns value from homeassistant.util.dt.utcnow().
        """
        if self.app_id == CAST_APP_ID_HOMEASSISTANT_LOVELACE:
            return None
        return self._media_status()[1]

    def _handle_signal_show_view(
        self,
        controller: HomeAssistantController,
        entity_id: str,
        view_path: str,
        url_path: str | None,
    ):
        """Handle a show view signal."""
        if entity_id != self.entity_id or self._chromecast is None:
            return

        if self._hass_cast_controller is None:
            self._hass_cast_controller = controller
            self._chromecast.register_handler(controller)

        self._hass_cast_controller.show_lovelace_view(view_path, url_path)


class DynamicCastGroup(CastDevice):
    """Representation of a Cast device on the network - for dynamic cast groups."""

    _mz_only = True

    def async_setup(self):
        """Create chromecast object."""
        self._async_setup("Dynamic group")

    async def _async_cast_removed(self, discover: ChromecastInfo):
        """Handle removal of Chromecast."""
        if self._cast_info.uuid != discover.uuid:
            # Removed is not our device.
            return

        if not discover.cast_info.services:
            # Clean up the dynamic group
            _LOGGER.debug("Clean up dynamic group: %s", discover)
            await self._async_tear_down()
