"""Define tests for the Airzone coordinator."""

from unittest.mock import MagicMock, patch

from aiohttp import ClientConnectorError

from homeassistant.components.airzone.const import DOMAIN
from homeassistant.components.airzone.coordinator import SCAN_INTERVAL
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import utcnow

from .util import CONFIG, HVAC_MOCK

from tests.common import MockConfigEntry, async_fire_time_changed


async def test_coordinator_client_connector_error(hass: HomeAssistant) -> None:
    """Test ClientConnectorError on coordinator update."""

    entry = MockConfigEntry(domain=DOMAIN, data=CONFIG)
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.airzone.AirzoneLocalApi.get_hvac",
        return_value=HVAC_MOCK,
    ) as mock_hvac:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        mock_hvac.assert_called_once()
        mock_hvac.reset_mock()

        mock_hvac.side_effect = ClientConnectorError(MagicMock(), MagicMock())
        async_fire_time_changed(hass, utcnow() + SCAN_INTERVAL)
        await hass.async_block_till_done()
        mock_hvac.assert_called_once()

        state = hass.states.get("sensor.despacho_temperature")
        assert state.state == STATE_UNAVAILABLE
