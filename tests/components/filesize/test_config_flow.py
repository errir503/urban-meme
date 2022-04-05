"""Tests for the Filesize config flow."""
from unittest.mock import patch

import pytest

from homeassistant.components.filesize.const import DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import CONF_FILE_PATH
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import (
    RESULT_TYPE_ABORT,
    RESULT_TYPE_CREATE_ENTRY,
    RESULT_TYPE_FORM,
)

from . import TEST_DIR, TEST_FILE, TEST_FILE_NAME, create_file

from tests.common import MockConfigEntry


async def test_full_user_flow(hass: HomeAssistant) -> None:
    """Test the full user configuration flow."""
    create_file(TEST_FILE)
    hass.config.allowlist_external_dirs = {TEST_DIR}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result.get("type") == RESULT_TYPE_FORM
    assert result.get("step_id") == SOURCE_USER
    assert "flow_id" in result

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_FILE_PATH: TEST_FILE},
    )

    assert result2.get("type") == RESULT_TYPE_CREATE_ENTRY
    assert result2.get("title") == TEST_FILE_NAME
    assert result2.get("data") == {CONF_FILE_PATH: TEST_FILE}


@pytest.mark.parametrize("source", [SOURCE_USER, SOURCE_IMPORT])
async def test_unique_path(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    source: str,
) -> None:
    """Test we abort if already setup."""
    hass.config.allowlist_external_dirs = {TEST_DIR}
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": source}, data={CONF_FILE_PATH: TEST_FILE}
    )

    assert result.get("type") == RESULT_TYPE_ABORT
    assert result.get("reason") == "already_configured"


async def test_import_flow(hass: HomeAssistant) -> None:
    """Test the import configuration flow."""
    create_file(TEST_FILE)
    hass.config.allowlist_external_dirs = {TEST_DIR}
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_FILE_PATH: TEST_FILE},
    )

    assert result.get("type") == RESULT_TYPE_CREATE_ENTRY
    assert result.get("title") == TEST_FILE_NAME
    assert result.get("data") == {CONF_FILE_PATH: TEST_FILE}


async def test_flow_fails_on_validation(hass: HomeAssistant) -> None:
    """Test config flow errors."""
    create_file(TEST_FILE)
    hass.config.allowlist_external_dirs = {}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] == RESULT_TYPE_FORM
    assert result["step_id"] == SOURCE_USER

    with patch(
        "homeassistant.components.filesize.config_flow.pathlib.Path",
        side_effect=OSError,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_FILE_PATH: TEST_FILE,
            },
        )

    assert result2["errors"] == {"base": "not_valid"}

    with patch("homeassistant.components.filesize.config_flow.pathlib.Path",), patch(
        "homeassistant.components.filesize.async_setup_entry",
        return_value=True,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_FILE_PATH: TEST_FILE,
            },
        )

    assert result2["errors"] == {"base": "not_allowed"}

    hass.config.allowlist_external_dirs = {TEST_DIR}
    with patch("homeassistant.components.filesize.config_flow.pathlib.Path",), patch(
        "homeassistant.components.filesize.async_setup_entry",
        return_value=True,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_FILE_PATH: TEST_FILE,
            },
        )

    assert result2["type"] == RESULT_TYPE_CREATE_ENTRY
    assert result2["title"] == TEST_FILE_NAME
    assert result2["data"] == {
        CONF_FILE_PATH: TEST_FILE,
    }
