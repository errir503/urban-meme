"""Fixtures for the Scrape integration."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from homeassistant.components.rest.data import DEFAULT_TIMEOUT
from homeassistant.components.rest.schema import DEFAULT_METHOD, DEFAULT_VERIFY_SSL
from homeassistant.components.scrape.const import CONF_INDEX, CONF_SELECT, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    CONF_METHOD,
    CONF_NAME,
    CONF_RESOURCE,
    CONF_TIMEOUT,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant

from . import MockRestData

from tests.common import MockConfigEntry


@pytest.fixture(name="get_config")
async def get_config_to_integration_load() -> dict[str, Any]:
    """Return default minimal configuration.

    To override the config, tests can be marked with:
    @pytest.mark.parametrize("get_config", [{...}])
    """
    return {
        CONF_RESOURCE: "https://www.home-assistant.io",
        CONF_METHOD: DEFAULT_METHOD,
        CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
        CONF_TIMEOUT: DEFAULT_TIMEOUT,
        "sensor": [
            {
                CONF_NAME: "Current version",
                CONF_SELECT: ".current-version h1",
                CONF_INDEX: 0,
            }
        ],
    }


@pytest.fixture(name="get_data")
async def get_data_to_integration_load() -> MockRestData:
    """Return RestData.

    To override the config, tests can be marked with:
    @pytest.mark.parametrize("get_data", [{...}])
    """
    return MockRestData("test_scrape_sensor")


@pytest.fixture(name="loaded_entry")
async def load_integration(
    hass: HomeAssistant, get_config: dict[str, Any], get_data: MockRestData
) -> MockConfigEntry:
    """Set up the Scrape integration in Home Assistant."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        source=SOURCE_USER,
        options=get_config,
        entry_id="1",
    )

    config_entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.rest.RestData",
        return_value=get_data,
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    return config_entry
