"""Test the System Bridge config flow."""
from unittest.mock import patch

from aiohttp.client_exceptions import ClientConnectionError
from systembridge.exceptions import BridgeAuthenticationException

from homeassistant import config_entries, data_entry_flow
from homeassistant.components import zeroconf
from homeassistant.components.system_bridge.const import DOMAIN
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT

from tests.common import MockConfigEntry

FIXTURE_MAC_ADDRESS = "aa:bb:cc:dd:ee:ff"
FIXTURE_UUID = "e91bf575-56f3-4c83-8f42-70ac17adcd33"

FIXTURE_AUTH_INPUT = {CONF_API_KEY: "abc-123-def-456-ghi"}

FIXTURE_USER_INPUT = {
    CONF_API_KEY: "abc-123-def-456-ghi",
    CONF_HOST: "test-bridge",
    CONF_PORT: "9170",
}

FIXTURE_ZEROCONF_INPUT = {
    CONF_API_KEY: "abc-123-def-456-ghi",
    CONF_HOST: "1.1.1.1",
    CONF_PORT: "9170",
}

FIXTURE_ZEROCONF = zeroconf.ZeroconfServiceInfo(
    host="1.1.1.1",
    addresses=["1.1.1.1"],
    port=9170,
    hostname="test-bridge.local.",
    type="_system-bridge._udp.local.",
    name="System Bridge - test-bridge._system-bridge._udp.local.",
    properties={
        "address": "http://test-bridge:9170",
        "fqdn": "test-bridge",
        "host": "test-bridge",
        "ip": "1.1.1.1",
        "mac": FIXTURE_MAC_ADDRESS,
        "port": "9170",
        "uuid": FIXTURE_UUID,
    },
)

FIXTURE_ZEROCONF_BAD = zeroconf.ZeroconfServiceInfo(
    host="1.1.1.1",
    addresses=["1.1.1.1"],
    port=9170,
    hostname="test-bridge.local.",
    type="_system-bridge._udp.local.",
    name="System Bridge - test-bridge._system-bridge._udp.local.",
    properties={
        "something": "bad",
    },
)


FIXTURE_INFORMATION = {
    "address": "http://test-bridge:9170",
    "apiPort": 9170,
    "fqdn": "test-bridge",
    "host": "test-bridge",
    "ip": "1.1.1.1",
    "mac": FIXTURE_MAC_ADDRESS,
    "updates": {
        "available": False,
        "newer": False,
        "url": "https://github.com/timmo001/system-bridge/releases/tag/v2.3.2",
        "version": {"current": "2.3.2", "new": "2.3.2"},
    },
    "uuid": FIXTURE_UUID,
    "version": "2.3.2",
    "websocketAddress": "ws://test-bridge:9172",
    "websocketPort": 9172,
}


FIXTURE_BASE_URL = (
    f"http://{FIXTURE_USER_INPUT[CONF_HOST]}:{FIXTURE_USER_INPUT[CONF_PORT]}"
)

FIXTURE_ZEROCONF_BASE_URL = f"http://{FIXTURE_ZEROCONF.host}:{FIXTURE_ZEROCONF.port}"


async def test_user_flow(
    hass, aiohttp_client, aioclient_mock, current_request_with_host
) -> None:
    """Test full user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] is None

    aioclient_mock.get(
        f"{FIXTURE_BASE_URL}/information",
        headers={"Content-Type": "application/json"},
        json=FIXTURE_INFORMATION,
    )

    with patch(
        "homeassistant.components.system_bridge.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], FIXTURE_USER_INPUT
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result2["title"] == "test-bridge"
    assert result2["data"] == FIXTURE_USER_INPUT
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_invalid_auth(
    hass, aiohttp_client, aioclient_mock, current_request_with_host
) -> None:
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] is None

    aioclient_mock.get(
        f"{FIXTURE_BASE_URL}/information", exc=BridgeAuthenticationException
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], FIXTURE_USER_INPUT
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_form_cannot_connect(
    hass, aiohttp_client, aioclient_mock, current_request_with_host
) -> None:
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] is None

    aioclient_mock.get(f"{FIXTURE_BASE_URL}/information", exc=ClientConnectionError)

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], FIXTURE_USER_INPUT
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_unknown_error(
    hass, aiohttp_client, aioclient_mock, current_request_with_host
) -> None:
    """Test we handle unknown error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] is None

    with patch(
        "homeassistant.components.system_bridge.config_flow.Bridge.async_get_information",
        side_effect=Exception("Boom"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], FIXTURE_USER_INPUT
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": "unknown"}


async def test_reauth_authorization_error(
    hass, aiohttp_client, aioclient_mock, current_request_with_host
) -> None:
    """Test we show user form on authorization error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth"}, data=FIXTURE_USER_INPUT
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "authenticate"

    aioclient_mock.get(
        f"{FIXTURE_BASE_URL}/information", exc=BridgeAuthenticationException
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], FIXTURE_AUTH_INPUT
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["step_id"] == "authenticate"
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_reauth_connection_error(
    hass, aiohttp_client, aioclient_mock, current_request_with_host
) -> None:
    """Test we show user form on connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth"}, data=FIXTURE_USER_INPUT
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "authenticate"

    aioclient_mock.get(f"{FIXTURE_BASE_URL}/information", exc=ClientConnectionError)

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], FIXTURE_AUTH_INPUT
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["step_id"] == "authenticate"
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_reauth_flow(
    hass, aiohttp_client, aioclient_mock, current_request_with_host
) -> None:
    """Test reauth flow."""
    mock_config = MockConfigEntry(
        domain=DOMAIN, unique_id=FIXTURE_UUID, data=FIXTURE_USER_INPUT
    )
    mock_config.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth"}, data=FIXTURE_USER_INPUT
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "authenticate"

    aioclient_mock.get(
        f"{FIXTURE_BASE_URL}/information",
        headers={"Content-Type": "application/json"},
        json=FIXTURE_INFORMATION,
    )

    with patch(
        "homeassistant.components.system_bridge.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], FIXTURE_AUTH_INPUT
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result2["reason"] == "reauth_successful"

    assert len(mock_setup_entry.mock_calls) == 1


async def test_zeroconf_flow(
    hass, aiohttp_client, aioclient_mock, current_request_with_host
) -> None:
    """Test zeroconf flow."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=FIXTURE_ZEROCONF,
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert not result["errors"]

    aioclient_mock.get(
        f"{FIXTURE_ZEROCONF_BASE_URL}/information",
        headers={"Content-Type": "application/json"},
        json=FIXTURE_INFORMATION,
    )

    with patch(
        "homeassistant.components.system_bridge.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], FIXTURE_AUTH_INPUT
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result2["title"] == "test-bridge"
    assert result2["data"] == FIXTURE_ZEROCONF_INPUT
    assert len(mock_setup_entry.mock_calls) == 1


async def test_zeroconf_cannot_connect(
    hass, aiohttp_client, aioclient_mock, current_request_with_host
) -> None:
    """Test zeroconf cannot connect flow."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=FIXTURE_ZEROCONF,
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert not result["errors"]

    aioclient_mock.get(
        f"{FIXTURE_ZEROCONF_BASE_URL}/information", exc=ClientConnectionError
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], FIXTURE_AUTH_INPUT
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result2["step_id"] == "authenticate"
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_bad_zeroconf_info(
    hass, aiohttp_client, aioclient_mock, current_request_with_host
) -> None:
    """Test zeroconf cannot connect flow."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=FIXTURE_ZEROCONF_BAD,
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "unknown"
