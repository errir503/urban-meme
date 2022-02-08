"""The tests for the filesize sensor."""
import os
from unittest.mock import patch

import pytest

from homeassistant import config as hass_config
from homeassistant.components.filesize import DOMAIN
from homeassistant.components.filesize.sensor import CONF_FILE_PATHS
from homeassistant.const import SERVICE_RELOAD, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import async_update_entity
from homeassistant.setup import async_setup_component

from tests.common import get_fixture_path

TEST_DIR = os.path.join(os.path.dirname(__file__))
TEST_FILE = os.path.join(TEST_DIR, "mock_file_test_filesize.txt")


def create_file(path) -> None:
    """Create a test file."""
    with open(path, "w") as test_file:
        test_file.write("test")


@pytest.fixture(autouse=True)
def remove_file() -> None:
    """Remove test file."""
    yield
    if os.path.isfile(TEST_FILE):
        os.remove(TEST_FILE)


async def test_invalid_path(hass: HomeAssistant) -> None:
    """Test that an invalid path is caught."""
    config = {"sensor": {"platform": "filesize", CONF_FILE_PATHS: ["invalid_path"]}}
    assert await async_setup_component(hass, "sensor", config)
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids("sensor")) == 0


async def test_cannot_access_file(hass: HomeAssistant) -> None:
    """Test that an invalid path is caught."""
    config = {"sensor": {"platform": "filesize", CONF_FILE_PATHS: [TEST_FILE]}}

    with patch(
        "homeassistant.components.filesize.sensor.pathlib",
        side_effect=OSError("Can not access"),
    ):
        assert await async_setup_component(hass, "sensor", config)
        await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids("sensor")) == 0


async def test_valid_path(hass: HomeAssistant) -> None:
    """Test for a valid path."""
    create_file(TEST_FILE)
    config = {"sensor": {"platform": "filesize", CONF_FILE_PATHS: [TEST_FILE]}}
    hass.config.allowlist_external_dirs = {TEST_DIR}
    assert await async_setup_component(hass, "sensor", config)
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids("sensor")) == 1
    state = hass.states.get("sensor.mock_file_test_filesize_txt")
    assert state.state == "0.0"
    assert state.attributes.get("bytes") == 4


async def test_state_unknown(hass: HomeAssistant, tmpdir: str) -> None:
    """Verify we handle state unavailable."""
    create_file(TEST_FILE)
    testfile = f"{tmpdir}/file"
    await hass.async_add_executor_job(create_file, testfile)
    with patch.object(hass.config, "is_allowed_path", return_value=True):
        await async_setup_component(
            hass,
            "sensor",
            {
                "sensor": {
                    "platform": "filesize",
                    "file_paths": [testfile],
                }
            },
        )
        await hass.async_block_till_done()

    assert hass.states.get("sensor.file")

    await hass.async_add_executor_job(os.remove, testfile)
    await async_update_entity(hass, "sensor.file")

    state = hass.states.get("sensor.file")
    assert state.state == STATE_UNKNOWN


async def test_reload(hass: HomeAssistant, tmpdir: str) -> None:
    """Verify we can reload filesize sensors."""
    testfile = f"{tmpdir}/file"
    await hass.async_add_executor_job(create_file, testfile)
    with patch.object(hass.config, "is_allowed_path", return_value=True):
        await async_setup_component(
            hass,
            "sensor",
            {
                "sensor": {
                    "platform": "filesize",
                    "file_paths": [testfile],
                }
            },
        )
        await hass.async_block_till_done()

    assert len(hass.states.async_all()) == 1

    assert hass.states.get("sensor.file")

    yaml_path = get_fixture_path("configuration.yaml", "filesize")
    with patch.object(hass_config, "YAML_CONFIG_FILE", yaml_path), patch.object(
        hass.config, "is_allowed_path", return_value=True
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RELOAD,
            {},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert hass.states.get("sensor.file") is None
