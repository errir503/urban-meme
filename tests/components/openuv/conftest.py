"""Define test fixtures for OpenUV."""
import json
from unittest.mock import patch

import pytest

from homeassistant.components.openuv import CONF_FROM_WINDOW, CONF_TO_WINDOW, DOMAIN
from homeassistant.const import (
    CONF_API_KEY,
    CONF_ELEVATION,
    CONF_LATITUDE,
    CONF_LONGITUDE,
)
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry, load_fixture


@pytest.fixture(name="config_entry")
def config_entry_fixture(hass, config):
    """Define a config entry fixture."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{config[CONF_LATITUDE]}, {config[CONF_LONGITUDE]}",
        data=config,
        options={CONF_FROM_WINDOW: 3.5, CONF_TO_WINDOW: 3.5},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture(name="config")
def config_fixture(hass):
    """Define a config entry data fixture."""
    return {
        CONF_API_KEY: "abcde12345",
        CONF_ELEVATION: 0,
        CONF_LATITUDE: 51.528308,
        CONF_LONGITUDE: -0.3817765,
    }


@pytest.fixture(name="data_protection_window", scope="package")
def data_protection_window_fixture():
    """Define a fixture to return UV protection window data."""
    return json.loads(load_fixture("protection_window_data.json", "openuv"))


@pytest.fixture(name="data_uv_index", scope="package")
def data_uv_index_fixture():
    """Define a fixture to return UV index data."""
    return json.loads(load_fixture("uv_index_data.json", "openuv"))


@pytest.fixture(name="setup_openuv")
async def setup_openuv_fixture(hass, config, data_protection_window, data_uv_index):
    """Define a fixture to set up OpenUV."""
    with patch(
        "homeassistant.components.openuv.async_get_entity_id_from_unique_id_suffix",
    ), patch(
        "homeassistant.components.openuv.Client.uv_index", return_value=data_uv_index
    ), patch(
        "homeassistant.components.openuv.Client.uv_protection_window",
        return_value=data_protection_window,
    ), patch(
        "homeassistant.components.openuv.PLATFORMS", []
    ):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()
        yield
