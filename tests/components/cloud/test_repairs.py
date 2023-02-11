"""Test cloud repairs."""
from collections.abc import Generator
from datetime import timedelta
from http import HTTPStatus
from unittest.mock import AsyncMock, patch

from homeassistant.components.cloud import DOMAIN
import homeassistant.components.cloud.repairs as cloud_repairs
from homeassistant.components.repairs import DOMAIN as REPAIRS_DOMAIN
from homeassistant.core import HomeAssistant
import homeassistant.helpers.issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt

from . import mock_cloud

from tests.common import async_fire_time_changed
from tests.test_util.aiohttp import AiohttpClientMocker
from tests.typing import ClientSessionGenerator


async def test_do_not_create_repair_issues_at_startup_if_not_logged_in(
    hass: HomeAssistant,
) -> None:
    """Test that we create repair issue at startup if we are logged in."""
    issue_registry: ir.IssueRegistry = ir.async_get(hass)

    with patch("homeassistant.components.cloud.Cloud.is_logged_in", False):
        await mock_cloud(hass)

        async_fire_time_changed(hass, dt.utcnow() + timedelta(hours=1))
        await hass.async_block_till_done()

    assert not issue_registry.async_get_issue(
        domain="cloud", issue_id="legacy_subscription"
    )


async def test_create_repair_issues_at_startup_if_logged_in(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_auth: Generator[None, AsyncMock, None],
):
    """Test that we create repair issue at startup if we are logged in."""
    issue_registry: ir.IssueRegistry = ir.async_get(hass)
    aioclient_mock.get(
        "https://accounts.nabucasa.com/payments/subscription_info",
        json={"provider": "legacy"},
    )

    with patch("homeassistant.components.cloud.Cloud.is_logged_in", True):
        await mock_cloud(hass)

        async_fire_time_changed(hass, dt.utcnow() + timedelta(hours=1))
        await hass.async_block_till_done()

    assert issue_registry.async_get_issue(
        domain="cloud", issue_id="legacy_subscription"
    )


async def test_legacy_subscription_delete_issue_if_no_longer_legacy(
    hass: HomeAssistant,
) -> None:
    """Test that we delete the legacy subscription issue if no longer legacy."""
    issue_registry: ir.IssueRegistry = ir.async_get(hass)
    cloud_repairs.async_manage_legacy_subscription_issue(hass, {"provider": "legacy"})
    assert issue_registry.async_get_issue(
        domain="cloud", issue_id="legacy_subscription"
    )

    cloud_repairs.async_manage_legacy_subscription_issue(hass, {})
    assert not issue_registry.async_get_issue(
        domain="cloud", issue_id="legacy_subscription"
    )


async def test_legacy_subscription_repair_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_auth: Generator[None, AsyncMock, None],
    hass_client: ClientSessionGenerator,
):
    """Test desired flow of the fix flow for legacy subscription."""
    issue_registry: ir.IssueRegistry = ir.async_get(hass)
    aioclient_mock.get(
        "https://accounts.nabucasa.com/payments/subscription_info",
        json={"provider": None},
    )
    aioclient_mock.post(
        "https://accounts.nabucasa.com/payments/migrate_paypal_agreement",
        json={"url": "https://paypal.com"},
    )

    cloud_repairs.async_manage_legacy_subscription_issue(hass, {"provider": "legacy"})
    repair_issue = issue_registry.async_get_issue(
        domain="cloud", issue_id="legacy_subscription"
    )
    assert repair_issue

    assert await async_setup_component(hass, REPAIRS_DOMAIN, {REPAIRS_DOMAIN: {}})
    await mock_cloud(hass)
    await hass.async_block_till_done()
    await hass.async_start()

    client = await hass_client()

    resp = await client.post(
        "/api/repairs/issues/fix",
        json={"handler": DOMAIN, "issue_id": repair_issue.issue_id},
    )

    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data == {
        "type": "form",
        "flow_id": flow_id,
        "handler": DOMAIN,
        "step_id": "confirm_change_plan",
        "data_schema": [],
        "errors": None,
        "description_placeholders": None,
        "last_step": None,
    }

    resp = await client.post(f"/api/repairs/issues/fix/{flow_id}")

    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data == {
        "type": "external",
        "flow_id": flow_id,
        "handler": DOMAIN,
        "step_id": "change_plan",
        "url": "https://paypal.com",
        "description_placeholders": None,
    }

    resp = await client.post(f"/api/repairs/issues/fix/{flow_id}")

    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data == {
        "version": 1,
        "type": "create_entry",
        "flow_id": flow_id,
        "handler": DOMAIN,
        "description": None,
        "description_placeholders": None,
    }

    assert not issue_registry.async_get_issue(
        domain="cloud", issue_id="legacy_subscription"
    )


async def test_legacy_subscription_repair_flow_timeout(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_auth: Generator[None, AsyncMock, None],
    aioclient_mock: AiohttpClientMocker,
):
    """Test timeout flow of the fix flow for legacy subscription."""
    aioclient_mock.post(
        "https://accounts.nabucasa.com/payments/migrate_paypal_agreement",
        status=403,
    )

    issue_registry: ir.IssueRegistry = ir.async_get(hass)

    cloud_repairs.async_manage_legacy_subscription_issue(hass, {"provider": "legacy"})
    repair_issue = issue_registry.async_get_issue(
        domain="cloud", issue_id="legacy_subscription"
    )
    assert repair_issue

    assert await async_setup_component(hass, REPAIRS_DOMAIN, {REPAIRS_DOMAIN: {}})
    await mock_cloud(hass)
    await hass.async_block_till_done()
    await hass.async_start()

    client = await hass_client()

    resp = await client.post(
        "/api/repairs/issues/fix",
        json={"handler": DOMAIN, "issue_id": repair_issue.issue_id},
    )

    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data == {
        "type": "form",
        "flow_id": flow_id,
        "handler": DOMAIN,
        "step_id": "confirm_change_plan",
        "data_schema": [],
        "errors": None,
        "description_placeholders": None,
        "last_step": None,
    }

    with patch("homeassistant.components.cloud.repairs.MAX_RETRIES", new=0):
        resp = await client.post(f"/api/repairs/issues/fix/{flow_id}")
        assert resp.status == HTTPStatus.OK
        data = await resp.json()

        flow_id = data["flow_id"]
        assert data == {
            "type": "external",
            "flow_id": flow_id,
            "handler": DOMAIN,
            "step_id": "change_plan",
            "url": "https://account.nabucasa.com/",
            "description_placeholders": None,
        }

    resp = await client.post(f"/api/repairs/issues/fix/{flow_id}")
    assert resp.status == HTTPStatus.OK
    data = await resp.json()

    flow_id = data["flow_id"]
    assert data == {
        "type": "abort",
        "flow_id": flow_id,
        "handler": "cloud",
        "reason": "operation_took_too_long",
        "description_placeholders": None,
        "result": None,
    }

    assert issue_registry.async_get_issue(
        domain="cloud", issue_id="legacy_subscription"
    )
