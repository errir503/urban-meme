"""Websocket API for OTBR."""
from typing import TYPE_CHECKING

import python_otbr_api

from homeassistant.components import websocket_api
from homeassistant.components.thread import async_add_dataset
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import DEFAULT_CHANNEL, DOMAIN

if TYPE_CHECKING:
    from . import OTBRData


@callback
def async_setup(hass: HomeAssistant) -> None:
    """Set up the OTBR Websocket API."""
    websocket_api.async_register_command(hass, websocket_info)
    websocket_api.async_register_command(hass, websocket_create_network)
    websocket_api.async_register_command(hass, websocket_get_extended_address)


@websocket_api.websocket_command(
    {
        "type": "otbr/info",
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_info(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Get OTBR info."""
    if DOMAIN not in hass.data:
        connection.send_error(msg["id"], "not_loaded", "No OTBR API loaded")
        return

    data: OTBRData = hass.data[DOMAIN]

    try:
        dataset = await data.get_active_dataset_tlvs()
    except HomeAssistantError as exc:
        connection.send_error(msg["id"], "get_dataset_failed", str(exc))
        return

    connection.send_result(
        msg["id"],
        {
            "url": data.url,
            "active_dataset_tlvs": dataset.hex() if dataset else None,
        },
    )


@websocket_api.websocket_command(
    {
        "type": "otbr/create_network",
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_create_network(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Create a new Thread network."""
    if DOMAIN not in hass.data:
        connection.send_error(msg["id"], "not_loaded", "No OTBR API loaded")
        return

    # We currently have no way to know which channel zha is using, assume it's
    # the default
    zha_channel = DEFAULT_CHANNEL

    data: OTBRData = hass.data[DOMAIN]

    try:
        await data.set_enabled(False)
    except HomeAssistantError as exc:
        connection.send_error(msg["id"], "set_enabled_failed", str(exc))
        return

    try:
        await data.create_active_dataset(
            python_otbr_api.OperationalDataSet(
                channel=zha_channel, network_name="home-assistant"
            )
        )
    except HomeAssistantError as exc:
        connection.send_error(msg["id"], "create_active_dataset_failed", str(exc))
        return

    try:
        await data.set_enabled(True)
    except HomeAssistantError as exc:
        connection.send_error(msg["id"], "set_enabled_failed", str(exc))
        return

    try:
        dataset_tlvs = await data.get_active_dataset_tlvs()
    except HomeAssistantError as exc:
        connection.send_error(msg["id"], "get_active_dataset_tlvs_failed", str(exc))
        return
    if not dataset_tlvs:
        connection.send_error(msg["id"], "get_active_dataset_tlvs_empty", "")
        return

    await async_add_dataset(hass, data.dataset_source, dataset_tlvs.hex())

    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        "type": "otbr/get_extended_address",
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_get_extended_address(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Get extended address (EUI-64)."""
    if DOMAIN not in hass.data:
        connection.send_error(msg["id"], "not_loaded", "No OTBR API loaded")
        return

    data: OTBRData = hass.data[DOMAIN]

    try:
        extended_address = await data.get_extended_address()
    except HomeAssistantError as exc:
        connection.send_error(msg["id"], "get_extended_address_failed", str(exc))
        return

    connection.send_result(msg["id"], {"extended_address": extended_address.hex()})
