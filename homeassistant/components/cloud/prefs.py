"""Preference management for cloud."""
from __future__ import annotations

from typing import Any

from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.auth.models import User
from homeassistant.components import webhook
from homeassistant.core import callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.util.logging import async_create_catching_coro

from .const import (
    DEFAULT_ALEXA_REPORT_STATE,
    DEFAULT_EXPOSED_DOMAINS,
    DEFAULT_GOOGLE_REPORT_STATE,
    DEFAULT_TTS_DEFAULT_VOICE,
    DOMAIN,
    PREF_ALEXA_DEFAULT_EXPOSE,
    PREF_ALEXA_ENTITY_CONFIGS,
    PREF_ALEXA_REPORT_STATE,
    PREF_ALEXA_SETTINGS_VERSION,
    PREF_CLOUD_USER,
    PREF_CLOUDHOOKS,
    PREF_ENABLE_ALEXA,
    PREF_ENABLE_GOOGLE,
    PREF_ENABLE_REMOTE,
    PREF_GOOGLE_DEFAULT_EXPOSE,
    PREF_GOOGLE_ENTITY_CONFIGS,
    PREF_GOOGLE_LOCAL_WEBHOOK_ID,
    PREF_GOOGLE_REPORT_STATE,
    PREF_GOOGLE_SECURE_DEVICES_PIN,
    PREF_GOOGLE_SETTINGS_VERSION,
    PREF_REMOTE_DOMAIN,
    PREF_TTS_DEFAULT_VOICE,
    PREF_USERNAME,
)

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
STORAGE_VERSION_MINOR = 2

ALEXA_SETTINGS_VERSION = 3
GOOGLE_SETTINGS_VERSION = 3


class CloudPreferencesStore(Store):
    """Store entity registry data."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Migrate to the new version."""
        if old_major_version == 1:
            if old_minor_version < 2:
                old_data.setdefault(PREF_ALEXA_SETTINGS_VERSION, 1)
                old_data.setdefault(PREF_GOOGLE_SETTINGS_VERSION, 1)

        return old_data


class CloudPreferences:
    """Handle cloud preferences."""

    def __init__(self, hass):
        """Initialize cloud prefs."""
        self._hass = hass
        self._store = CloudPreferencesStore(
            hass, STORAGE_VERSION, STORAGE_KEY, minor_version=STORAGE_VERSION_MINOR
        )
        self._prefs = None
        self._listeners = []
        self.last_updated: set[str] = set()

    async def async_initialize(self):
        """Finish initializing the preferences."""
        if (prefs := await self._store.async_load()) is None:
            prefs = self._empty_config("")

        self._prefs = prefs

        if PREF_GOOGLE_LOCAL_WEBHOOK_ID not in self._prefs:
            await self._save_prefs(
                {
                    **self._prefs,
                    PREF_GOOGLE_LOCAL_WEBHOOK_ID: webhook.async_generate_id(),
                }
            )

    @callback
    def async_listen_updates(self, listener):
        """Listen for updates to the preferences."""
        self._listeners.append(listener)

    async def async_update(
        self,
        *,
        google_enabled=UNDEFINED,
        alexa_enabled=UNDEFINED,
        remote_enabled=UNDEFINED,
        google_secure_devices_pin=UNDEFINED,
        cloudhooks=UNDEFINED,
        cloud_user=UNDEFINED,
        alexa_report_state=UNDEFINED,
        google_report_state=UNDEFINED,
        tts_default_voice=UNDEFINED,
        remote_domain=UNDEFINED,
        alexa_settings_version=UNDEFINED,
        google_settings_version=UNDEFINED,
    ):
        """Update user preferences."""
        prefs = {**self._prefs}

        for key, value in (
            (PREF_ENABLE_GOOGLE, google_enabled),
            (PREF_ENABLE_ALEXA, alexa_enabled),
            (PREF_ENABLE_REMOTE, remote_enabled),
            (PREF_GOOGLE_SECURE_DEVICES_PIN, google_secure_devices_pin),
            (PREF_CLOUDHOOKS, cloudhooks),
            (PREF_CLOUD_USER, cloud_user),
            (PREF_ALEXA_REPORT_STATE, alexa_report_state),
            (PREF_GOOGLE_REPORT_STATE, google_report_state),
            (PREF_ALEXA_SETTINGS_VERSION, alexa_settings_version),
            (PREF_GOOGLE_SETTINGS_VERSION, google_settings_version),
            (PREF_TTS_DEFAULT_VOICE, tts_default_voice),
            (PREF_REMOTE_DOMAIN, remote_domain),
        ):
            if value is not UNDEFINED:
                prefs[key] = value

        await self._save_prefs(prefs)

    async def async_set_username(self, username) -> bool:
        """Set the username that is logged in."""
        # Logging out.
        if username is None:
            user = await self._load_cloud_user()

            if user is not None:
                await self._hass.auth.async_remove_user(user)
                await self._save_prefs({**self._prefs, PREF_CLOUD_USER: None})
            return False

        cur_username = self._prefs.get(PREF_USERNAME)

        if cur_username == username:
            return False

        if cur_username is None:
            await self._save_prefs({**self._prefs, PREF_USERNAME: username})
        else:
            await self._save_prefs(self._empty_config(username))

        return True

    def as_dict(self):
        """Return dictionary version."""
        return {
            PREF_ALEXA_DEFAULT_EXPOSE: self.alexa_default_expose,
            PREF_ALEXA_REPORT_STATE: self.alexa_report_state,
            PREF_CLOUDHOOKS: self.cloudhooks,
            PREF_ENABLE_ALEXA: self.alexa_enabled,
            PREF_ENABLE_GOOGLE: self.google_enabled,
            PREF_ENABLE_REMOTE: self.remote_enabled,
            PREF_GOOGLE_DEFAULT_EXPOSE: self.google_default_expose,
            PREF_GOOGLE_REPORT_STATE: self.google_report_state,
            PREF_GOOGLE_SECURE_DEVICES_PIN: self.google_secure_devices_pin,
            PREF_TTS_DEFAULT_VOICE: self.tts_default_voice,
        }

    @property
    def remote_enabled(self):
        """Return if remote is enabled on start."""
        if not self._prefs.get(PREF_ENABLE_REMOTE, False):
            return False

        return True

    @property
    def remote_domain(self):
        """Return remote domain."""
        return self._prefs.get(PREF_REMOTE_DOMAIN)

    @property
    def alexa_enabled(self):
        """Return if Alexa is enabled."""
        return self._prefs[PREF_ENABLE_ALEXA]

    @property
    def alexa_report_state(self):
        """Return if Alexa report state is enabled."""
        return self._prefs.get(PREF_ALEXA_REPORT_STATE, DEFAULT_ALEXA_REPORT_STATE)

    @property
    def alexa_default_expose(self) -> list[str] | None:
        """Return array of entity domains that are exposed by default to Alexa.

        Can return None, in which case for backwards should be interpreted as allow all domains.
        """
        return self._prefs.get(PREF_ALEXA_DEFAULT_EXPOSE)

    @property
    def alexa_entity_configs(self):
        """Return Alexa Entity configurations."""
        return self._prefs.get(PREF_ALEXA_ENTITY_CONFIGS, {})

    @property
    def alexa_settings_version(self):
        """Return version of Alexa settings."""
        return self._prefs[PREF_ALEXA_SETTINGS_VERSION]

    @property
    def google_enabled(self):
        """Return if Google is enabled."""
        return self._prefs[PREF_ENABLE_GOOGLE]

    @property
    def google_report_state(self):
        """Return if Google report state is enabled."""
        return self._prefs.get(PREF_GOOGLE_REPORT_STATE, DEFAULT_GOOGLE_REPORT_STATE)

    @property
    def google_secure_devices_pin(self):
        """Return if Google is allowed to unlock locks."""
        return self._prefs.get(PREF_GOOGLE_SECURE_DEVICES_PIN)

    @property
    def google_entity_configs(self):
        """Return Google Entity configurations."""
        return self._prefs.get(PREF_GOOGLE_ENTITY_CONFIGS, {})

    @property
    def google_settings_version(self):
        """Return version of Google settings."""
        return self._prefs[PREF_GOOGLE_SETTINGS_VERSION]

    @property
    def google_local_webhook_id(self):
        """Return Google webhook ID to receive local messages."""
        return self._prefs[PREF_GOOGLE_LOCAL_WEBHOOK_ID]

    @property
    def google_default_expose(self) -> list[str] | None:
        """Return array of entity domains that are exposed by default to Google.

        Can return None, in which case for backwards should be interpreted as allow all domains.
        """
        return self._prefs.get(PREF_GOOGLE_DEFAULT_EXPOSE)

    @property
    def cloudhooks(self):
        """Return the published cloud webhooks."""
        return self._prefs.get(PREF_CLOUDHOOKS, {})

    @property
    def tts_default_voice(self):
        """Return the default TTS voice."""
        return self._prefs.get(PREF_TTS_DEFAULT_VOICE, DEFAULT_TTS_DEFAULT_VOICE)

    async def get_cloud_user(self) -> str:
        """Return ID of Home Assistant Cloud system user."""
        user = await self._load_cloud_user()

        if user:
            return user.id

        user = await self._hass.auth.async_create_system_user(
            "Home Assistant Cloud", group_ids=[GROUP_ID_ADMIN], local_only=True
        )
        assert user is not None
        await self.async_update(cloud_user=user.id)
        return user.id

    async def _load_cloud_user(self) -> User | None:
        """Load cloud user if available."""
        if (user_id := self._prefs.get(PREF_CLOUD_USER)) is None:
            return None

        # Fetch the user. It can happen that the user no longer exists if
        # an image was restored without restoring the cloud prefs.
        return await self._hass.auth.async_get_user(user_id)

    async def _save_prefs(self, prefs):
        """Save preferences to disk."""
        self.last_updated = {
            key for key, value in prefs.items() if value != self._prefs.get(key)
        }
        self._prefs = prefs
        await self._store.async_save(self._prefs)

        for listener in self._listeners:
            self._hass.async_create_task(async_create_catching_coro(listener(self)))

    @callback
    @staticmethod
    def _empty_config(username):
        """Return an empty config."""
        return {
            PREF_ALEXA_DEFAULT_EXPOSE: DEFAULT_EXPOSED_DOMAINS,
            PREF_ALEXA_ENTITY_CONFIGS: {},
            PREF_ALEXA_SETTINGS_VERSION: ALEXA_SETTINGS_VERSION,
            PREF_CLOUD_USER: None,
            PREF_CLOUDHOOKS: {},
            PREF_ENABLE_ALEXA: True,
            PREF_ENABLE_GOOGLE: True,
            PREF_ENABLE_REMOTE: False,
            PREF_GOOGLE_DEFAULT_EXPOSE: DEFAULT_EXPOSED_DOMAINS,
            PREF_GOOGLE_ENTITY_CONFIGS: {},
            PREF_GOOGLE_SETTINGS_VERSION: GOOGLE_SETTINGS_VERSION,
            PREF_GOOGLE_LOCAL_WEBHOOK_ID: webhook.async_generate_id(),
            PREF_GOOGLE_SECURE_DEVICES_PIN: None,
            PREF_REMOTE_DOMAIN: None,
            PREF_USERNAME: username,
        }
