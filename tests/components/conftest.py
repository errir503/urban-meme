"""Fixtures for component testing."""
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(scope="session", autouse=True)
def patch_zeroconf_multiple_catcher():
    """Patch zeroconf wrapper that detects if multiple instances are used."""
    with patch(
        "homeassistant.components.zeroconf.install_multiple_zeroconf_catcher",
        side_effect=lambda zc: None,
    ):
        yield


@pytest.fixture(autouse=True)
def prevent_io():
    """Fixture to prevent certain I/O from happening."""
    with patch(
        "homeassistant.components.http.ban.async_load_ip_bans_config",
        return_value=[],
    ):
        yield


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[AsyncMock, None, None]:
    """Test fixture that ensures all entities are enabled in the registry."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
    ) as mock_entity_registry_enabled_by_default:
        yield mock_entity_registry_enabled_by_default
