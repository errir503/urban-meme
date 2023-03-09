"""Tests for the legacy_api_password auth provider."""
import pytest

from homeassistant import auth, data_entry_flow
from homeassistant.auth import auth_store
from homeassistant.auth.providers import legacy_api_password
from homeassistant.core import HomeAssistant


@pytest.fixture
def store(hass):
    """Mock store."""
    return auth_store.AuthStore(hass)


@pytest.fixture
def provider(hass, store):
    """Mock provider."""
    return legacy_api_password.LegacyApiPasswordAuthProvider(
        hass, store, {"type": "legacy_api_password", "api_password": "test-password"}
    )


@pytest.fixture
def manager(hass, store, provider):
    """Mock manager."""
    return auth.AuthManager(hass, store, {(provider.type, provider.id): provider}, {})


async def test_create_new_credential(manager, provider) -> None:
    """Test that we create a new credential."""
    credentials = await provider.async_get_or_create_credentials({})
    assert credentials.is_new is True

    user = await manager.async_get_or_create_user(credentials)
    assert user.name == legacy_api_password.LEGACY_USER_NAME
    assert user.is_active


async def test_only_one_credentials(manager, provider) -> None:
    """Call create twice will return same credential."""
    credentials = await provider.async_get_or_create_credentials({})
    await manager.async_get_or_create_user(credentials)
    credentials2 = await provider.async_get_or_create_credentials({})
    assert credentials2.id == credentials.id
    assert credentials2.is_new is False


async def test_verify_login(hass: HomeAssistant, provider) -> None:
    """Test login using legacy api password auth provider."""
    provider.async_validate_login("test-password")
    with pytest.raises(legacy_api_password.InvalidAuthError):
        provider.async_validate_login("invalid-password")


async def test_login_flow_works(hass: HomeAssistant, manager) -> None:
    """Test wrong config."""
    result = await manager.login_flow.async_init(handler=("legacy_api_password", None))
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await manager.login_flow.async_configure(
        flow_id=result["flow_id"], user_input={"password": "not-hello"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"

    result = await manager.login_flow.async_configure(
        flow_id=result["flow_id"], user_input={"password": "test-password"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
