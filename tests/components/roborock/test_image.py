"""Test Roborock Image platform."""
import copy
from datetime import timedelta
from http import HTTPStatus
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from tests.common import MockConfigEntry, async_fire_time_changed
from tests.components.roborock.mock_data import MAP_DATA, PROP
from tests.typing import ClientSessionGenerator


async def test_floorplan_image(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test floor plan map image is correctly set up."""
    # Setup calls the image parsing the first time and caches it.
    assert len(hass.states.async_all("image")) == 4

    assert hass.states.get("image.roborock_s7_maxv_upstairs") is not None
    # call a second time -should return cached data
    client = await hass_client()
    resp = await client.get("/api/image_proxy/image.roborock_s7_maxv_upstairs")
    assert resp.status == HTTPStatus.OK
    body = await resp.read()
    assert body is not None
    # Call a third time - this time forcing it to update
    now = dt_util.utcnow() + timedelta(seconds=91)
    async_fire_time_changed(hass, now)
    # Copy the device prop so we don't override it
    prop = copy.deepcopy(PROP)
    prop.status.in_cleaning = 1
    with patch(
        "homeassistant.components.roborock.coordinator.RoborockLocalClient.get_prop",
        return_value=prop,
    ), patch(
        "homeassistant.components.roborock.image.dt_util.utcnow", return_value=now
    ):
        await hass.async_block_till_done()
        resp = await client.get("/api/image_proxy/image.roborock_s7_maxv_upstairs")
    assert resp.status == HTTPStatus.OK
    body = await resp.read()
    assert body is not None


async def test_floorplan_image_failed_parse(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test that we correctly handle getting None from the image parser."""
    client = await hass_client()
    map_data = copy.deepcopy(MAP_DATA)
    map_data.image = None
    now = dt_util.utcnow() + timedelta(seconds=91)
    async_fire_time_changed(hass, now)
    # Copy the device prop so we don't override it
    prop = copy.deepcopy(PROP)
    prop.status.in_cleaning = 1
    # Update image, but get none for parse image.
    with patch(
        "homeassistant.components.roborock.image.RoborockMapDataParser.parse",
        return_value=map_data,
    ), patch(
        "homeassistant.components.roborock.coordinator.RoborockLocalClient.get_prop",
        return_value=prop,
    ), patch(
        "homeassistant.components.roborock.image.dt_util.utcnow", return_value=now
    ):
        resp = await client.get("/api/image_proxy/image.roborock_s7_maxv_upstairs")
    assert not resp.ok
