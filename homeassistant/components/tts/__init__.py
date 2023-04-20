"""Provide functionality for TTS."""
from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
from http import HTTPStatus
import io
import logging
import mimetypes
import os
import re
from typing import Any, TypedDict

from aiohttp import web
import mutagen
from mutagen.id3 import ID3, TextFrame as ID3Text
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.const import PLATFORM_FORMAT
from homeassistant.core import HassJob, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.network import get_url
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import language as language_util

from .const import (
    ATTR_CACHE,
    ATTR_LANGUAGE,
    ATTR_MESSAGE,
    ATTR_OPTIONS,
    CONF_BASE_URL,
    CONF_CACHE,
    CONF_CACHE_DIR,
    CONF_TIME_MEMORY,
    DEFAULT_CACHE,
    DEFAULT_CACHE_DIR,
    DEFAULT_TIME_MEMORY,
    DOMAIN,
    TtsAudioType,
)
from .legacy import PLATFORM_SCHEMA, PLATFORM_SCHEMA_BASE, Provider, async_setup_legacy
from .media_source import generate_media_source_id, media_source_id_to_kwargs

__all__ = [
    "async_get_media_source_audio",
    "async_resolve_engine",
    "async_support_options",
    "ATTR_AUDIO_OUTPUT",
    "CONF_LANG",
    "DEFAULT_CACHE_DIR",
    "generate_media_source_id",
    "get_base_url",
    "PLATFORM_SCHEMA_BASE",
    "PLATFORM_SCHEMA",
    "Provider",
    "TtsAudioType",
]

_LOGGER = logging.getLogger(__name__)

ATTR_PLATFORM = "platform"
ATTR_AUDIO_OUTPUT = "audio_output"

CONF_LANG = "language"

BASE_URL_KEY = "tts_base_url"

SERVICE_CLEAR_CACHE = "clear_cache"

_RE_VOICE_FILE = re.compile(r"([a-f0-9]{40})_([^_]+)_([^_]+)_([a-z_]+)\.[a-z0-9]{3,4}")
KEY_PATTERN = "{0}_{1}_{2}_{3}"

SCHEMA_SERVICE_CLEAR_CACHE = vol.Schema({})


class TTSCache(TypedDict):
    """Cached TTS file."""

    filename: str
    voice: bytes
    pending: asyncio.Task | None


@callback
def async_resolve_engine(hass: HomeAssistant, engine: str | None) -> str | None:
    """Resolve engine.

    Returns None if no engines found or invalid engine passed in.
    """
    manager: SpeechManager = hass.data[DOMAIN]

    if engine is not None:
        if engine not in manager.providers:
            return None
        return engine

    if not manager.providers:
        return None

    if "cloud" in manager.providers:
        return "cloud"

    return next(iter(manager.providers))


async def async_support_options(
    hass: HomeAssistant,
    engine: str,
    language: str | None = None,
    options: dict | None = None,
) -> bool:
    """Return if an engine supports options."""
    manager: SpeechManager = hass.data[DOMAIN]
    try:
        manager.process_options(engine, language, options)
    except HomeAssistantError:
        return False

    return True


async def async_get_media_source_audio(
    hass: HomeAssistant,
    media_source_id: str,
) -> tuple[str, bytes]:
    """Get TTS audio as extension, data."""
    manager: SpeechManager = hass.data[DOMAIN]
    return await manager.async_get_tts_audio(
        **media_source_id_to_kwargs(media_source_id),
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up TTS."""
    websocket_api.async_register_command(hass, websocket_list_engines)
    websocket_api.async_register_command(hass, websocket_list_engine_voices)

    # Legacy config options
    conf = config[DOMAIN][0] if config.get(DOMAIN) else {}
    use_cache: bool = conf.get(CONF_CACHE, DEFAULT_CACHE)
    cache_dir: str = conf.get(CONF_CACHE_DIR, DEFAULT_CACHE_DIR)
    time_memory: int = conf.get(CONF_TIME_MEMORY, DEFAULT_TIME_MEMORY)
    base_url: str | None = conf.get(CONF_BASE_URL)
    if base_url is not None:
        _LOGGER.warning(
            "TTS base_url option is deprecated. Configure internal/external URL"
            " instead"
        )
    hass.data[BASE_URL_KEY] = base_url

    tts = SpeechManager(hass, use_cache, cache_dir, time_memory, base_url)

    try:
        await tts.async_init_cache()
    except (HomeAssistantError, KeyError):
        _LOGGER.exception("Error on cache init")
        return False

    hass.data[DOMAIN] = tts
    hass.http.register_view(TextToSpeechView(tts))
    hass.http.register_view(TextToSpeechUrlView(tts))

    platform_setups = await async_setup_legacy(hass, config)

    if platform_setups:
        await asyncio.wait([asyncio.create_task(setup) for setup in platform_setups])

    async def async_clear_cache_handle(service: ServiceCall) -> None:
        """Handle clear cache service call."""
        await tts.async_clear_cache()

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_CACHE,
        async_clear_cache_handle,
        schema=SCHEMA_SERVICE_CLEAR_CACHE,
    )

    return True


def _hash_options(options: dict) -> str:
    """Hashes an options dictionary."""
    opts_hash = hashlib.blake2s(digest_size=5)
    for key, value in sorted(options.items()):
        opts_hash.update(str(key).encode())
        opts_hash.update(str(value).encode())

    return opts_hash.hexdigest()


class SpeechManager:
    """Representation of a speech store."""

    def __init__(
        self,
        hass: HomeAssistant,
        use_cache: bool,
        cache_dir: str,
        time_memory: int,
        base_url: str | None,
    ) -> None:
        """Initialize a speech store."""
        self.hass = hass
        self.providers: dict[str, Provider] = {}

        self.use_cache = use_cache
        self.cache_dir = cache_dir
        self.time_memory = time_memory
        self.base_url = base_url
        self.file_cache: dict[str, str] = {}
        self.mem_cache: dict[str, TTSCache] = {}

    async def async_init_cache(self) -> None:
        """Init config folder and load file cache."""
        try:
            self.cache_dir = await self.hass.async_add_executor_job(
                _init_tts_cache_dir, self.hass, self.cache_dir
            )
        except OSError as err:
            raise HomeAssistantError(f"Can't init cache dir {err}") from err

        try:
            cache_files = await self.hass.async_add_executor_job(
                _get_cache_files, self.cache_dir
            )
        except OSError as err:
            raise HomeAssistantError(f"Can't read cache dir {err}") from err

        if cache_files:
            self.file_cache.update(cache_files)

    async def async_clear_cache(self) -> None:
        """Read file cache and delete files."""
        self.mem_cache = {}

        def remove_files() -> None:
            """Remove files from filesystem."""
            for filename in self.file_cache.values():
                try:
                    os.remove(os.path.join(self.cache_dir, filename))
                except OSError as err:
                    _LOGGER.warning("Can't remove cache file '%s': %s", filename, err)

        await self.hass.async_add_executor_job(remove_files)
        self.file_cache = {}

    @callback
    def async_register_legacy_engine(
        self, engine: str, provider: Provider, config: ConfigType
    ) -> None:
        """Register a TTS provider."""
        provider.hass = self.hass
        if provider.name is None:
            provider.name = engine
        self.providers[engine] = provider

        self.hass.config.components.add(
            PLATFORM_FORMAT.format(domain=engine, platform=DOMAIN)
        )

    @callback
    def process_options(
        self,
        engine: str,
        language: str | None = None,
        options: dict | None = None,
    ) -> tuple[str, dict | None]:
        """Validate and process options."""
        if (provider := self.providers.get(engine)) is None:
            raise HomeAssistantError(f"Provider {engine} not found")

        # Languages
        language = language or provider.default_language

        if language is None or provider.supported_languages is None:
            raise HomeAssistantError(f"Not supported language {language}")

        if language not in provider.supported_languages:
            language_matches = language_util.matches(
                language, provider.supported_languages
            )
            if language_matches:
                # Choose best match
                language = language_matches[0]
            else:
                raise HomeAssistantError(f"Not supported language {language}")

        # Options
        if (default_options := provider.default_options) and options:
            merged_options = dict(default_options)
            merged_options.update(options)
            options = merged_options
        if not options:
            options = None if default_options is None else dict(default_options)

        if options is not None:
            supported_options = provider.supported_options or []
            invalid_opts = [
                opt_name for opt_name in options if opt_name not in supported_options
            ]
            if invalid_opts:
                raise HomeAssistantError(f"Invalid options found: {invalid_opts}")

        return language, options

    async def async_get_url_path(
        self,
        engine: str,
        message: str,
        cache: bool | None = None,
        language: str | None = None,
        options: dict | None = None,
    ) -> str:
        """Get URL for play message.

        This method is a coroutine.
        """
        language, options = self.process_options(engine, language, options)
        cache_key = self._generate_cache_key(message, language, options, engine)
        use_cache = cache if cache is not None else self.use_cache

        # Is speech already in memory
        if cache_key in self.mem_cache:
            filename = self.mem_cache[cache_key]["filename"]
        # Is file store in file cache
        elif use_cache and cache_key in self.file_cache:
            filename = self.file_cache[cache_key]
            self.hass.async_create_task(self._async_file_to_mem(cache_key))
        # Load speech from provider into memory
        else:
            filename = await self._async_get_tts_audio(
                engine,
                cache_key,
                message,
                use_cache,
                language,
                options,
            )

        return f"/api/tts_proxy/{filename}"

    async def async_get_tts_audio(
        self,
        engine: str,
        message: str,
        cache: bool | None = None,
        language: str | None = None,
        options: dict | None = None,
    ) -> tuple[str, bytes]:
        """Fetch TTS audio."""
        language, options = self.process_options(engine, language, options)
        cache_key = self._generate_cache_key(message, language, options, engine)
        use_cache = cache if cache is not None else self.use_cache

        # If we have the file, load it into memory if necessary
        if cache_key not in self.mem_cache:
            if use_cache and cache_key in self.file_cache:
                await self._async_file_to_mem(cache_key)
            else:
                await self._async_get_tts_audio(
                    engine, cache_key, message, use_cache, language, options
                )

        extension = os.path.splitext(self.mem_cache[cache_key]["filename"])[1][1:]
        cached = self.mem_cache[cache_key]
        if pending := cached.get("pending"):
            await pending
            cached = self.mem_cache[cache_key]
        return extension, cached["voice"]

    @callback
    def _generate_cache_key(
        self,
        message: str,
        language: str,
        options: dict | None,
        engine: str,
    ) -> str:
        """Generate a cache key for a message."""
        options_key = _hash_options(options) if options else "-"
        msg_hash = hashlib.sha1(bytes(message, "utf-8")).hexdigest()
        return KEY_PATTERN.format(
            msg_hash, language.replace("_", "-"), options_key, engine
        ).lower()

    async def _async_get_tts_audio(
        self,
        engine: str,
        cache_key: str,
        message: str,
        cache: bool,
        language: str,
        options: dict | None,
    ) -> str:
        """Receive TTS, store for view in cache and return filename.

        This method is a coroutine.
        """
        provider = self.providers[engine]

        if options is not None and ATTR_AUDIO_OUTPUT in options:
            expected_extension = options[ATTR_AUDIO_OUTPUT]
        else:
            expected_extension = None

        async def get_tts_data() -> str:
            """Handle data available."""
            extension, data = await provider.async_get_tts_audio(
                message, language, options
            )

            if data is None or extension is None:
                raise HomeAssistantError(f"No TTS from {engine} for '{message}'")

            # Create file infos
            filename = f"{cache_key}.{extension}".lower()

            # Validate filename
            if not _RE_VOICE_FILE.match(filename):
                raise HomeAssistantError(
                    f"TTS filename '{filename}' from {engine} is invalid!"
                )

            # Save to memory
            if extension == "mp3":
                data = self.write_tags(
                    filename, data, provider, message, language, options
                )
            self._async_store_to_memcache(cache_key, filename, data)

            if cache:
                self.hass.async_create_task(
                    self._async_save_tts_audio(cache_key, filename, data)
                )

            return filename

        audio_task = self.hass.async_create_task(get_tts_data())

        if expected_extension is None:
            return await audio_task

        def handle_error(_future: asyncio.Future) -> None:
            """Handle error."""
            if audio_task.exception():
                self.mem_cache.pop(cache_key, None)

        audio_task.add_done_callback(handle_error)

        filename = f"{cache_key}.{expected_extension}".lower()
        self.mem_cache[cache_key] = {
            "filename": filename,
            "voice": b"",
            "pending": audio_task,
        }
        return filename

    async def _async_save_tts_audio(
        self, cache_key: str, filename: str, data: bytes
    ) -> None:
        """Store voice data to file and file_cache.

        This method is a coroutine.
        """
        voice_file = os.path.join(self.cache_dir, filename)

        def save_speech() -> None:
            """Store speech to filesystem."""
            with open(voice_file, "wb") as speech:
                speech.write(data)

        try:
            await self.hass.async_add_executor_job(save_speech)
            self.file_cache[cache_key] = filename
        except OSError as err:
            _LOGGER.error("Can't write %s: %s", filename, err)

    async def _async_file_to_mem(self, cache_key: str) -> None:
        """Load voice from file cache into memory.

        This method is a coroutine.
        """
        if not (filename := self.file_cache.get(cache_key)):
            raise HomeAssistantError(f"Key {cache_key} not in file cache!")

        voice_file = os.path.join(self.cache_dir, filename)

        def load_speech() -> bytes:
            """Load a speech from filesystem."""
            with open(voice_file, "rb") as speech:
                return speech.read()

        try:
            data = await self.hass.async_add_executor_job(load_speech)
        except OSError as err:
            del self.file_cache[cache_key]
            raise HomeAssistantError(f"Can't read {voice_file}") from err

        self._async_store_to_memcache(cache_key, filename, data)

    @callback
    def _async_store_to_memcache(
        self, cache_key: str, filename: str, data: bytes
    ) -> None:
        """Store data to memcache and set timer to remove it."""
        self.mem_cache[cache_key] = {
            "filename": filename,
            "voice": data,
            "pending": None,
        }

        @callback
        def async_remove_from_mem(_: datetime) -> None:
            """Cleanup memcache."""
            self.mem_cache.pop(cache_key, None)

        async_call_later(
            self.hass,
            self.time_memory,
            HassJob(
                async_remove_from_mem,
                name="tts remove_from_mem",
                cancel_on_shutdown=True,
            ),
        )

    async def async_read_tts(self, filename: str) -> tuple[str | None, bytes]:
        """Read a voice file and return binary.

        This method is a coroutine.
        """
        if not (record := _RE_VOICE_FILE.match(filename.lower())):
            raise HomeAssistantError("Wrong tts file format!")

        cache_key = KEY_PATTERN.format(
            record.group(1), record.group(2), record.group(3), record.group(4)
        )

        if cache_key not in self.mem_cache:
            if cache_key not in self.file_cache:
                raise HomeAssistantError(f"{cache_key} not in cache!")
            await self._async_file_to_mem(cache_key)

        content, _ = mimetypes.guess_type(filename)
        cached = self.mem_cache[cache_key]
        if pending := cached.get("pending"):
            await pending
            cached = self.mem_cache[cache_key]
        return content, cached["voice"]

    @staticmethod
    def write_tags(
        filename: str,
        data: bytes,
        provider: Provider,
        message: str,
        language: str,
        options: dict | None,
    ) -> bytes:
        """Write ID3 tags to file.

        Async friendly.
        """

        data_bytes = io.BytesIO(data)
        data_bytes.name = filename
        data_bytes.seek(0)

        album = provider.name
        artist = language

        if options is not None and (voice := options.get("voice")) is not None:
            artist = voice

        try:
            tts_file = mutagen.File(data_bytes)
            if tts_file is not None:
                if not tts_file.tags:
                    tts_file.add_tags()
                if isinstance(tts_file.tags, ID3):
                    tts_file["artist"] = ID3Text(
                        encoding=3,
                        text=artist,  # type: ignore[no-untyped-call]
                    )
                    tts_file["album"] = ID3Text(
                        encoding=3,
                        text=album,  # type: ignore[no-untyped-call]
                    )
                    tts_file["title"] = ID3Text(
                        encoding=3,
                        text=message,  # type: ignore[no-untyped-call]
                    )
                else:
                    tts_file["artist"] = artist
                    tts_file["album"] = album
                    tts_file["title"] = message
                tts_file.save(data_bytes)
        except mutagen.MutagenError as err:
            _LOGGER.error("ID3 tag error: %s", err)

        return data_bytes.getvalue()


def _init_tts_cache_dir(hass: HomeAssistant, cache_dir: str) -> str:
    """Init cache folder."""
    if not os.path.isabs(cache_dir):
        cache_dir = hass.config.path(cache_dir)
    if not os.path.isdir(cache_dir):
        _LOGGER.info("Create cache dir %s", cache_dir)
        os.mkdir(cache_dir)
    return cache_dir


def _get_cache_files(cache_dir: str) -> dict[str, str]:
    """Return a dict of given engine files."""
    cache = {}

    folder_data = os.listdir(cache_dir)
    for file_data in folder_data:
        if record := _RE_VOICE_FILE.match(file_data):
            key = KEY_PATTERN.format(
                record.group(1), record.group(2), record.group(3), record.group(4)
            )
            cache[key.lower()] = file_data.lower()
    return cache


class TextToSpeechUrlView(HomeAssistantView):
    """TTS view to get a url to a generated speech file."""

    requires_auth = True
    url = "/api/tts_get_url"
    name = "api:tts:geturl"

    def __init__(self, tts: SpeechManager) -> None:
        """Initialize a tts view."""
        self.tts = tts

    async def post(self, request: web.Request) -> web.Response:
        """Generate speech and provide url."""
        try:
            data = await request.json()
        except ValueError:
            return self.json_message("Invalid JSON specified", HTTPStatus.BAD_REQUEST)
        if not data.get(ATTR_PLATFORM) and data.get(ATTR_MESSAGE):
            return self.json_message(
                "Must specify platform and message", HTTPStatus.BAD_REQUEST
            )

        p_type = data[ATTR_PLATFORM]
        message = data[ATTR_MESSAGE]
        cache = data.get(ATTR_CACHE)
        language = data.get(ATTR_LANGUAGE)
        options = data.get(ATTR_OPTIONS)

        try:
            path = await self.tts.async_get_url_path(
                p_type, message, cache=cache, language=language, options=options
            )
        except HomeAssistantError as err:
            _LOGGER.error("Error on init tts: %s", err)
            return self.json({"error": err}, HTTPStatus.BAD_REQUEST)

        base = self.tts.base_url or get_url(self.tts.hass)
        url = base + path

        return self.json({"url": url, "path": path})


class TextToSpeechView(HomeAssistantView):
    """TTS view to serve a speech audio."""

    requires_auth = False
    url = "/api/tts_proxy/{filename}"
    name = "api:tts_speech"

    def __init__(self, tts: SpeechManager) -> None:
        """Initialize a tts view."""
        self.tts = tts

    async def get(self, request: web.Request, filename: str) -> web.Response:
        """Start a get request."""
        try:
            content, data = await self.tts.async_read_tts(filename)
        except HomeAssistantError as err:
            _LOGGER.error("Error on load tts: %s", err)
            return web.Response(status=HTTPStatus.NOT_FOUND)

        return web.Response(body=data, content_type=content)


def get_base_url(hass: HomeAssistant) -> str:
    """Get base URL."""
    return hass.data[BASE_URL_KEY] or get_url(hass)


@websocket_api.websocket_command(
    {
        "type": "tts/engine/list",
        vol.Optional("language"): str,
    }
)
@callback
def websocket_list_engines(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """List text to speech engines and, optionally, if they support a given language."""
    manager: SpeechManager = hass.data[DOMAIN]

    language = msg.get("language")
    providers = []
    for engine_id, provider in manager.providers.items():
        provider_info: dict[str, Any] = {"engine_id": engine_id}
        if language:
            provider_info["language_supported"] = bool(
                language_util.matches(language, provider.supported_languages)
            )
        providers.append(provider_info)

    connection.send_message(
        websocket_api.result_message(msg["id"], {"providers": providers})
    )


@websocket_api.websocket_command(
    {
        "type": "tts/engine/voices",
        vol.Required("engine_id"): str,
        vol.Required("language"): str,
    }
)
@callback
def websocket_list_engine_voices(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """List voices for a given language."""
    engine_id = msg["engine_id"]
    language = msg["language"]

    manager: SpeechManager = hass.data[DOMAIN]
    engine = manager.providers.get(engine_id)

    if not engine:
        connection.send_error(
            msg["id"],
            websocket_api.const.ERR_NOT_FOUND,
            f"tts engine {engine_id} not found",
        )
        return

    voices = {"voices": engine.async_get_supported_voices(language)}

    connection.send_message(websocket_api.result_message(msg["id"], voices))
