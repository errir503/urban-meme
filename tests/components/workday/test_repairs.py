"""Test repairs for unifiprotect."""
from __future__ import annotations

from http import HTTPStatus

from homeassistant.components.repairs.websocket_api import (
    RepairsFlowIndexView,
    RepairsFlowResourceView,
)
from homeassistant.components.workday.const import DOMAIN
from homeassistant.const import CONF_COUNTRY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import async_create_issue
from homeassistant.setup import async_setup_component

from . import (
    TEST_CONFIG_INCORRECT_COUNTRY,
    TEST_CONFIG_INCORRECT_PROVINCE,
    init_integration,
)

from tests.common import ANY
from tests.typing import ClientSessionGenerator, WebSocketGenerator


async def test_bad_country(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test fixing bad country."""
    assert await async_setup_component(hass, "repairs", {})
    entry = await init_integration(hass, TEST_CONFIG_INCORRECT_COUNTRY)

    state = hass.states.get("binary_sensor.workday_sensor")
    assert not state

    ws_client = await hass_ws_client(hass)
    client = await hass_client()

    await ws_client.send_json({"id": 1, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    assert len(msg["result"]["issues"]) > 0
    issue = None
    for i in msg["result"]["issues"]:
        if i["issue_id"] == "bad_country":
            issue = i
    assert issue is not None

    url = RepairsFlowIndexView.url
    resp = await client.post(url, json={"handler": DOMAIN, "issue_id": "bad_country"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data["description_placeholders"] == {"title": entry.title}
    assert data["step_id"] == "country"

    url = RepairsFlowResourceView.url.format(flow_id=flow_id)
    resp = await client.post(url, json={"country": "DE"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    url = RepairsFlowResourceView.url.format(flow_id=flow_id)
    resp = await client.post(url, json={"province": "HB"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    assert data["type"] == "create_entry"
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.workday_sensor")
    assert state

    await ws_client.send_json({"id": 2, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    issue = None
    for i in msg["result"]["issues"]:
        if i["issue_id"] == "bad_country":
            issue = i
    assert not issue


async def test_bad_country_none(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test fixing bad country with no province."""
    assert await async_setup_component(hass, "repairs", {})
    entry = await init_integration(hass, TEST_CONFIG_INCORRECT_COUNTRY)

    state = hass.states.get("binary_sensor.workday_sensor")
    assert not state

    ws_client = await hass_ws_client(hass)
    client = await hass_client()

    await ws_client.send_json({"id": 1, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    assert len(msg["result"]["issues"]) > 0
    issue = None
    for i in msg["result"]["issues"]:
        if i["issue_id"] == "bad_country":
            issue = i
    assert issue is not None

    url = RepairsFlowIndexView.url
    resp = await client.post(url, json={"handler": DOMAIN, "issue_id": "bad_country"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data["description_placeholders"] == {"title": entry.title}
    assert data["step_id"] == "country"

    url = RepairsFlowResourceView.url.format(flow_id=flow_id)
    resp = await client.post(url, json={"country": "DE"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    url = RepairsFlowResourceView.url.format(flow_id=flow_id)
    resp = await client.post(url, json={})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    assert data["type"] == "create_entry"
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.workday_sensor")
    assert state

    await ws_client.send_json({"id": 2, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    issue = None
    for i in msg["result"]["issues"]:
        if i["issue_id"] == "bad_country":
            issue = i
    assert not issue


async def test_bad_country_no_province(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test fixing bad country."""
    assert await async_setup_component(hass, "repairs", {})
    entry = await init_integration(hass, TEST_CONFIG_INCORRECT_COUNTRY)

    state = hass.states.get("binary_sensor.workday_sensor")
    assert not state

    ws_client = await hass_ws_client(hass)
    client = await hass_client()

    await ws_client.send_json({"id": 1, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    assert len(msg["result"]["issues"]) > 0
    issue = None
    for i in msg["result"]["issues"]:
        if i["issue_id"] == "bad_country":
            issue = i
    assert issue is not None

    url = RepairsFlowIndexView.url
    resp = await client.post(url, json={"handler": DOMAIN, "issue_id": "bad_country"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data["description_placeholders"] == {"title": entry.title}
    assert data["step_id"] == "country"

    url = RepairsFlowResourceView.url.format(flow_id=flow_id)
    resp = await client.post(url, json={"country": "SE"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    assert data["type"] == "create_entry"
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.workday_sensor")
    assert state

    await ws_client.send_json({"id": 2, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    issue = None
    for i in msg["result"]["issues"]:
        if i["issue_id"] == "bad_country":
            issue = i
    assert not issue


async def test_bad_province(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test fixing bad province."""
    assert await async_setup_component(hass, "repairs", {})
    entry = await init_integration(hass, TEST_CONFIG_INCORRECT_PROVINCE)

    state = hass.states.get("binary_sensor.workday_sensor")
    assert not state

    ws_client = await hass_ws_client(hass)
    client = await hass_client()

    await ws_client.send_json({"id": 1, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    assert len(msg["result"]["issues"]) > 0
    issue = None
    for i in msg["result"]["issues"]:
        if i["issue_id"] == "bad_province":
            issue = i
    assert issue is not None

    url = RepairsFlowIndexView.url
    resp = await client.post(url, json={"handler": DOMAIN, "issue_id": "bad_province"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data["description_placeholders"] == {
        CONF_COUNTRY: "DE",
        "title": entry.title,
    }
    assert data["step_id"] == "province"

    url = RepairsFlowResourceView.url.format(flow_id=flow_id)
    resp = await client.post(url, json={"province": "BW"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    assert data["type"] == "create_entry"
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.workday_sensor")
    assert state

    await ws_client.send_json({"id": 2, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    issue = None
    for i in msg["result"]["issues"]:
        if i["issue_id"] == "bad_province":
            issue = i
    assert not issue


async def test_bad_province_none(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test fixing bad province selecting none."""
    assert await async_setup_component(hass, "repairs", {})
    entry = await init_integration(hass, TEST_CONFIG_INCORRECT_PROVINCE)

    state = hass.states.get("binary_sensor.workday_sensor")
    assert not state

    ws_client = await hass_ws_client(hass)
    client = await hass_client()

    await ws_client.send_json({"id": 1, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    assert len(msg["result"]["issues"]) > 0
    issue = None
    for i in msg["result"]["issues"]:
        if i["issue_id"] == "bad_province":
            issue = i
    assert issue is not None

    url = RepairsFlowIndexView.url
    resp = await client.post(url, json={"handler": DOMAIN, "issue_id": "bad_province"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data["description_placeholders"] == {
        CONF_COUNTRY: "DE",
        "title": entry.title,
    }
    assert data["step_id"] == "province"

    url = RepairsFlowResourceView.url.format(flow_id=flow_id)
    resp = await client.post(url, json={})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    assert data["type"] == "create_entry"
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.workday_sensor")
    assert state

    await ws_client.send_json({"id": 2, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    issue = None
    for i in msg["result"]["issues"]:
        if i["issue_id"] == "bad_province":
            issue = i
    assert not issue


async def test_other_fixable_issues(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test fixing bad province selecting none."""
    assert await async_setup_component(hass, "repairs", {})
    await init_integration(hass, TEST_CONFIG_INCORRECT_PROVINCE)

    ws_client = await hass_ws_client(hass)
    client = await hass_client()

    await ws_client.send_json({"id": 1, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]

    issue = {
        "breaks_in_ha_version": "2022.9.0dev0",
        "domain": DOMAIN,
        "issue_id": "issue_1",
        "is_fixable": True,
        "learn_more_url": "",
        "severity": "error",
        "translation_key": "issue_1",
    }
    async_create_issue(
        hass,
        issue["domain"],
        issue["issue_id"],
        breaks_in_ha_version=issue["breaks_in_ha_version"],
        is_fixable=issue["is_fixable"],
        is_persistent=False,
        learn_more_url=None,
        severity=issue["severity"],
        translation_key=issue["translation_key"],
    )

    await ws_client.send_json({"id": 2, "type": "repairs/list_issues"})
    msg = await ws_client.receive_json()

    assert msg["success"]
    results = msg["result"]["issues"]
    assert {
        "breaks_in_ha_version": "2022.9.0dev0",
        "created": ANY,
        "dismissed_version": None,
        "domain": "workday",
        "is_fixable": True,
        "issue_domain": None,
        "issue_id": "issue_1",
        "learn_more_url": None,
        "severity": "error",
        "translation_key": "issue_1",
        "translation_placeholders": None,
        "ignored": False,
    } in results

    url = RepairsFlowIndexView.url
    resp = await client.post(url, json={"handler": DOMAIN, "issue_id": "issue_1"})
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data["step_id"] == "confirm"

    url = RepairsFlowResourceView.url.format(flow_id=flow_id)
    resp = await client.post(url)
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    assert data["type"] == "create_entry"
    await hass.async_block_till_done()
