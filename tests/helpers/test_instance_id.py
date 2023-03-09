"""Tests for instance ID helper."""
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import instance_id


async def test_get_id_empty(hass: HomeAssistant, hass_storage: dict[str, Any]) -> None:
    """Get unique ID."""
    uuid = await instance_id.async_get(hass)
    assert uuid is not None
    # Assert it's stored
    assert hass_storage["core.uuid"]["data"]["uuid"] == uuid


async def test_get_id_migrate(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Migrate existing file."""
    with patch(
        "homeassistant.util.json.load_json", return_value={"uuid": "1234"}
    ), patch("os.path.isfile", return_value=True), patch("os.remove") as mock_remove:
        uuid = await instance_id.async_get(hass)

    assert uuid == "1234"

    # Assert it's stored
    assert hass_storage["core.uuid"]["data"]["uuid"] == uuid

    # assert old deleted
    assert len(mock_remove.mock_calls) == 1
