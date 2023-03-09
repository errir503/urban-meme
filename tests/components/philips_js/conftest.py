"""Standard setup for tests."""
from collections.abc import Generator
from unittest.mock import AsyncMock, create_autospec, patch

from haphilipsjs import PhilipsTV
import pytest

from homeassistant.components.philips_js.const import DOMAIN

from . import MOCK_CONFIG, MOCK_ENTITY_ID, MOCK_NAME, MOCK_SERIAL_NO, MOCK_SYSTEM

from tests.common import MockConfigEntry, mock_device_registry


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock, None, None]:
    """Disable component setup."""
    with patch(
        "homeassistant.components.philips_js.async_setup_entry", return_value=True
    ) as mock_setup_entry, patch(
        "homeassistant.components.philips_js.async_unload_entry", return_value=True
    ):
        yield mock_setup_entry


@pytest.fixture(autouse=True)
async def setup_notification(hass):
    """Configure notification system."""


@pytest.fixture(autouse=True)
def mock_tv():
    """Disable component actual use."""
    tv = create_autospec(PhilipsTV)
    tv.sources = {}
    tv.channels = {}
    tv.application = None
    tv.applications = {}
    tv.system = MOCK_SYSTEM
    tv.api_version = 1
    tv.api_version_detected = None
    tv.on = True
    tv.notify_change_supported = False
    tv.pairing_type = None
    tv.powerstate = None
    tv.source_id = None
    tv.ambilight_current_configuration = None
    tv.ambilight_styles = {}
    tv.ambilight_cached = {}

    with patch(
        "homeassistant.components.philips_js.config_flow.PhilipsTV", return_value=tv
    ), patch("homeassistant.components.philips_js.PhilipsTV", return_value=tv):
        yield tv


@pytest.fixture
async def mock_config_entry(hass):
    """Get standard player."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG, title=MOCK_NAME, unique_id=MOCK_SERIAL_NO
    )
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.fixture
def mock_device_reg(hass):
    """Get standard device."""
    return mock_device_registry(hass)


@pytest.fixture
async def mock_entity(hass, mock_device_reg, mock_config_entry):
    """Get standard player."""
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return MOCK_ENTITY_ID


@pytest.fixture
def mock_device(hass, mock_device_reg, mock_entity, mock_config_entry):
    """Get standard device."""
    return mock_device_reg.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, MOCK_SERIAL_NO)},
    )
