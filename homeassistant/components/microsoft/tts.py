"""Support for the Microsoft Cognitive Services text-to-speech service."""
from http.client import HTTPException
import logging

from pycsspeechtts import pycsspeechtts
import voluptuous as vol

from homeassistant.components.tts import CONF_LANG, PLATFORM_SCHEMA, Provider
from homeassistant.const import CONF_API_KEY, CONF_REGION, CONF_TYPE, PERCENTAGE
import homeassistant.helpers.config_validation as cv

CONF_GENDER = "gender"
CONF_OUTPUT = "output"
CONF_RATE = "rate"
CONF_VOLUME = "volume"
CONF_PITCH = "pitch"
CONF_CONTOUR = "contour"
_LOGGER = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = [
    "ar-eg",
    "ar-sa",
    "bg-bg",
    "ca-es",
    "cs-cz",
    "cy-gb",
    "da-dk",
    "de-at",
    "de-ch",
    "de-de",
    "el-gr",
    "en-au",
    "en-ca",
    "en-gb",
    "en-hk",
    "en-ie",
    "en-in",
    "en-nz",
    "en-ph",
    "en-sg",
    "en-us",
    "en-za",
    "es-ar",
    "es-co",
    "es-es",
    "es-mx",
    "es-us",
    "et-ee",
    "fi-fi",
    "fr-be",
    "fr-ca",
    "fr-ch",
    "fr-fr",
    "ga-ie",
    "gu-in",
    "he-il",
    "hi-in",
    "hr-hr",
    "hu-hu",
    "id-id",
    "is-is",
    "it-it",
    "ja-jp",
    "ko-kr",
    "lt-lt",
    "lv-lv",
    "mr-in",
    "ms-my",
    "mt-mt",
    "nb-no",
    "nl-be",
    "nl-nl",
    "pl-pl",
    "pt-br",
    "pt-pt",
    "ro-ro",
    "ru-ru",
    "sk-sk",
    "sl-si",
    "sv-se",
    "sw-ke",
    "ta-in",
    "te-in",
    "th-th",
    "tr-tr",
    "uk-ua",
    "ur-pk",
    "vi-vn",
    "zh-cn",
    "zh-hk",
    "zh-tw",
]

GENDERS = ["Female", "Male"]

DEFAULT_LANG = "en-us"
DEFAULT_GENDER = "Female"
DEFAULT_TYPE = "JennyNeural"
DEFAULT_OUTPUT = "audio-24khz-96kbitrate-mono-mp3"
DEFAULT_RATE = 0
DEFAULT_VOLUME = 0
DEFAULT_PITCH = "default"
DEFAULT_CONTOUR = ""
DEFAULT_REGION = "eastus"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_LANG, default=DEFAULT_LANG): vol.In(SUPPORTED_LANGUAGES),
        vol.Optional(CONF_GENDER, default=DEFAULT_GENDER): vol.In(GENDERS),
        vol.Optional(CONF_TYPE, default=DEFAULT_TYPE): cv.string,
        vol.Optional(CONF_RATE, default=DEFAULT_RATE): vol.All(
            vol.Coerce(int), vol.Range(-100, 100)
        ),
        vol.Optional(CONF_VOLUME, default=DEFAULT_VOLUME): vol.All(
            vol.Coerce(int), vol.Range(-100, 100)
        ),
        vol.Optional(CONF_PITCH, default=DEFAULT_PITCH): cv.string,
        vol.Optional(CONF_CONTOUR, default=DEFAULT_CONTOUR): cv.string,
        vol.Optional(CONF_REGION, default=DEFAULT_REGION): cv.string,
    }
)


def get_engine(hass, config, discovery_info=None):
    """Set up Microsoft speech component."""
    return MicrosoftProvider(
        config[CONF_API_KEY],
        config[CONF_LANG],
        config[CONF_GENDER],
        config[CONF_TYPE],
        config[CONF_RATE],
        config[CONF_VOLUME],
        config[CONF_PITCH],
        config[CONF_CONTOUR],
        config[CONF_REGION],
    )


class MicrosoftProvider(Provider):
    """The Microsoft speech API provider."""

    def __init__(
        self, apikey, lang, gender, ttype, rate, volume, pitch, contour, region
    ):
        """Init Microsoft TTS service."""
        self._apikey = apikey
        self._lang = lang
        self._gender = gender
        self._type = ttype
        self._output = DEFAULT_OUTPUT
        self._rate = f"{rate}{PERCENTAGE}"
        self._volume = f"{volume}{PERCENTAGE}"
        self._pitch = pitch
        self._contour = contour
        self._region = region
        self.name = "Microsoft"

    @property
    def default_language(self):
        """Return the default language."""
        return self._lang

    @property
    def supported_languages(self):
        """Return list of supported languages."""
        return SUPPORTED_LANGUAGES

    @property
    def supported_options(self):
        """Return list of supported options like voice, emotion."""
        return [CONF_GENDER, CONF_TYPE]

    @property
    def default_options(self):
        """Return a dict include default options."""
        return {CONF_GENDER: self._gender, CONF_TYPE: self._type}

    def get_tts_audio(self, message, language, options=None):
        """Load TTS from Microsoft."""
        if language is None:
            language = self._lang

        try:
            trans = pycsspeechtts.TTSTranslator(self._apikey, self._region)
            data = trans.speak(
                language=language,
                gender=options[CONF_GENDER],
                voiceType=options[CONF_TYPE],
                output=self._output,
                rate=self._rate,
                volume=self._volume,
                pitch=self._pitch,
                contour=self._contour,
                text=message,
            )
        except HTTPException as ex:
            _LOGGER.error("Error occurred for Microsoft TTS: %s", ex)
            return (None, None)
        return ("mp3", data)
