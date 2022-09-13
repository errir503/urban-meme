"""Google config for Cloud."""
import asyncio
from http import HTTPStatus
import logging

from hass_nabucasa import Cloud, cloud_api
from hass_nabucasa.google_report_state import ErrorResponse

from homeassistant.components.google_assistant import DOMAIN as GOOGLE_DOMAIN
from homeassistant.components.google_assistant.helpers import AbstractConfig
from homeassistant.const import CLOUD_NEVER_EXPOSED_ENTITIES
from homeassistant.core import CoreState, Event, callback, split_entity_id
from homeassistant.helpers import device_registry as dr, entity_registry as er, start
from homeassistant.setup import async_setup_component

from .const import (
    CONF_ENTITY_CONFIG,
    DEFAULT_DISABLE_2FA,
    PREF_DISABLE_2FA,
    PREF_SHOULD_EXPOSE,
)
from .prefs import CloudPreferences

_LOGGER = logging.getLogger(__name__)


class CloudGoogleConfig(AbstractConfig):
    """HA Cloud Configuration for Google Assistant."""

    def __init__(
        self, hass, config, cloud_user: str, prefs: CloudPreferences, cloud: Cloud
    ):
        """Initialize the Google config."""
        super().__init__(hass)
        self._config = config
        self._user = cloud_user
        self._prefs = prefs
        self._cloud = cloud
        self._cur_entity_prefs = self._prefs.google_entity_configs
        self._cur_default_expose = self._prefs.google_default_expose
        self._sync_entities_lock = asyncio.Lock()

    @property
    def enabled(self):
        """Return if Google is enabled."""
        return (
            self._cloud.is_logged_in
            and not self._cloud.subscription_expired
            and self._prefs.google_enabled
        )

    @property
    def entity_config(self):
        """Return entity config."""
        return self._config.get(CONF_ENTITY_CONFIG) or {}

    @property
    def secure_devices_pin(self):
        """Return entity config."""
        return self._prefs.google_secure_devices_pin

    @property
    def should_report_state(self):
        """Return if states should be proactively reported."""
        return self.enabled and self._prefs.google_report_state

    def get_local_webhook_id(self, agent_user_id):
        """Return the webhook ID to be used for actions for a given agent user id via the local SDK."""
        return self._prefs.google_local_webhook_id

    def get_local_agent_user_id(self, webhook_id):
        """Return the user ID to be used for actions received via the local SDK."""
        return self._user

    @property
    def cloud_user(self):
        """Return Cloud User account."""
        return self._user

    async def async_initialize(self):
        """Perform async initialization of config."""
        await super().async_initialize()

        async def hass_started(hass):
            if self.enabled and GOOGLE_DOMAIN not in self.hass.config.components:
                await async_setup_component(self.hass, GOOGLE_DOMAIN, {})

        start.async_at_start(self.hass, hass_started)

        # Remove any stored user agent id that is not ours
        remove_agent_user_ids = []
        for agent_user_id in self._store.agent_user_ids:
            if agent_user_id != self.agent_user_id:
                remove_agent_user_ids.append(agent_user_id)

        for agent_user_id in remove_agent_user_ids:
            await self.async_disconnect_agent_user(agent_user_id)

        self._prefs.async_listen_updates(self._async_prefs_updated)

        self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            self._handle_entity_registry_updated,
        )
        self.hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            self._handle_device_registry_updated,
        )

    def should_expose(self, state):
        """If a state object should be exposed."""
        return self._should_expose_entity_id(state.entity_id)

    def _should_expose_entity_id(self, entity_id):
        """If an entity ID should be exposed."""
        if entity_id in CLOUD_NEVER_EXPOSED_ENTITIES:
            return False

        if not self._config["filter"].empty_filter:
            return self._config["filter"](entity_id)

        entity_configs = self._prefs.google_entity_configs
        entity_config = entity_configs.get(entity_id, {})
        entity_expose = entity_config.get(PREF_SHOULD_EXPOSE)
        if entity_expose is not None:
            return entity_expose

        entity_registry = er.async_get(self.hass)
        if registry_entry := entity_registry.async_get(entity_id):
            auxiliary_entity = (
                registry_entry.entity_category is not None
                or registry_entry.hidden_by is not None
            )
        else:
            auxiliary_entity = False

        default_expose = self._prefs.google_default_expose

        # Backwards compat
        if default_expose is None:
            return not auxiliary_entity

        return not auxiliary_entity and split_entity_id(entity_id)[0] in default_expose

    @property
    def agent_user_id(self):
        """Return Agent User Id to use for query responses."""
        return self._cloud.username

    @property
    def has_registered_user_agent(self):
        """Return if we have a Agent User Id registered."""
        return len(self._store.agent_user_ids) > 0

    def get_agent_user_id(self, context):
        """Get agent user ID making request."""
        return self.agent_user_id

    def should_2fa(self, state):
        """If an entity should be checked for 2FA."""
        entity_configs = self._prefs.google_entity_configs
        entity_config = entity_configs.get(state.entity_id, {})
        return not entity_config.get(PREF_DISABLE_2FA, DEFAULT_DISABLE_2FA)

    async def async_report_state(self, message, agent_user_id: str):
        """Send a state report to Google."""
        try:
            await self._cloud.google_report_state.async_send_message(message)
        except ErrorResponse as err:
            _LOGGER.warning("Error reporting state - %s: %s", err.code, err.message)

    async def _async_request_sync_devices(self, agent_user_id: str):
        """Trigger a sync with Google."""
        if self._sync_entities_lock.locked():
            return HTTPStatus.OK

        async with self._sync_entities_lock:
            resp = await cloud_api.async_google_actions_request_sync(self._cloud)
            return resp.status

    async def _async_prefs_updated(self, prefs):
        """Handle updated preferences."""
        if not self._cloud.is_logged_in:
            if self.is_reporting_state:
                self.async_disable_report_state()
            if self.is_local_sdk_active:
                self.async_disable_local_sdk()
            return

        if (
            self.enabled
            and GOOGLE_DOMAIN not in self.hass.config.components
            and self.hass.is_running
        ):
            await async_setup_component(self.hass, GOOGLE_DOMAIN, {})

        sync_entities = False

        if self.should_report_state != self.is_reporting_state:
            if self.should_report_state:
                self.async_enable_report_state()
            else:
                self.async_disable_report_state()

            # State reporting is reported as a property on entities.
            # So when we change it, we need to sync all entities.
            sync_entities = True

        # If entity prefs are the same or we have filter in config.yaml,
        # don't sync.
        elif (
            self._cur_entity_prefs is not prefs.google_entity_configs
            or self._cur_default_expose is not prefs.google_default_expose
        ) and self._config["filter"].empty_filter:
            self.async_schedule_google_sync_all()

        if self.enabled and not self.is_local_sdk_active:
            self.async_enable_local_sdk()
            sync_entities = True
        elif not self.enabled and self.is_local_sdk_active:
            self.async_disable_local_sdk()
            sync_entities = True

        self._cur_entity_prefs = prefs.google_entity_configs
        self._cur_default_expose = prefs.google_default_expose

        if sync_entities and self.hass.is_running:
            await self.async_sync_entities_all()

    @callback
    def _handle_entity_registry_updated(self, event: Event) -> None:
        """Handle when entity registry updated."""
        if (
            not self.enabled
            or not self._cloud.is_logged_in
            or self.hass.state != CoreState.running
        ):
            return

        # Only consider entity registry updates if info relevant for Google has changed
        if event.data["action"] == "update" and not bool(
            set(event.data["changes"]) & er.ENTITY_DESCRIBING_ATTRIBUTES
        ):
            return

        entity_id = event.data["entity_id"]

        if not self._should_expose_entity_id(entity_id):
            return

        self.async_schedule_google_sync_all()

    @callback
    def _handle_device_registry_updated(self, event: Event) -> None:
        """Handle when device registry updated."""
        if (
            not self.enabled
            or not self._cloud.is_logged_in
            or self.hass.state != CoreState.running
        ):
            return

        # Device registry is only used for area changes. All other changes are ignored.
        if event.data["action"] != "update" or "area_id" not in event.data["changes"]:
            return

        # Check if any exposed entity uses the device area
        if not any(
            entity_entry.area_id is None
            and self._should_expose_entity_id(entity_entry.entity_id)
            for entity_entry in er.async_entries_for_device(
                er.async_get(self.hass), event.data["device_id"]
            )
        ):
            return

        self.async_schedule_google_sync_all()
