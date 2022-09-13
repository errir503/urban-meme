"""Decorator service for the media_player.play_media service."""
import logging

import voluptuous as vol
from youtube_dl import YoutubeDL
from youtube_dl.utils import DownloadError, ExtractorError

from homeassistant.components.media_player import (
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    MEDIA_PLAYER_PLAY_MEDIA_SCHEMA,
    SERVICE_PLAY_MEDIA,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

CONF_CUSTOMIZE_ENTITIES = "customize"
CONF_DEFAULT_STREAM_QUERY = "default_query"

DEFAULT_STREAM_QUERY = "best"
DOMAIN = "media_extractor"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_DEFAULT_STREAM_QUERY): cv.string,
                vol.Optional(CONF_CUSTOMIZE_ENTITIES): vol.Schema(
                    {cv.entity_id: vol.Schema({cv.string: cv.string})}
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the media extractor service."""

    def play_media(call: ServiceCall) -> None:
        """Get stream URL and send it to the play_media service."""
        MediaExtractor(hass, config[DOMAIN], call.data).extract_and_send()

    hass.services.register(
        DOMAIN,
        SERVICE_PLAY_MEDIA,
        play_media,
        schema=cv.make_entity_service_schema(MEDIA_PLAYER_PLAY_MEDIA_SCHEMA),
    )

    return True


class MEDownloadException(Exception):
    """Media extractor download exception."""


class MEQueryException(Exception):
    """Media extractor query exception."""


class MediaExtractor:
    """Class which encapsulates all extraction logic."""

    def __init__(self, hass, component_config, call_data):
        """Initialize media extractor."""
        self.hass = hass
        self.config = component_config
        self.call_data = call_data

    def get_media_url(self):
        """Return media content url."""
        return self.call_data.get(ATTR_MEDIA_CONTENT_ID)

    def get_entities(self):
        """Return list of entities."""
        return self.call_data.get(ATTR_ENTITY_ID, [])

    def extract_and_send(self):
        """Extract exact stream format for each entity_id and play it."""
        try:
            stream_selector = self.get_stream_selector()
        except MEDownloadException:
            _LOGGER.error(
                "Could not retrieve data for the URL: %s", self.get_media_url()
            )
        else:
            if not (entities := self.get_entities()):
                self.call_media_player_service(stream_selector, None)

            for entity_id in entities:
                self.call_media_player_service(stream_selector, entity_id)

    def get_stream_selector(self):
        """Return format selector for the media URL."""
        ydl = YoutubeDL({"quiet": True, "logger": _LOGGER})

        try:
            all_media = ydl.extract_info(self.get_media_url(), process=False)
        except DownloadError as err:
            # This exception will be logged by youtube-dl itself
            raise MEDownloadException() from err

        if "entries" in all_media:
            _LOGGER.warning("Playlists are not supported, looking for the first video")
            entries = list(all_media["entries"])
            if entries:
                selected_media = entries[0]
            else:
                _LOGGER.error("Playlist is empty")
                raise MEDownloadException()
        else:
            selected_media = all_media

        def stream_selector(query):
            """Find stream URL that matches query."""
            try:
                ydl.params["format"] = query
                requested_stream = ydl.process_ie_result(selected_media, download=False)
            except (ExtractorError, DownloadError) as err:
                _LOGGER.error("Could not extract stream for the query: %s", query)
                raise MEQueryException() from err

            return requested_stream["url"]

        return stream_selector

    def call_media_player_service(self, stream_selector, entity_id):
        """Call Media player play_media service."""
        stream_query = self.get_stream_query_for_entity(entity_id)

        try:
            stream_url = stream_selector(stream_query)
        except MEQueryException:
            _LOGGER.error("Wrong query format: %s", stream_query)
            return
        else:
            data = {k: v for k, v in self.call_data.items() if k != ATTR_ENTITY_ID}
            data[ATTR_MEDIA_CONTENT_ID] = stream_url

            if entity_id:
                data[ATTR_ENTITY_ID] = entity_id

            self.hass.async_create_task(
                self.hass.services.async_call(
                    MEDIA_PLAYER_DOMAIN, SERVICE_PLAY_MEDIA, data
                )
            )

    def get_stream_query_for_entity(self, entity_id):
        """Get stream format query for entity."""
        default_stream_query = self.config.get(
            CONF_DEFAULT_STREAM_QUERY, DEFAULT_STREAM_QUERY
        )

        if entity_id:
            media_content_type = self.call_data.get(ATTR_MEDIA_CONTENT_TYPE)

            return (
                self.config.get(CONF_CUSTOMIZE_ENTITIES, {})
                .get(entity_id, {})
                .get(media_content_type, default_stream_query)
            )

        return default_stream_query
