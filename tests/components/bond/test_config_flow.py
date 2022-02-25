"""Test the Bond config flow."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from aiohttp import ClientConnectionError, ClientResponseError

from homeassistant import config_entries, core
from homeassistant.components import zeroconf
from homeassistant.components.bond.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_HOST

from .common import (
    patch_bond_bridge,
    patch_bond_device,
    patch_bond_device_ids,
    patch_bond_device_properties,
    patch_bond_token,
    patch_bond_version,
)

from tests.common import MockConfigEntry


async def test_user_form(hass: core.HomeAssistant):
    """Test we get the user initiated form."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch_bond_version(
        return_value={"bondid": "test-bond-id"}
    ), patch_bond_device_ids(
        return_value=["f6776c11", "f6776c12"]
    ), patch_bond_bridge(), patch_bond_device_properties(), patch_bond_device(), _patch_async_setup_entry() as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "some host", CONF_ACCESS_TOKEN: "test-token"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "bond-name"
    assert result2["data"] == {
        CONF_HOST: "some host",
        CONF_ACCESS_TOKEN: "test-token",
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_form_with_non_bridge(hass: core.HomeAssistant):
    """Test setup a smart by bond fan."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch_bond_version(
        return_value={"bondid": "test-bond-id"}
    ), patch_bond_device_ids(
        return_value=["f6776c11"]
    ), patch_bond_device_properties(), patch_bond_device(
        return_value={
            "name": "New Fan",
        }
    ), patch_bond_bridge(
        return_value={}
    ), _patch_async_setup_entry() as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "some host", CONF_ACCESS_TOKEN: "test-token"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "New Fan"
    assert result2["data"] == {
        CONF_HOST: "some host",
        CONF_ACCESS_TOKEN: "test-token",
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_form_invalid_auth(hass: core.HomeAssistant):
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch_bond_version(
        return_value={"bond_id": "test-bond-id"}
    ), patch_bond_bridge(), patch_bond_device_ids(
        side_effect=ClientResponseError(Mock(), Mock(), status=401),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "some host", CONF_ACCESS_TOKEN: "test-token"},
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_user_form_cannot_connect(hass: core.HomeAssistant):
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch_bond_version(
        side_effect=ClientConnectionError()
    ), patch_bond_bridge(), patch_bond_device_ids():
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "some host", CONF_ACCESS_TOKEN: "test-token"},
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_user_form_old_firmware(hass: core.HomeAssistant):
    """Test we handle unsupported old firmware."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch_bond_version(
        return_value={"no_bond_id": "present"}
    ), patch_bond_bridge(), patch_bond_device_ids():
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "some host", CONF_ACCESS_TOKEN: "test-token"},
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "old_firmware"}


async def test_user_form_unexpected_client_error(hass: core.HomeAssistant):
    """Test we handle unexpected client error gracefully."""
    await _help_test_form_unexpected_error(
        hass,
        source=config_entries.SOURCE_USER,
        user_input={CONF_HOST: "some host", CONF_ACCESS_TOKEN: "test-token"},
        error=ClientResponseError(Mock(), Mock(), status=500),
    )


async def test_user_form_unexpected_error(hass: core.HomeAssistant):
    """Test we handle unexpected error gracefully."""
    await _help_test_form_unexpected_error(
        hass,
        source=config_entries.SOURCE_USER,
        user_input={CONF_HOST: "some host", CONF_ACCESS_TOKEN: "test-token"},
        error=Exception(),
    )


async def test_user_form_one_entry_per_device_allowed(hass: core.HomeAssistant):
    """Test that only one entry allowed per unique ID reported by Bond hub device."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="already-registered-bond-id",
        data={CONF_HOST: "some host", CONF_ACCESS_TOKEN: "test-token"},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch_bond_version(
        return_value={"bondid": "already-registered-bond-id"}
    ), patch_bond_bridge(), patch_bond_device_ids(), _patch_async_setup_entry() as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "some host", CONF_ACCESS_TOKEN: "test-token"},
        )

    assert result2["type"] == "abort"
    assert result2["reason"] == "already_configured"

    await hass.async_block_till_done()
    assert len(mock_setup_entry.mock_calls) == 0


async def test_zeroconf_form(hass: core.HomeAssistant):
    """Test we get the discovery form."""

    with patch_bond_version(), patch_bond_token():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=zeroconf.ZeroconfServiceInfo(
                host="test-host",
                addresses=["test-host"],
                hostname="mock_hostname",
                name="test-bond-id.some-other-tail-info",
                port=None,
                properties={},
                type="mock_type",
            ),
        )
        assert result["type"] == "form"
        assert result["errors"] == {}

    with patch_bond_version(
        return_value={"bondid": "test-bond-id"}
    ), patch_bond_bridge(), patch_bond_device_ids(), _patch_async_setup_entry() as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "test-token"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "bond-name"
    assert result2["data"] == {
        CONF_HOST: "test-host",
        CONF_ACCESS_TOKEN: "test-token",
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_zeroconf_form_token_unavailable(hass: core.HomeAssistant):
    """Test we get the discovery form and we handle the token being unavailable."""

    with patch_bond_version(), patch_bond_token():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=zeroconf.ZeroconfServiceInfo(
                host="test-host",
                addresses=["test-host"],
                hostname="mock_hostname",
                name="test-bond-id.some-other-tail-info",
                port=None,
                properties={},
                type="mock_type",
            ),
        )
        await hass.async_block_till_done()
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch_bond_version(), patch_bond_bridge(), patch_bond_device_ids(), _patch_async_setup_entry() as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ACCESS_TOKEN: "test-token"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "bond-name"
    assert result2["data"] == {
        CONF_HOST: "test-host",
        CONF_ACCESS_TOKEN: "test-token",
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_zeroconf_form_with_token_available(hass: core.HomeAssistant):
    """Test we get the discovery form when we can get the token."""

    with patch_bond_version(return_value={"bondid": "test-bond-id"}), patch_bond_token(
        return_value={"token": "discovered-token"}
    ), patch_bond_bridge(
        return_value={"name": "discovered-name"}
    ), patch_bond_device_ids():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=zeroconf.ZeroconfServiceInfo(
                host="test-host",
                addresses=["test-host"],
                hostname="mock_hostname",
                name="test-bond-id.some-other-tail-info",
                port=None,
                properties={},
                type="mock_type",
            ),
        )
        await hass.async_block_till_done()
    assert result["type"] == "form"
    assert result["errors"] == {}

    with _patch_async_setup_entry() as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "discovered-name"
    assert result2["data"] == {
        CONF_HOST: "test-host",
        CONF_ACCESS_TOKEN: "discovered-token",
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_zeroconf_form_with_token_available_name_unavailable(
    hass: core.HomeAssistant,
):
    """Test we get the discovery form when we can get the token but the name is unavailable."""

    with patch_bond_version(
        side_effect=ClientResponseError(Mock(), (), status=HTTPStatus.BAD_REQUEST)
    ), patch_bond_token(return_value={"token": "discovered-token"}):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=zeroconf.ZeroconfServiceInfo(
                host="test-host",
                addresses=["test-host"],
                hostname="mock_hostname",
                name="test-bond-id.some-other-tail-info",
                port=None,
                properties={},
                type="mock_type",
            ),
        )
        await hass.async_block_till_done()
    assert result["type"] == "form"
    assert result["errors"] == {}

    with _patch_async_setup_entry() as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "test-bond-id"
    assert result2["data"] == {
        CONF_HOST: "test-host",
        CONF_ACCESS_TOKEN: "discovered-token",
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_zeroconf_already_configured(hass: core.HomeAssistant):
    """Test starting a flow from discovery when already configured."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="already-registered-bond-id",
        data={CONF_HOST: "stored-host", CONF_ACCESS_TOKEN: "test-token"},
    )
    entry.add_to_hass(hass)

    with _patch_async_setup_entry() as mock_setup_entry:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=zeroconf.ZeroconfServiceInfo(
                host="updated-host",
                addresses=["updated-host"],
                hostname="mock_hostname",
                name="already-registered-bond-id.some-other-tail-info",
                port=None,
                properties={},
                type="mock_type",
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "updated-host"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_zeroconf_already_configured_refresh_token(hass: core.HomeAssistant):
    """Test starting a flow from zeroconf when already configured and the token is out of date."""
    entry2 = MockConfigEntry(
        domain=DOMAIN,
        unique_id="not-the-same-bond-id",
        data={CONF_HOST: "stored-host", CONF_ACCESS_TOKEN: "correct-token"},
    )
    entry2.add_to_hass(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="already-registered-bond-id",
        data={CONF_HOST: "stored-host", CONF_ACCESS_TOKEN: "incorrect-token"},
    )
    entry.add_to_hass(hass)

    with patch_bond_version(
        side_effect=ClientResponseError(MagicMock(), MagicMock(), status=401)
    ):
        await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR

    with _patch_async_setup_entry() as mock_setup_entry, patch_bond_token(
        return_value={"token": "discovered-token"}
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=zeroconf.ZeroconfServiceInfo(
                host="updated-host",
                addresses=["updated-host"],
                hostname="mock_hostname",
                name="already-registered-bond-id.some-other-tail-info",
                port=None,
                properties={},
                type="mock_type",
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "updated-host"
    assert entry.data[CONF_ACCESS_TOKEN] == "discovered-token"
    # entry2 should not get changed
    assert entry2.data[CONF_ACCESS_TOKEN] == "correct-token"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_zeroconf_already_configured_no_reload_same_host(
    hass: core.HomeAssistant,
):
    """Test starting a flow from zeroconf when already configured does not reload if the host is the same."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="already-registered-bond-id",
        data={CONF_HOST: "stored-host", CONF_ACCESS_TOKEN: "correct-token"},
    )
    entry.add_to_hass(hass)

    with _patch_async_setup_entry() as mock_setup_entry, patch_bond_token(
        return_value={"token": "correct-token"}
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=zeroconf.ZeroconfServiceInfo(
                host="stored-host",
                addresses=["stored-host"],
                hostname="mock_hostname",
                name="already-registered-bond-id.some-other-tail-info",
                port=None,
                properties={},
                type="mock_type",
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    assert len(mock_setup_entry.mock_calls) == 0


async def test_zeroconf_form_unexpected_error(hass: core.HomeAssistant):
    """Test we handle unexpected error gracefully."""
    await _help_test_form_unexpected_error(
        hass,
        source=config_entries.SOURCE_ZEROCONF,
        initial_input=zeroconf.ZeroconfServiceInfo(
            host="test-host",
            addresses=["test-host"],
            hostname="mock_hostname",
            name="test-bond-id.some-other-tail-info",
            port=None,
            properties={},
            type="mock_type",
        ),
        user_input={CONF_ACCESS_TOKEN: "test-token"},
        error=Exception(),
    )


async def _help_test_form_unexpected_error(
    hass: core.HomeAssistant,
    *,
    source: str,
    initial_input: dict[str, Any] = None,
    user_input: dict[str, Any],
    error: Exception,
):
    """Test we handle unexpected error gracefully."""
    with patch_bond_token():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": source}, data=initial_input
        )

    with patch_bond_version(
        return_value={"bond_id": "test-bond-id"}
    ), patch_bond_device_ids(side_effect=error):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "unknown"}


def _patch_async_setup_entry():
    return patch(
        "homeassistant.components.bond.async_setup_entry",
        return_value=True,
    )
