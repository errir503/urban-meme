"""Test OTBR Websocket API."""
from unittest.mock import Mock, patch

import pytest
import python_otbr_api

from homeassistant.components import otbr, thread
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from . import BASE_URL, DATASET_CH15, DATASET_CH16

from tests.test_util.aiohttp import AiohttpClientMocker
from tests.typing import WebSocketGenerator


@pytest.fixture
async def websocket_client(hass, hass_ws_client):
    """Create a websocket client."""
    return await hass_ws_client(hass)


async def test_get_info(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test async_get_info."""

    aioclient_mock.get(f"{BASE_URL}/node/dataset/active", text=DATASET_CH16.hex())

    await websocket_client.send_json_auto_id({"type": "otbr/info"})

    msg = await websocket_client.receive_json()
    assert msg["success"]
    assert msg["result"] == {
        "url": BASE_URL,
        "active_dataset_tlvs": DATASET_CH16.hex().lower(),
    }


async def test_get_info_no_entry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test async_get_info."""
    await async_setup_component(hass, "otbr", {})
    websocket_client = await hass_ws_client(hass)
    await websocket_client.send_json_auto_id({"type": "otbr/info"})

    msg = await websocket_client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_loaded"


async def test_get_info_fetch_fails(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test async_get_info."""
    with patch(
        "python_otbr_api.OTBR.get_active_dataset_tlvs",
        side_effect=python_otbr_api.OTBRError,
    ):
        await websocket_client.send_json_auto_id({"type": "otbr/info"})
        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "get_dataset_failed"


async def test_create_network(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test create network."""

    with patch(
        "python_otbr_api.OTBR.create_active_dataset"
    ) as create_dataset_mock, patch(
        "python_otbr_api.OTBR.set_enabled"
    ) as set_enabled_mock, patch(
        "python_otbr_api.OTBR.get_active_dataset_tlvs", return_value=DATASET_CH16
    ) as get_active_dataset_tlvs_mock, patch(
        "homeassistant.components.thread.dataset_store.DatasetStore.async_add"
    ) as mock_add:
        await websocket_client.send_json_auto_id({"type": "otbr/create_network"})

        msg = await websocket_client.receive_json()
        assert msg["success"]
        assert msg["result"] is None

    create_dataset_mock.assert_called_once_with(
        python_otbr_api.models.OperationalDataSet(
            channel=15, network_name="home-assistant"
        )
    )
    assert len(set_enabled_mock.mock_calls) == 2
    assert set_enabled_mock.mock_calls[0][1][0] is False
    assert set_enabled_mock.mock_calls[1][1][0] is True
    get_active_dataset_tlvs_mock.assert_called_once()
    mock_add.assert_called_once_with(otbr.DOMAIN, DATASET_CH16.hex())


async def test_create_network_no_entry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test create network."""
    await async_setup_component(hass, "otbr", {})
    websocket_client = await hass_ws_client(hass)
    await websocket_client.send_json_auto_id({"type": "otbr/create_network"})

    msg = await websocket_client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_loaded"


async def test_create_network_fails_1(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test create network."""
    with patch(
        "python_otbr_api.OTBR.set_enabled",
        side_effect=python_otbr_api.OTBRError,
    ):
        await websocket_client.send_json_auto_id({"type": "otbr/create_network"})
        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "set_enabled_failed"


async def test_create_network_fails_2(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test create network."""
    with patch(
        "python_otbr_api.OTBR.set_enabled",
    ), patch(
        "python_otbr_api.OTBR.create_active_dataset",
        side_effect=python_otbr_api.OTBRError,
    ):
        await websocket_client.send_json_auto_id({"type": "otbr/create_network"})
        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "create_active_dataset_failed"


async def test_create_network_fails_3(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test create network."""
    with patch(
        "python_otbr_api.OTBR.set_enabled",
        side_effect=[None, python_otbr_api.OTBRError],
    ), patch(
        "python_otbr_api.OTBR.create_active_dataset",
    ):
        await websocket_client.send_json_auto_id({"type": "otbr/create_network"})
        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "set_enabled_failed"


async def test_create_network_fails_4(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test create network."""
    with patch("python_otbr_api.OTBR.set_enabled"), patch(
        "python_otbr_api.OTBR.create_active_dataset"
    ), patch(
        "python_otbr_api.OTBR.get_active_dataset_tlvs",
        side_effect=python_otbr_api.OTBRError,
    ):
        await websocket_client.send_json_auto_id({"type": "otbr/create_network"})
        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "get_active_dataset_tlvs_failed"


async def test_create_network_fails_5(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test create network."""
    with patch("python_otbr_api.OTBR.set_enabled"), patch(
        "python_otbr_api.OTBR.create_active_dataset"
    ), patch("python_otbr_api.OTBR.get_active_dataset_tlvs", return_value=None):
        await websocket_client.send_json_auto_id({"type": "otbr/create_network"})
        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "get_active_dataset_tlvs_empty"


async def test_set_network(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test set network."""

    await thread.async_add_dataset(hass, "test", DATASET_CH15.hex())
    dataset_store = await thread.dataset_store.async_get_store(hass)
    dataset_id = list(dataset_store.datasets)[1]

    with patch(
        "python_otbr_api.OTBR.set_active_dataset_tlvs"
    ) as set_active_dataset_tlvs_mock, patch(
        "python_otbr_api.OTBR.set_enabled"
    ) as set_enabled_mock:
        await websocket_client.send_json_auto_id(
            {
                "type": "otbr/set_network",
                "dataset_id": dataset_id,
            }
        )

        msg = await websocket_client.receive_json()
        assert msg["success"]
        assert msg["result"] is None

    set_active_dataset_tlvs_mock.assert_called_once_with(DATASET_CH15)
    assert len(set_enabled_mock.mock_calls) == 2
    assert set_enabled_mock.mock_calls[0][1][0] is False
    assert set_enabled_mock.mock_calls[1][1][0] is True


async def test_set_network_no_entry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test set network."""
    await async_setup_component(hass, "otbr", {})
    websocket_client = await hass_ws_client(hass)
    await websocket_client.send_json_auto_id(
        {
            "type": "otbr/set_network",
            "dataset_id": "abc",
        }
    )

    msg = await websocket_client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_loaded"


async def test_set_network_channel_conflict(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test set network."""

    dataset_store = await thread.dataset_store.async_get_store(hass)
    dataset_id = list(dataset_store.datasets)[0]

    networksettings = Mock()
    networksettings.network_info.channel = 15

    with patch(
        "homeassistant.components.otbr.util.zha_api.async_get_radio_path",
        return_value="socket://core-silabs-multiprotocol:9999",
    ), patch(
        "homeassistant.components.otbr.util.zha_api.async_get_network_settings",
        return_value=networksettings,
    ):
        await websocket_client.send_json_auto_id(
            {
                "type": "otbr/set_network",
                "dataset_id": dataset_id,
            }
        )

        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "channel_conflict"


async def test_set_network_unknown_dataset(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test set network."""

    await websocket_client.send_json_auto_id(
        {
            "type": "otbr/set_network",
            "dataset_id": "abc",
        }
    )

    msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "unknown_dataset"


async def test_set_network_fails_1(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test set network."""
    await thread.async_add_dataset(hass, "test", DATASET_CH15.hex())
    dataset_store = await thread.dataset_store.async_get_store(hass)
    dataset_id = list(dataset_store.datasets)[1]

    with patch(
        "python_otbr_api.OTBR.set_enabled",
        side_effect=python_otbr_api.OTBRError,
    ):
        await websocket_client.send_json_auto_id(
            {
                "type": "otbr/set_network",
                "dataset_id": dataset_id,
            }
        )
        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "set_enabled_failed"


async def test_set_network_fails_2(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test set network."""
    await thread.async_add_dataset(hass, "test", DATASET_CH15.hex())
    dataset_store = await thread.dataset_store.async_get_store(hass)
    dataset_id = list(dataset_store.datasets)[1]

    with patch(
        "python_otbr_api.OTBR.set_enabled",
    ), patch(
        "python_otbr_api.OTBR.set_active_dataset_tlvs",
        side_effect=python_otbr_api.OTBRError,
    ):
        await websocket_client.send_json_auto_id(
            {
                "type": "otbr/set_network",
                "dataset_id": dataset_id,
            }
        )
        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "set_active_dataset_tlvs_failed"


async def test_set_network_fails_3(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test set network."""
    await thread.async_add_dataset(hass, "test", DATASET_CH15.hex())
    dataset_store = await thread.dataset_store.async_get_store(hass)
    dataset_id = list(dataset_store.datasets)[1]

    with patch(
        "python_otbr_api.OTBR.set_enabled",
        side_effect=[None, python_otbr_api.OTBRError],
    ), patch(
        "python_otbr_api.OTBR.set_active_dataset_tlvs",
    ):
        await websocket_client.send_json_auto_id(
            {
                "type": "otbr/set_network",
                "dataset_id": dataset_id,
            }
        )
        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "set_enabled_failed"


async def test_get_extended_address(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test get extended address."""

    with patch(
        "python_otbr_api.OTBR.get_extended_address",
        return_value=bytes.fromhex("4EF6C4F3FF750626"),
    ):
        await websocket_client.send_json_auto_id({"type": "otbr/get_extended_address"})
        msg = await websocket_client.receive_json()

    assert msg["success"]
    assert msg["result"] == {"extended_address": "4EF6C4F3FF750626".lower()}


async def test_get_extended_address_no_entry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test get extended address."""
    await async_setup_component(hass, "otbr", {})
    websocket_client = await hass_ws_client(hass)
    await websocket_client.send_json_auto_id({"type": "otbr/get_extended_address"})

    msg = await websocket_client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_loaded"


async def test_get_extended_address_fetch_fails(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    otbr_config_entry,
    websocket_client,
) -> None:
    """Test get extended address."""
    with patch(
        "python_otbr_api.OTBR.get_extended_address",
        side_effect=python_otbr_api.OTBRError,
    ):
        await websocket_client.send_json_auto_id({"type": "otbr/get_extended_address"})
        msg = await websocket_client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "get_extended_address_failed"
