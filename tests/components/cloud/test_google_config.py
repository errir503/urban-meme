"""Test the Cloud Google Config."""
from http import HTTPStatus
from unittest.mock import Mock, patch

from freezegun import freeze_time
import pytest

from homeassistant.components.cloud import GACTIONS_SCHEMA
from homeassistant.components.cloud.const import (
    PREF_DISABLE_2FA,
    PREF_GOOGLE_DEFAULT_EXPOSE,
    PREF_GOOGLE_ENTITY_CONFIGS,
    PREF_SHOULD_EXPOSE,
)
from homeassistant.components.cloud.google_config import CloudGoogleConfig
from homeassistant.components.cloud.prefs import CloudPreferences
from homeassistant.components.google_assistant import helpers as ga_helpers
from homeassistant.components.homeassistant.exposed_entities import (
    DATA_EXPOSED_ENTITIES,
    ExposedEntities,
)
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EntityCategory
from homeassistant.core import CoreState, HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util.dt import utcnow

from tests.common import async_fire_time_changed


@pytest.fixture
def mock_conf(hass, cloud_prefs):
    """Mock Google conf."""
    return CloudGoogleConfig(
        hass,
        GACTIONS_SCHEMA({}),
        "mock-user-id",
        cloud_prefs,
        Mock(claims={"cognito:username": "abcdefghjkl"}),
    )


def expose_new(hass, expose_new):
    """Enable exposing new entities to Google."""
    exposed_entities: ExposedEntities = hass.data[DATA_EXPOSED_ENTITIES]
    exposed_entities.async_set_expose_new_entities("cloud.google_assistant", expose_new)


def expose_entity(hass, entity_id, should_expose):
    """Expose an entity to Google."""
    exposed_entities: ExposedEntities = hass.data[DATA_EXPOSED_ENTITIES]
    exposed_entities.async_expose_entity(
        "cloud.google_assistant", entity_id, should_expose
    )


async def test_google_update_report_state(
    mock_conf, hass: HomeAssistant, cloud_prefs
) -> None:
    """Test Google config responds to updating preference."""
    assert await async_setup_component(hass, "homeassistant", {})

    await mock_conf.async_initialize()
    await mock_conf.async_connect_agent_user("mock-user-id")

    mock_conf._cloud.subscription_expired = False

    with patch.object(mock_conf, "async_sync_entities") as mock_sync, patch(
        "homeassistant.components.google_assistant.report_state.async_enable_report_state"
    ) as mock_report_state:
        await cloud_prefs.async_update(google_report_state=True)
        await hass.async_block_till_done()

    assert len(mock_sync.mock_calls) == 1
    assert len(mock_report_state.mock_calls) == 1


async def test_google_update_report_state_subscription_expired(
    mock_conf, hass: HomeAssistant, cloud_prefs
) -> None:
    """Test Google config not reporting state when subscription has expired."""
    assert await async_setup_component(hass, "homeassistant", {})

    await mock_conf.async_initialize()
    await mock_conf.async_connect_agent_user("mock-user-id")

    assert mock_conf._cloud.subscription_expired

    with patch.object(mock_conf, "async_sync_entities") as mock_sync, patch(
        "homeassistant.components.google_assistant.report_state.async_enable_report_state"
    ) as mock_report_state:
        await cloud_prefs.async_update(google_report_state=True)
        await hass.async_block_till_done()

    assert len(mock_sync.mock_calls) == 0
    assert len(mock_report_state.mock_calls) == 0


async def test_sync_entities(mock_conf, hass: HomeAssistant, cloud_prefs) -> None:
    """Test sync devices."""
    assert await async_setup_component(hass, "homeassistant", {})

    await mock_conf.async_initialize()
    await mock_conf.async_connect_agent_user("mock-user-id")

    assert len(mock_conf._store.agent_user_ids) == 1

    with patch(
        "hass_nabucasa.cloud_api.async_google_actions_request_sync",
        return_value=Mock(status=HTTPStatus.NOT_FOUND),
    ) as mock_request_sync:
        assert (
            await mock_conf.async_sync_entities("mock-user-id") == HTTPStatus.NOT_FOUND
        )
        assert len(mock_conf._store.agent_user_ids) == 0
        assert len(mock_request_sync.mock_calls) == 1


async def test_google_update_expose_trigger_sync(
    hass: HomeAssistant, cloud_prefs
) -> None:
    """Test Google config responds to updating exposed entities."""
    assert await async_setup_component(hass, "homeassistant", {})
    entity_registry = er.async_get(hass)

    # Enable exposing new entities to Google
    expose_new(hass, True)
    # Register entities
    binary_sensor_entry = entity_registry.async_get_or_create(
        "binary_sensor", "test", "unique", suggested_object_id="door"
    )
    sensor_entry = entity_registry.async_get_or_create(
        "sensor", "test", "unique", suggested_object_id="temp"
    )
    light_entry = entity_registry.async_get_or_create(
        "light", "test", "unique", suggested_object_id="kitchen"
    )

    with freeze_time(utcnow()):
        config = CloudGoogleConfig(
            hass,
            GACTIONS_SCHEMA({}),
            "mock-user-id",
            cloud_prefs,
            Mock(claims={"cognito:username": "abcdefghjkl"}),
        )
        await config.async_initialize()
        await config.async_connect_agent_user("mock-user-id")

        with patch.object(config, "async_sync_entities") as mock_sync, patch.object(
            ga_helpers, "SYNC_DELAY", 0
        ):
            expose_entity(hass, light_entry.entity_id, True)
            await hass.async_block_till_done()
            async_fire_time_changed(hass, utcnow())
            await hass.async_block_till_done()

        assert len(mock_sync.mock_calls) == 1

        with patch.object(config, "async_sync_entities") as mock_sync, patch.object(
            ga_helpers, "SYNC_DELAY", 0
        ):
            expose_entity(hass, light_entry.entity_id, False)
            expose_entity(hass, binary_sensor_entry.entity_id, True)
            expose_entity(hass, sensor_entry.entity_id, True)
            await hass.async_block_till_done()
            async_fire_time_changed(hass, utcnow())
            await hass.async_block_till_done()

        assert len(mock_sync.mock_calls) == 1


async def test_google_entity_registry_sync(
    hass: HomeAssistant, mock_cloud_login, cloud_prefs
) -> None:
    """Test Google config responds to entity registry."""
    entity_registry = er.async_get(hass)

    # Enable exposing new entities to Google
    expose_new(hass, True)

    config = CloudGoogleConfig(
        hass, GACTIONS_SCHEMA({}), "mock-user-id", cloud_prefs, hass.data["cloud"]
    )
    await config.async_initialize()
    await config.async_connect_agent_user("mock-user-id")

    with patch.object(
        config, "async_schedule_google_sync_all"
    ) as mock_sync, patch.object(config, "async_sync_entities_all"), patch.object(
        ga_helpers, "SYNC_DELAY", 0
    ):
        # Created entity
        entry = entity_registry.async_get_or_create(
            "light", "test", "unique", suggested_object_id="kitchen"
        )
        await hass.async_block_till_done()

        assert len(mock_sync.mock_calls) == 1

        # Removed entity
        hass.bus.async_fire(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            {"action": "remove", "entity_id": entry.entity_id},
        )
        await hass.async_block_till_done()

        assert len(mock_sync.mock_calls) == 2

        # Entity registry updated with relevant changes
        hass.bus.async_fire(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            {
                "action": "update",
                "entity_id": entry.entity_id,
                "changes": ["entity_id"],
            },
        )
        await hass.async_block_till_done()

        assert len(mock_sync.mock_calls) == 3

        # Entity registry updated with non-relevant changes
        hass.bus.async_fire(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            {"action": "update", "entity_id": entry.entity_id, "changes": ["icon"]},
        )
        await hass.async_block_till_done()

        assert len(mock_sync.mock_calls) == 3

        # When hass is not started yet we wait till started
        hass.state = CoreState.starting
        hass.bus.async_fire(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            {"action": "create", "entity_id": entry.entity_id},
        )
        await hass.async_block_till_done()

        assert len(mock_sync.mock_calls) == 3


async def test_google_device_registry_sync(
    hass: HomeAssistant, mock_cloud_login, cloud_prefs
) -> None:
    """Test Google config responds to device registry."""
    config = CloudGoogleConfig(
        hass, GACTIONS_SCHEMA({}), "mock-user-id", cloud_prefs, hass.data["cloud"]
    )
    ent_reg = er.async_get(hass)

    # Enable exposing new entities to Google
    expose_new(hass, True)

    entity_entry = ent_reg.async_get_or_create("light", "hue", "1234", device_id="1234")
    entity_entry = ent_reg.async_update_entity(entity_entry.entity_id, area_id="ABCD")

    with patch.object(config, "async_sync_entities_all"):
        await config.async_initialize()
        await hass.async_block_till_done()
    await config.async_connect_agent_user("mock-user-id")

    with patch.object(config, "async_schedule_google_sync_all") as mock_sync:
        # Device registry updated with non-relevant changes
        hass.bus.async_fire(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            {
                "action": "update",
                "device_id": "1234",
                "changes": ["manufacturer"],
            },
        )
        await hass.async_block_till_done()

        assert len(mock_sync.mock_calls) == 0

        # Device registry updated with relevant changes
        # but entity has area ID so not impacted
        hass.bus.async_fire(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            {
                "action": "update",
                "device_id": "1234",
                "changes": ["area_id"],
            },
        )
        await hass.async_block_till_done()

        assert len(mock_sync.mock_calls) == 0

        ent_reg.async_update_entity(entity_entry.entity_id, area_id=None)

        # Device registry updated with relevant changes
        # but entity has area ID so not impacted
        hass.bus.async_fire(
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            {
                "action": "update",
                "device_id": "1234",
                "changes": ["area_id"],
            },
        )
        await hass.async_block_till_done()

        assert len(mock_sync.mock_calls) == 1


async def test_sync_google_when_started(
    hass: HomeAssistant, mock_cloud_login, cloud_prefs
) -> None:
    """Test Google config syncs on init."""
    config = CloudGoogleConfig(
        hass, GACTIONS_SCHEMA({}), "mock-user-id", cloud_prefs, hass.data["cloud"]
    )
    with patch.object(config, "async_sync_entities_all") as mock_sync:
        await config.async_initialize()
        await config.async_connect_agent_user("mock-user-id")
        await hass.async_block_till_done()
        assert len(mock_sync.mock_calls) == 1


async def test_sync_google_on_home_assistant_start(
    hass: HomeAssistant, mock_cloud_login, cloud_prefs
) -> None:
    """Test Google config syncs when home assistant started."""
    config = CloudGoogleConfig(
        hass, GACTIONS_SCHEMA({}), "mock-user-id", cloud_prefs, hass.data["cloud"]
    )
    hass.state = CoreState.starting
    with patch.object(config, "async_sync_entities_all") as mock_sync:
        await config.async_initialize()
        await config.async_connect_agent_user("mock-user-id")
        assert len(mock_sync.mock_calls) == 0

        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()
        assert len(mock_sync.mock_calls) == 1


async def test_google_config_expose_entity_prefs(
    hass: HomeAssistant, mock_conf, cloud_prefs, entity_registry: er.EntityRegistry
) -> None:
    """Test Google config should expose using prefs."""
    assert await async_setup_component(hass, "homeassistant", {})
    entity_entry1 = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_config_id",
        suggested_object_id="config_light",
        entity_category=EntityCategory.CONFIG,
    )
    entity_entry2 = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_diagnostic_id",
        suggested_object_id="diagnostic_light",
        entity_category=EntityCategory.DIAGNOSTIC,
    )
    entity_entry3 = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_hidden_integration_id",
        suggested_object_id="hidden_integration_light",
        hidden_by=er.RegistryEntryHider.INTEGRATION,
    )
    entity_entry4 = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_hidden_user_id",
        suggested_object_id="hidden_user_light",
        hidden_by=er.RegistryEntryHider.USER,
    )
    entity_entry5 = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_basement_id",
        suggested_object_id="basement",
    )
    entity_entry6 = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_entrance_id",
        suggested_object_id="entrance",
    )

    expose_new(hass, True)
    expose_entity(hass, entity_entry5.entity_id, False)

    state = State("light.kitchen", "on")
    state_config = State(entity_entry1.entity_id, "on")
    state_diagnostic = State(entity_entry2.entity_id, "on")
    state_hidden_integration = State(entity_entry3.entity_id, "on")
    state_hidden_user = State(entity_entry4.entity_id, "on")
    state_not_exposed = State(entity_entry5.entity_id, "on")
    state_exposed_default = State(entity_entry6.entity_id, "on")

    # can't expose an entity which is not in the entity registry
    with pytest.raises(HomeAssistantError):
        expose_entity(hass, "light.kitchen", True)
    assert not mock_conf.should_expose(state)
    # categorized and hidden entities should not be exposed
    assert not mock_conf.should_expose(state_config)
    assert not mock_conf.should_expose(state_diagnostic)
    assert not mock_conf.should_expose(state_hidden_integration)
    assert not mock_conf.should_expose(state_hidden_user)
    # this has been hidden
    assert not mock_conf.should_expose(state_not_exposed)
    # exposed by default
    assert mock_conf.should_expose(state_exposed_default)

    expose_entity(hass, entity_entry5.entity_id, True)
    assert mock_conf.should_expose(state_not_exposed)

    expose_entity(hass, entity_entry5.entity_id, None)
    assert not mock_conf.should_expose(state_not_exposed)


def test_enabled_requires_valid_sub(
    hass: HomeAssistant, mock_expired_cloud_login, cloud_prefs
) -> None:
    """Test that google config enabled requires a valid Cloud sub."""
    assert cloud_prefs.google_enabled
    assert hass.data["cloud"].is_logged_in
    assert hass.data["cloud"].subscription_expired

    config = CloudGoogleConfig(
        hass, GACTIONS_SCHEMA({}), "mock-user-id", cloud_prefs, hass.data["cloud"]
    )

    assert not config.enabled


async def test_setup_integration(hass: HomeAssistant, mock_conf, cloud_prefs) -> None:
    """Test that we set up the integration if used."""
    assert await async_setup_component(hass, "homeassistant", {})
    mock_conf._cloud.subscription_expired = False

    assert "google_assistant" not in hass.config.components

    await mock_conf.async_initialize()
    await hass.async_block_till_done()
    assert "google_assistant" in hass.config.components

    hass.config.components.remove("google_assistant")

    await cloud_prefs.async_update()
    await hass.async_block_till_done()
    assert "google_assistant" in hass.config.components


async def test_google_handle_logout(
    hass: HomeAssistant, cloud_prefs, mock_cloud_login
) -> None:
    """Test Google config responds to logging out."""
    gconf = CloudGoogleConfig(
        hass, GACTIONS_SCHEMA({}), "mock-user-id", cloud_prefs, Mock(is_logged_in=False)
    )

    await gconf.async_initialize()

    with patch(
        "homeassistant.components.google_assistant.report_state.async_enable_report_state",
    ) as mock_enable:
        gconf.async_enable_report_state()

    assert len(mock_enable.mock_calls) == 1

    # This will trigger a prefs update when we logout.
    await cloud_prefs.get_cloud_user()

    with patch.object(
        hass.data["cloud"].auth,
        "async_check_token",
        side_effect=AssertionError("Should not be called"),
    ):
        await cloud_prefs.async_set_username(None)
        await hass.async_block_till_done()

    assert len(mock_enable.return_value.mock_calls) == 1


async def test_google_config_migrate_expose_entity_prefs(
    hass: HomeAssistant,
    cloud_prefs: CloudPreferences,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test migrating Google entity config."""

    assert await async_setup_component(hass, "homeassistant", {})
    entity_exposed = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_exposed",
        suggested_object_id="exposed",
    )

    entity_no_2fa_exposed = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_no_2fa_exposed",
        suggested_object_id="no_2fa_exposed",
    )

    entity_migrated = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_migrated",
        suggested_object_id="migrated",
    )

    entity_config = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_config",
        suggested_object_id="config",
        entity_category=EntityCategory.CONFIG,
    )

    entity_default = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_default",
        suggested_object_id="default",
    )

    entity_blocked = entity_registry.async_get_or_create(
        "group",
        "test",
        "group_all_locks",
        suggested_object_id="all_locks",
    )
    assert entity_blocked.entity_id == "group.all_locks"

    await cloud_prefs.async_update(
        google_enabled=True,
        google_report_state=False,
        google_settings_version=1,
    )
    expose_entity(hass, entity_migrated.entity_id, False)

    cloud_prefs._prefs[PREF_GOOGLE_ENTITY_CONFIGS]["light.unknown"] = {
        PREF_SHOULD_EXPOSE: True
    }
    cloud_prefs._prefs[PREF_GOOGLE_ENTITY_CONFIGS][entity_exposed.entity_id] = {
        PREF_SHOULD_EXPOSE: True
    }
    cloud_prefs._prefs[PREF_GOOGLE_ENTITY_CONFIGS][entity_no_2fa_exposed.entity_id] = {
        PREF_SHOULD_EXPOSE: True,
        PREF_DISABLE_2FA: True,
    }
    cloud_prefs._prefs[PREF_GOOGLE_ENTITY_CONFIGS][entity_migrated.entity_id] = {
        PREF_SHOULD_EXPOSE: True
    }
    conf = CloudGoogleConfig(
        hass, GACTIONS_SCHEMA({}), "mock-user-id", cloud_prefs, Mock(is_logged_in=False)
    )
    await conf.async_initialize()

    entity_exposed = entity_registry.async_get(entity_exposed.entity_id)
    assert entity_exposed.options == {"cloud.google_assistant": {"should_expose": True}}

    entity_migrated = entity_registry.async_get(entity_migrated.entity_id)
    assert entity_migrated.options == {
        "cloud.google_assistant": {"should_expose": False}
    }

    entity_no_2fa_exposed = entity_registry.async_get(entity_no_2fa_exposed.entity_id)
    assert entity_no_2fa_exposed.options == {
        "cloud.google_assistant": {"disable_2fa": True, "should_expose": True}
    }

    entity_config = entity_registry.async_get(entity_config.entity_id)
    assert entity_config.options == {"cloud.google_assistant": {"should_expose": False}}

    entity_default = entity_registry.async_get(entity_default.entity_id)
    assert entity_default.options == {"cloud.google_assistant": {"should_expose": True}}

    entity_blocked = entity_registry.async_get(entity_blocked.entity_id)
    assert entity_blocked.options == {
        "cloud.google_assistant": {"should_expose": False}
    }


async def test_google_config_migrate_expose_entity_prefs_default_none(
    hass: HomeAssistant,
    cloud_prefs: CloudPreferences,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test migrating Google entity config."""

    assert await async_setup_component(hass, "homeassistant", {})
    entity_default = entity_registry.async_get_or_create(
        "light",
        "test",
        "light_default",
        suggested_object_id="default",
    )

    await cloud_prefs.async_update(
        google_enabled=True,
        google_report_state=False,
        google_settings_version=1,
    )

    cloud_prefs._prefs[PREF_GOOGLE_DEFAULT_EXPOSE] = None
    conf = CloudGoogleConfig(
        hass, GACTIONS_SCHEMA({}), "mock-user-id", cloud_prefs, Mock(is_logged_in=False)
    )
    await conf.async_initialize()

    entity_default = entity_registry.async_get(entity_default.entity_id)
    assert entity_default.options == {"cloud.google_assistant": {"should_expose": True}}
