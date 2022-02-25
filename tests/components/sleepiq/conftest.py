"""Common methods for SleepIQ."""
from unittest.mock import create_autospec, patch

from asyncsleepiq import SleepIQBed, SleepIQSleeper
import pytest

from homeassistant.components.sleepiq import DOMAIN
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

BED_ID = "123456"
BED_NAME = "Test Bed"
BED_NAME_LOWER = BED_NAME.lower().replace(" ", "_")
SLEEPER_L_NAME = "SleeperL"
SLEEPER_R_NAME = "Sleeper R"
SLEEPER_L_NAME_LOWER = SLEEPER_L_NAME.lower().replace(" ", "_")
SLEEPER_R_NAME_LOWER = SLEEPER_R_NAME.lower().replace(" ", "_")


@pytest.fixture
def mock_asyncsleepiq():
    """Mock an AsyncSleepIQ object."""
    with patch("homeassistant.components.sleepiq.AsyncSleepIQ", autospec=True) as mock:
        client = mock.return_value
        bed = create_autospec(SleepIQBed)
        client.beds = {BED_ID: bed}
        bed.name = BED_NAME
        bed.id = BED_ID
        bed.mac_addr = "12:34:56:78:AB:CD"
        bed.model = "C10"
        bed.paused = False
        sleeper_l = create_autospec(SleepIQSleeper)
        sleeper_r = create_autospec(SleepIQSleeper)
        bed.sleepers = [sleeper_l, sleeper_r]

        sleeper_l.side = "L"
        sleeper_l.name = SLEEPER_L_NAME
        sleeper_l.in_bed = True
        sleeper_l.sleep_number = 40

        sleeper_r.side = "R"
        sleeper_r.name = SLEEPER_R_NAME
        sleeper_r.in_bed = False
        sleeper_r.sleep_number = 80

        yield client


async def setup_platform(hass: HomeAssistant, platform) -> MockConfigEntry:
    """Set up the SleepIQ platform."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@email.com",
            CONF_PASSWORD: "password",
        },
    )
    mock_entry.add_to_hass(hass)

    if platform:
        with patch("homeassistant.components.sleepiq.PLATFORMS", [platform]):
            assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

    return mock_entry
