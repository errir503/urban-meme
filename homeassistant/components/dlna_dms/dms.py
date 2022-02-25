"""Wrapper for media_source around async_upnp_client's DmsDevice ."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import functools
from typing import Any, TypeVar, cast

from async_upnp_client import UpnpEventHandler, UpnpFactory, UpnpRequester
from async_upnp_client.aiohttp import AiohttpSessionRequester
from async_upnp_client.const import NotificationSubType
from async_upnp_client.exceptions import UpnpActionError, UpnpConnectionError, UpnpError
from async_upnp_client.profiles.dlna import ContentDirectoryErrorCode, DmsDevice
from didl_lite import didl_lite

from homeassistant.backports.enum import StrEnum
from homeassistant.components import ssdp
from homeassistant.components.media_player.const import MEDIA_CLASS_DIRECTORY
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.components.media_source.error import Unresolvable
from homeassistant.components.media_source.models import BrowseMediaSource, PlayMedia
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.util import slugify

from .const import (
    DLNA_BROWSE_FILTER,
    DLNA_PATH_FILTER,
    DLNA_RESOLVE_FILTER,
    DLNA_SORT_CRITERIA,
    DOMAIN,
    LOGGER,
    MEDIA_CLASS_MAP,
    PATH_OBJECT_ID_FLAG,
    PATH_SEARCH_FLAG,
    PATH_SEP,
    ROOT_OBJECT_ID,
    STREAMABLE_PROTOCOLS,
)

_DlnaDmsDeviceMethod = TypeVar("_DlnaDmsDeviceMethod", bound="DmsDeviceSource")
_RetType = TypeVar("_RetType")


class DlnaDmsData:
    """Storage class for domain global data."""

    hass: HomeAssistant
    lock: asyncio.Lock
    requester: UpnpRequester
    upnp_factory: UpnpFactory
    event_handler: UpnpEventHandler
    devices: dict[str, DmsDeviceSource]  # Indexed by config_entry.unique_id
    sources: dict[str, DmsDeviceSource]  # Indexed by source_id

    def __init__(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Initialize global data."""
        self.hass = hass
        self.lock = asyncio.Lock()
        session = aiohttp_client.async_get_clientsession(hass, verify_ssl=False)
        self.requester = AiohttpSessionRequester(session, with_sleep=True)
        self.upnp_factory = UpnpFactory(self.requester, non_strict=True)
        # NOTE: event_handler is not actually used, and is only created to
        # satisfy the DmsDevice.__init__ signature
        self.event_handler = UpnpEventHandler("", self.requester)
        self.devices = {}
        self.sources = {}

    async def async_setup_entry(self, config_entry: ConfigEntry) -> bool:
        """Create a DMS device connection from a config entry."""
        assert config_entry.unique_id
        async with self.lock:
            source_id = self._generate_source_id(config_entry.title)
            device = DmsDeviceSource(self.hass, config_entry, source_id)
            self.devices[config_entry.unique_id] = device
            self.sources[device.source_id] = device

        # Update the device when the associated config entry is modified
        config_entry.async_on_unload(
            config_entry.add_update_listener(self.async_update_entry)
        )

        await device.async_added_to_hass()
        return True

    async def async_unload_entry(self, config_entry: ConfigEntry) -> bool:
        """Unload a config entry and disconnect the corresponding DMS device."""
        assert config_entry.unique_id
        async with self.lock:
            device = self.devices.pop(config_entry.unique_id)
            del self.sources[device.source_id]
        await device.async_will_remove_from_hass()
        return True

    async def async_update_entry(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Update a DMS device when the config entry changes."""
        assert config_entry.unique_id
        async with self.lock:
            device = self.devices[config_entry.unique_id]
            # Update the source_id to match the new name
            del self.sources[device.source_id]
            device.source_id = self._generate_source_id(config_entry.title)
            self.sources[device.source_id] = device

    def _generate_source_id(self, name: str) -> str:
        """Generate a unique source ID.

        Caller should hold self.lock when calling this method.
        """
        source_id_base = slugify(name)
        if source_id_base not in self.sources:
            return source_id_base

        tries = 1
        while (suggested_source_id := f"{source_id_base}_{tries}") in self.sources:
            tries += 1

        return suggested_source_id


@callback
def get_domain_data(hass: HomeAssistant) -> DlnaDmsData:
    """Obtain this integration's domain data, creating it if needed."""
    if DOMAIN in hass.data:
        return cast(DlnaDmsData, hass.data[DOMAIN])

    data = DlnaDmsData(hass)
    hass.data[DOMAIN] = data
    return data


@dataclass
class DidlPlayMedia(PlayMedia):
    """Playable media with DIDL metadata."""

    didl_metadata: didl_lite.DidlObject


class DlnaDmsDeviceError(BrowseError, Unresolvable):
    """Base for errors raised by DmsDeviceSource.

    Caught by both media_player (BrowseError) and media_source (Unresolvable),
    so DmsDeviceSource methods can be used for both browse and resolve
    functionality.
    """


class DeviceConnectionError(DlnaDmsDeviceError):
    """Error occurred with the connection to the server."""


class ActionError(DlnaDmsDeviceError):
    """Error when calling a UPnP Action on the device."""


def catch_request_errors(
    func: Callable[[_DlnaDmsDeviceMethod, str], Coroutine[Any, Any, _RetType]]
) -> Callable[[_DlnaDmsDeviceMethod, str], Coroutine[Any, Any, _RetType]]:
    """Catch UpnpError errors."""

    @functools.wraps(func)
    async def wrapper(self: _DlnaDmsDeviceMethod, req_param: str) -> _RetType:
        """Catch UpnpError errors and check availability before and after request."""
        if not self.available:
            LOGGER.warning("Device disappeared when trying to call %s", func.__name__)
            raise DeviceConnectionError("DMS is not connected")

        try:
            return await func(self, req_param)
        except UpnpActionError as err:
            LOGGER.debug("Server failure", exc_info=err)
            if err.error_code == ContentDirectoryErrorCode.NO_SUCH_OBJECT:
                LOGGER.debug("No such object: %s", req_param)
                raise ActionError(f"No such object: {req_param}") from err
            if err.error_code == ContentDirectoryErrorCode.INVALID_SEARCH_CRITERIA:
                LOGGER.debug("Invalid query: %s", req_param)
                raise ActionError(f"Invalid query: {req_param}") from err
            raise DeviceConnectionError(f"Server failure: {err!r}") from err
        except UpnpConnectionError as err:
            LOGGER.debug("Server disconnected", exc_info=err)
            await self.device_disconnect()
            raise DeviceConnectionError(f"Server disconnected: {err!r}") from err
        except UpnpError as err:
            LOGGER.debug("Server communication failure", exc_info=err)
            raise DeviceConnectionError(
                f"Server communication failure: {err!r}"
            ) from err

    return wrapper


class DmsDeviceSource:
    """DMS Device wrapper, providing media files as a media_source."""

    hass: HomeAssistant
    config_entry: ConfigEntry

    # Unique slug used for media-source URIs
    source_id: str

    # Last known URL for the device, used when adding this wrapper to hass to
    # try to connect before SSDP has rediscovered it, or when SSDP discovery
    # fails.
    location: str | None

    _device_lock: asyncio.Lock  # Held when connecting or disconnecting the device
    _device: DmsDevice | None = None

    # Only try to connect once when an ssdp:alive advertisement is received
    _ssdp_connect_failed: bool = False

    # Track BOOTID in SSDP advertisements for device changes
    _bootid: int | None = None

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, source_id: str
    ) -> None:
        """Initialize a DMS Source."""
        self.hass = hass
        self.config_entry = config_entry
        self.source_id = source_id
        self.location = self.config_entry.data[CONF_URL]
        self._device_lock = asyncio.Lock()

    # Callbacks and events

    async def async_added_to_hass(self) -> None:
        """Handle addition of this source."""

        # Try to connect to the last known location, but don't worry if not available
        if not self._device and self.location:
            try:
                await self.device_connect()
            except UpnpError as err:
                LOGGER.debug("Couldn't connect immediately: %r", err)

        # Get SSDP notifications for only this device
        self.config_entry.async_on_unload(
            await ssdp.async_register_callback(
                self.hass, self.async_ssdp_callback, {"USN": self.usn}
            )
        )

        # async_upnp_client.SsdpListener only reports byebye once for each *UDN*
        # (device name) which often is not the USN (service within the device)
        # that we're interested in. So also listen for byebye advertisements for
        # the UDN, which is reported in the _udn field of the combined_headers.
        self.config_entry.async_on_unload(
            await ssdp.async_register_callback(
                self.hass,
                self.async_ssdp_callback,
                {"_udn": self.udn, "NTS": NotificationSubType.SSDP_BYEBYE},
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        """Handle removal of this source."""
        await self.device_disconnect()

    async def async_ssdp_callback(
        self, info: ssdp.SsdpServiceInfo, change: ssdp.SsdpChange
    ) -> None:
        """Handle notification from SSDP of device state change."""
        LOGGER.debug(
            "SSDP %s notification of device %s at %s",
            change,
            info.ssdp_usn,
            info.ssdp_location,
        )

        try:
            bootid_str = info.ssdp_headers[ssdp.ATTR_SSDP_BOOTID]
            bootid: int | None = int(bootid_str, 10)
        except (KeyError, ValueError):
            bootid = None

        if change == ssdp.SsdpChange.UPDATE:
            # This is an announcement that bootid is about to change
            if self._bootid is not None and self._bootid == bootid:
                # Store the new value (because our old value matches) so that we
                # can ignore subsequent ssdp:alive messages
                try:
                    next_bootid_str = info.ssdp_headers[ssdp.ATTR_SSDP_NEXTBOOTID]
                    self._bootid = int(next_bootid_str, 10)
                except (KeyError, ValueError):
                    pass
            # Nothing left to do until ssdp:alive comes through
            return

        if self._bootid is not None and self._bootid != bootid:
            # Device has rebooted
            # Maybe connection will succeed now
            self._ssdp_connect_failed = False
            if self._device:
                # Drop existing connection and maybe reconnect
                await self.device_disconnect()
        self._bootid = bootid

        if change == ssdp.SsdpChange.BYEBYE:
            # Device is going away
            if self._device:
                # Disconnect from gone device
                await self.device_disconnect()
            # Maybe the next alive message will result in a successful connection
            self._ssdp_connect_failed = False

        if (
            change == ssdp.SsdpChange.ALIVE
            and not self._device
            and not self._ssdp_connect_failed
        ):
            assert info.ssdp_location
            self.location = info.ssdp_location
            try:
                await self.device_connect()
            except UpnpError as err:
                self._ssdp_connect_failed = True
                LOGGER.warning(
                    "Failed connecting to recently alive device at %s: %r",
                    self.location,
                    err,
                )

    # Device connection/disconnection

    async def device_connect(self) -> None:
        """Connect to the device now that it's available."""
        LOGGER.debug("Connecting to device at %s", self.location)

        async with self._device_lock:
            if self._device:
                LOGGER.debug("Trying to connect when device already connected")
                return

            if not self.location:
                LOGGER.debug("Not connecting because location is not known")
                return

            domain_data = get_domain_data(self.hass)

            # Connect to the base UPNP device
            upnp_device = await domain_data.upnp_factory.async_create_device(
                self.location
            )

            # Create profile wrapper
            self._device = DmsDevice(upnp_device, domain_data.event_handler)

            # Update state variables. We don't care if they change, so this is
            # only done once, here.
            await self._device.async_update()

    async def device_disconnect(self) -> None:
        """Destroy connections to the device now that it's not available.

        Also call when removing this device wrapper from hass to clean up connections.
        """
        async with self._device_lock:
            if not self._device:
                LOGGER.debug("Disconnecting from device that's not connected")
                return

            LOGGER.debug("Disconnecting from %s", self._device.name)

            self._device = None

    # Device properties

    @property
    def available(self) -> bool:
        """Device is available when we have a connection to it."""
        return self._device is not None and self._device.profile_device.available

    @property
    def usn(self) -> str:
        """Get the USN (Unique Service Name) for the wrapped UPnP device end-point."""
        return self.config_entry.data[CONF_DEVICE_ID]

    @property
    def udn(self) -> str:
        """Get the UDN (Unique Device Name) based on the USN."""
        return self.usn.partition("::")[0]

    @property
    def name(self) -> str:
        """Return a name for the media server."""
        return self.config_entry.title

    @property
    def icon(self) -> str | None:
        """Return an URL to an icon for the media server."""
        if not self._device:
            return None

        return self._device.icon

    # MediaSource methods

    async def async_resolve_media(self, identifier: str) -> DidlPlayMedia:
        """Resolve a media item to a playable item."""
        LOGGER.debug("async_resolve_media(%s)", identifier)
        action, parameters = _parse_identifier(identifier)

        if action is Action.OBJECT:
            return await self.async_resolve_object(parameters)

        if action is Action.PATH:
            object_id = await self.async_resolve_path(parameters)
            return await self.async_resolve_object(object_id)

        if action is Action.SEARCH:
            return await self.async_resolve_search(parameters)

        LOGGER.debug("Invalid identifier %s", identifier)
        raise Unresolvable(f"Invalid identifier {identifier}")

    async def async_browse_media(self, identifier: str | None) -> BrowseMediaSource:
        """Browse media."""
        LOGGER.debug("async_browse_media(%s)", identifier)
        action, parameters = _parse_identifier(identifier)

        if action is Action.OBJECT:
            return await self.async_browse_object(parameters)

        if action is Action.PATH:
            object_id = await self.async_resolve_path(parameters)
            return await self.async_browse_object(object_id)

        if action is Action.SEARCH:
            return await self.async_browse_search(parameters)

        return await self.async_browse_object(ROOT_OBJECT_ID)

    # DMS methods

    @catch_request_errors
    async def async_resolve_object(self, object_id: str) -> DidlPlayMedia:
        """Return a playable media item specified by ObjectID."""
        assert self._device

        item = await self._device.async_browse_metadata(
            object_id, metadata_filter=DLNA_RESOLVE_FILTER
        )

        # Use the first playable resource
        return self._didl_to_play_media(item)

    @catch_request_errors
    async def async_resolve_path(self, path: str) -> str:
        """Return an Object ID resolved from a path string."""
        assert self._device

        # Iterate through the path, searching for a matching title within the
        # DLNA object hierarchy.
        object_id = ROOT_OBJECT_ID
        for node in path.split(PATH_SEP):
            if not node:
                # Skip empty names, for when multiple slashes are involved, e.g //
                continue

            criteria = (
                f'@parentID="{_esc_quote(object_id)}" and dc:title="{_esc_quote(node)}"'
            )
            try:
                result = await self._device.async_search_directory(
                    object_id,
                    search_criteria=criteria,
                    metadata_filter=DLNA_PATH_FILTER,
                    requested_count=1,
                )
            except UpnpActionError as err:
                LOGGER.debug("Error in call to async_search_directory: %r", err)
                if err.error_code == ContentDirectoryErrorCode.NO_SUCH_CONTAINER:
                    raise Unresolvable(f"No such container: {object_id}") from err
                # Search failed, but can still try browsing children
            else:
                if result.total_matches > 1:
                    raise Unresolvable(f"Too many items found for {node} in {path}")

                if result.result:
                    object_id = result.result[0].id
                    continue

            # Nothing was found via search, fall back to iterating children
            result = await self._device.async_browse_direct_children(
                object_id, metadata_filter=DLNA_PATH_FILTER
            )

            if result.total_matches == 0 or not result.result:
                raise Unresolvable(f"No contents for {node} in {path}")

            node_lower = node.lower()
            for child in result.result:
                if child.title.lower() == node_lower:
                    object_id = child.id
                    break
            else:
                # Examining all direct children failed too
                raise Unresolvable(f"Nothing found for {node} in {path}")
        return object_id

    @catch_request_errors
    async def async_resolve_search(self, query: str) -> DidlPlayMedia:
        """Return first playable media item found by the query string."""
        assert self._device

        result = await self._device.async_search_directory(
            container_id=ROOT_OBJECT_ID,
            search_criteria=query,
            metadata_filter=DLNA_RESOLVE_FILTER,
            requested_count=1,
        )

        if result.total_matches == 0 or not result.result:
            raise Unresolvable(f"Nothing found for {query}")

        # Use the first result, even if it doesn't have a playable resource
        item = result.result[0]

        if not isinstance(item, didl_lite.DidlObject):
            raise Unresolvable(f"{item} is not a DidlObject")

        return self._didl_to_play_media(item)

    @catch_request_errors
    async def async_browse_object(self, object_id: str) -> BrowseMediaSource:
        """Return the contents of a DLNA container by ObjectID."""
        assert self._device

        base_object = await self._device.async_browse_metadata(
            object_id, metadata_filter=DLNA_BROWSE_FILTER
        )

        children = await self._device.async_browse_direct_children(
            object_id,
            metadata_filter=DLNA_BROWSE_FILTER,
            sort_criteria=DLNA_SORT_CRITERIA,
        )

        return self._didl_to_media_source(base_object, children)

    @catch_request_errors
    async def async_browse_search(self, query: str) -> BrowseMediaSource:
        """Return all media items found by the query string."""
        assert self._device

        result = await self._device.async_search_directory(
            container_id=ROOT_OBJECT_ID,
            search_criteria=query,
            metadata_filter=DLNA_BROWSE_FILTER,
        )

        children = [
            self._didl_to_media_source(child)
            for child in result.result
            if isinstance(child, didl_lite.DidlObject)
        ]

        media_source = BrowseMediaSource(
            domain=DOMAIN,
            identifier=self._make_identifier(Action.SEARCH, query),
            media_class=MEDIA_CLASS_DIRECTORY,
            media_content_type="",
            title="Search results",
            can_play=False,
            can_expand=True,
            children=children,
        )

        media_source.calculate_children_class()

        return media_source

    def _didl_to_play_media(self, item: didl_lite.DidlObject) -> DidlPlayMedia:
        """Return the first playable resource from a DIDL-Lite object."""
        assert self._device

        if not item.res:
            LOGGER.debug("Object %s has no resources", item.id)
            raise Unresolvable("Object has no resources")

        for resource in item.res:
            if not resource.uri:
                continue
            if mime_type := _resource_mime_type(resource):
                url = self._device.get_absolute_url(resource.uri)
                LOGGER.debug("Resolved to url %s MIME %s", url, mime_type)
                return DidlPlayMedia(url, mime_type, item)

        LOGGER.debug("Object %s has no playable resources", item.id)
        raise Unresolvable("Object has no playable resources")

    def _didl_to_media_source(
        self,
        item: didl_lite.DidlObject,
        browsed_children: DmsDevice.BrowseResult | None = None,
    ) -> BrowseMediaSource:
        """Convert a DIDL-Lite object to a browse media source."""
        children: list[BrowseMediaSource] | None = None

        if browsed_children:
            children = [
                self._didl_to_media_source(child)
                for child in browsed_children.result
                if isinstance(child, didl_lite.DidlObject)
            ]

        # Can expand if it has children (even if we don't have them yet), or its
        # a container type. Otherwise the front-end will try to play it (even if
        # can_play is False).
        try:
            child_count = int(item.child_count)
        except (AttributeError, TypeError, ValueError):
            child_count = 0
        can_expand = (
            bool(children) or child_count > 0 or isinstance(item, didl_lite.Container)
        )

        # Can play if item has any resource that can be streamed over the network
        can_play = any(_resource_is_streaming(res) for res in item.res)

        # Use server name for root object, not "root"
        title = self.name if item.id == ROOT_OBJECT_ID else item.title

        mime_type = _resource_mime_type(item.res[0]) if item.res else None
        media_content_type = mime_type or item.upnp_class

        media_source = BrowseMediaSource(
            domain=DOMAIN,
            identifier=self._make_identifier(Action.OBJECT, item.id),
            media_class=MEDIA_CLASS_MAP.get(item.upnp_class, ""),
            media_content_type=media_content_type,
            title=title,
            can_play=can_play,
            can_expand=can_expand,
            children=children,
            thumbnail=self._didl_thumbnail_url(item),
        )

        media_source.calculate_children_class()

        return media_source

    def _didl_thumbnail_url(self, item: didl_lite.DidlObject) -> str | None:
        """Return absolute URL of a thumbnail for a DIDL-Lite object.

        Some objects have the thumbnail in albumArtURI, others in an image
        resource.
        """
        assert self._device

        # Based on DmrDevice.media_image_url from async_upnp_client.
        if album_art_uri := getattr(item, "album_art_uri", None):
            return self._device.get_absolute_url(album_art_uri)

        for resource in item.res:
            if not resource.protocol_info or not resource.uri:
                continue
            if resource.protocol_info.startswith("http-get:*:image/"):
                return self._device.get_absolute_url(resource.uri)

        return None

    def _make_identifier(self, action: Action, object_id: str) -> str:
        """Make an identifier for BrowseMediaSource."""
        return f"{self.source_id}/{action}{object_id}"


class Action(StrEnum):
    """Actions that can be specified in a DMS media-source identifier."""

    OBJECT = PATH_OBJECT_ID_FLAG
    PATH = PATH_SEP
    SEARCH = PATH_SEARCH_FLAG


def _parse_identifier(identifier: str | None) -> tuple[Action | None, str]:
    """Parse the media identifier component of a media-source URI."""
    if not identifier:
        return None, ""
    if identifier.startswith(PATH_OBJECT_ID_FLAG):
        return Action.OBJECT, identifier[1:]
    if identifier.startswith(PATH_SEP):
        return Action.PATH, identifier[1:]
    if identifier.startswith(PATH_SEARCH_FLAG):
        return Action.SEARCH, identifier[1:]
    return Action.PATH, identifier


def _resource_is_streaming(resource: didl_lite.Resource) -> bool:
    """Determine if a resource can be streamed across a network."""
    # Err on the side of "True" if the protocol info is not available
    if not resource.protocol_info:
        return True
    protocol = resource.protocol_info.split(":")[0].lower()
    return protocol.lower() in STREAMABLE_PROTOCOLS


def _resource_mime_type(resource: didl_lite.Resource) -> str | None:
    """Return the MIME type of a resource, if specified."""
    # This is the contentFormat portion of the ProtocolInfo for an http-get stream
    if not resource.protocol_info:
        return None
    try:
        protocol, _, content_format, _ = resource.protocol_info.split(":", 3)
    except ValueError:
        return None
    if protocol.lower() in STREAMABLE_PROTOCOLS:
        return content_format
    return None


def _esc_quote(contents: str) -> str:
    """Escape string contents for DLNA search quoted values.

    See ContentDirectory:v4, section 4.1.2.
    """
    return contents.replace("\\", "\\\\").replace('"', '\\"')
