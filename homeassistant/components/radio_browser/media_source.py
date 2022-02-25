"""Expose Radio Browser as a media source."""
from __future__ import annotations

import mimetypes

from radios import FilterBy, Order, RadioBrowser, Station

from homeassistant.components.media_player.const import (
    MEDIA_CLASS_CHANNEL,
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_MUSIC,
    MEDIA_TYPE_MUSIC,
)
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

CODEC_TO_MIMETYPE = {
    "MP3": "audio/mpeg",
    "AAC": "audio/aac",
    "AAC+": "audio/aac",
    "OGG": "application/ogg",
}


async def async_get_media_source(hass: HomeAssistant) -> RadioMediaSource:
    """Set up Radio Browser media source."""
    # Radio browser support only a single config entry
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    radios = hass.data[DOMAIN]

    return RadioMediaSource(hass, radios, entry)


class RadioMediaSource(MediaSource):
    """Provide Radio stations as media sources."""

    name = "Radio Browser"

    def __init__(
        self, hass: HomeAssistant, radios: RadioBrowser, entry: ConfigEntry
    ) -> None:
        """Initialize CameraMediaSource."""
        super().__init__(DOMAIN)
        self.hass = hass
        self.entry = entry
        self.radios = radios

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve selected Radio station to a streaming URL."""
        station = await self.radios.station(uuid=item.identifier)
        if not station:
            raise BrowseError("Radio station is no longer available")

        if not (mime_type := self._async_get_station_mime_type(station)):
            raise BrowseError("Could not determine stream type of radio station")

        # Register "click" with Radio Browser
        await self.radios.station_click(uuid=station.uuid)

        return PlayMedia(station.url, mime_type)

    async def async_browse_media(
        self,
        item: MediaSourceItem,
    ) -> BrowseMediaSource:
        """Return media."""
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MEDIA_CLASS_CHANNEL,
            media_content_type=MEDIA_TYPE_MUSIC,
            title=self.entry.title,
            can_play=False,
            can_expand=True,
            children_media_class=MEDIA_CLASS_DIRECTORY,
            children=[
                *await self._async_build_popular(item),
                *await self._async_build_by_tag(item),
                *await self._async_build_by_language(item),
                *await self._async_build_by_country(item),
            ],
        )

    @callback
    @staticmethod
    def _async_get_station_mime_type(station: Station) -> str | None:
        """Determine mime type of a radio station."""
        mime_type = CODEC_TO_MIMETYPE.get(station.codec)
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(station.url)
        return mime_type

    @callback
    def _async_build_stations(self, stations: list[Station]) -> list[BrowseMediaSource]:
        """Build list of media sources from radio stations."""
        items: list[BrowseMediaSource] = []

        for station in stations:
            if station.codec == "UNKNOWN" or not (
                mime_type := self._async_get_station_mime_type(station)
            ):
                continue

            items.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=station.uuid,
                    media_class=MEDIA_CLASS_MUSIC,
                    media_content_type=mime_type,
                    title=station.name,
                    can_play=True,
                    can_expand=False,
                    thumbnail=station.favicon,
                )
            )

        return items

    async def _async_build_by_country(
        self, item: MediaSourceItem
    ) -> list[BrowseMediaSource]:
        """Handle browsing radio stations by country."""
        category, _, country_code = (item.identifier or "").partition("/")
        if country_code:
            stations = await self.radios.stations(
                filter_by=FilterBy.COUNTRY_CODE_EXACT,
                filter_term=country_code,
                hide_broken=True,
                order=Order.NAME,
                reverse=False,
            )
            return self._async_build_stations(stations)

        # We show country in the root additionally, when there is no item
        if not item.identifier or category == "country":
            countries = await self.radios.countries(order=Order.NAME)
            return [
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"country/{country.code}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    media_content_type=MEDIA_TYPE_MUSIC,
                    title=country.name,
                    can_play=False,
                    can_expand=True,
                    thumbnail=country.favicon,
                )
                for country in countries
            ]

        return []

    async def _async_build_by_language(
        self, item: MediaSourceItem
    ) -> list[BrowseMediaSource]:
        """Handle browsing radio stations by language."""
        category, _, language = (item.identifier or "").partition("/")
        if category == "language" and language:
            stations = await self.radios.stations(
                filter_by=FilterBy.LANGUAGE_EXACT,
                filter_term=language,
                hide_broken=True,
                order=Order.NAME,
                reverse=False,
            )
            return self._async_build_stations(stations)

        if category == "language":
            languages = await self.radios.languages(order=Order.NAME, hide_broken=True)
            return [
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"language/{language.code}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    media_content_type=MEDIA_TYPE_MUSIC,
                    title=language.name,
                    can_play=False,
                    can_expand=True,
                    thumbnail=language.favicon,
                )
                for language in languages
            ]

        if not item.identifier:
            return [
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier="language",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    media_content_type=MEDIA_TYPE_MUSIC,
                    title="By Language",
                    can_play=False,
                    can_expand=True,
                )
            ]

        return []

    async def _async_build_popular(
        self, item: MediaSourceItem
    ) -> list[BrowseMediaSource]:
        """Handle browsing popular radio stations."""
        if item.identifier == "popular":
            stations = await self.radios.stations(
                hide_broken=True,
                limit=250,
                order=Order.CLICK_COUNT,
                reverse=True,
            )
            return self._async_build_stations(stations)

        if not item.identifier:
            return [
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier="popular",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    media_content_type=MEDIA_TYPE_MUSIC,
                    title="Popular",
                    can_play=False,
                    can_expand=True,
                )
            ]

        return []

    async def _async_build_by_tag(
        self, item: MediaSourceItem
    ) -> list[BrowseMediaSource]:
        """Handle browsing radio stations by tags."""
        category, _, tag = (item.identifier or "").partition("/")
        if category == "tag" and tag:
            stations = await self.radios.stations(
                filter_by=FilterBy.TAG_EXACT,
                filter_term=tag,
                hide_broken=True,
                order=Order.NAME,
                reverse=False,
            )
            return self._async_build_stations(stations)

        if category == "tag":
            tags = await self.radios.tags(
                hide_broken=True,
                limit=100,
                order=Order.STATION_COUNT,
                reverse=True,
            )

            # Now we have the top tags, reorder them by name
            tags.sort(key=lambda tag: tag.name)

            return [
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"tag/{tag.name}",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    media_content_type=MEDIA_TYPE_MUSIC,
                    title=tag.name.title(),
                    can_play=False,
                    can_expand=True,
                )
                for tag in tags
            ]

        if not item.identifier:
            return [
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier="tag",
                    media_class=MEDIA_CLASS_DIRECTORY,
                    media_content_type=MEDIA_TYPE_MUSIC,
                    title="By Category",
                    can_play=False,
                    can_expand=True,
                )
            ]

        return []
