"""Test NAM diagnostics."""
import json

from homeassistant.core import HomeAssistant

from . import init_integration

from tests.common import load_fixture
from tests.components.diagnostics import get_diagnostics_for_config_entry
from tests.typing import ClientSessionGenerator


async def test_entry_diagnostics(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """Test config entry diagnostics."""
    entry = await init_integration(hass)

    diagnostics_data = json.loads(load_fixture("diagnostics_data.json", "nam"))

    result = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert result["info"] == {"host": "10.10.2.3"}
    assert result["data"] == diagnostics_data
