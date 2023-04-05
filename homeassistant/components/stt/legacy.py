"""Handle legacy speech to text platforms."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_per_platform, discovery
from homeassistant.helpers.typing import ConfigType
from homeassistant.setup import async_prepare_setup_platform

from .const import (
    DOMAIN,
    AudioBitRates,
    AudioChannels,
    AudioCodecs,
    AudioFormats,
    AudioSampleRates,
    SpeechResultState,
)

_LOGGER = logging.getLogger(__name__)


@callback
def async_get_provider(
    hass: HomeAssistant, domain: str | None = None
) -> Provider | None:
    """Return provider."""
    if domain:
        return hass.data[DOMAIN].get(domain)

    if not hass.data[DOMAIN]:
        return None

    if "cloud" in hass.data[DOMAIN]:
        return hass.data[DOMAIN]["cloud"]

    return next(iter(hass.data[DOMAIN].values()))


@callback
def async_setup_legacy(
    hass: HomeAssistant, config: ConfigType
) -> list[Coroutine[Any, Any, None]]:
    """Set up legacy speech to text providers."""
    providers = hass.data[DOMAIN] = {}

    async def async_setup_platform(p_type, p_config=None, discovery_info=None):
        """Set up a TTS platform."""
        if p_config is None:
            p_config = {}

        platform = await async_prepare_setup_platform(hass, config, DOMAIN, p_type)
        if platform is None:
            _LOGGER.error("Unknown speech to text platform specified")
            return

        try:
            provider = await platform.async_get_engine(hass, p_config, discovery_info)

            provider.name = p_type
            provider.hass = hass

            providers[provider.name] = provider
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Error setting up platform: %s", p_type)
            return

    # Add discovery support
    async def async_platform_discovered(platform, info):
        """Handle for discovered platform."""
        await async_setup_platform(platform, discovery_info=info)

    discovery.async_listen_platform(hass, DOMAIN, async_platform_discovered)

    return [
        async_setup_platform(p_type, p_config)
        for p_type, p_config in config_per_platform(config, DOMAIN)
    ]


@dataclass
class SpeechMetadata:
    """Metadata of audio stream."""

    language: str
    format: AudioFormats
    codec: AudioCodecs
    bit_rate: AudioBitRates
    sample_rate: AudioSampleRates
    channel: AudioChannels

    def __post_init__(self) -> None:
        """Finish initializing the metadata."""
        self.bit_rate = AudioBitRates(int(self.bit_rate))
        self.sample_rate = AudioSampleRates(int(self.sample_rate))
        self.channel = AudioChannels(int(self.channel))


@dataclass
class SpeechResult:
    """Result of audio Speech."""

    text: str | None
    result: SpeechResultState


class Provider(ABC):
    """Represent a single STT provider."""

    hass: HomeAssistant | None = None
    name: str | None = None

    @property
    @abstractmethod
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""

    @property
    @abstractmethod
    def supported_formats(self) -> list[AudioFormats]:
        """Return a list of supported formats."""

    @property
    @abstractmethod
    def supported_codecs(self) -> list[AudioCodecs]:
        """Return a list of supported codecs."""

    @property
    @abstractmethod
    def supported_bit_rates(self) -> list[AudioBitRates]:
        """Return a list of supported bit rates."""

    @property
    @abstractmethod
    def supported_sample_rates(self) -> list[AudioSampleRates]:
        """Return a list of supported sample rates."""

    @property
    @abstractmethod
    def supported_channels(self) -> list[AudioChannels]:
        """Return a list of supported channels."""

    @abstractmethod
    async def async_process_audio_stream(
        self, metadata: SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> SpeechResult:
        """Process an audio stream to STT service.

        Only streaming of content are allow!
        """

    @callback
    def check_metadata(self, metadata: SpeechMetadata) -> bool:
        """Check if given metadata supported by this provider."""
        if (
            metadata.language not in self.supported_languages
            or metadata.format not in self.supported_formats
            or metadata.codec not in self.supported_codecs
            or metadata.bit_rate not in self.supported_bit_rates
            or metadata.sample_rate not in self.supported_sample_rates
            or metadata.channel not in self.supported_channels
        ):
            return False
        return True
