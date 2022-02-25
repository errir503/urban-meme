"""Fixtures for DLNA DMS tests."""
from __future__ import annotations

from collections.abc import AsyncGenerator, Iterable
from typing import Final
from unittest.mock import Mock, create_autospec, patch, seal

from async_upnp_client import UpnpDevice, UpnpService
from async_upnp_client.utils import absolute_url
import pytest

from homeassistant.components.dlna_dms.const import DOMAIN
from homeassistant.components.dlna_dms.dms import DlnaDmsData, get_domain_data
from homeassistant.const import CONF_DEVICE_ID, CONF_URL
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

MOCK_DEVICE_HOST: Final = "192.88.99.21"
MOCK_DEVICE_BASE_URL: Final = f"http://{MOCK_DEVICE_HOST}"
MOCK_DEVICE_LOCATION: Final = MOCK_DEVICE_BASE_URL + "/dms_description.xml"
MOCK_DEVICE_NAME: Final = "Test Server Device"
MOCK_DEVICE_TYPE: Final = "urn:schemas-upnp-org:device:MediaServer:1"
MOCK_DEVICE_UDN: Final = "uuid:7bf34520-f034-4fa2-8d2d-2f709d4221ef"
MOCK_DEVICE_USN: Final = f"{MOCK_DEVICE_UDN}::{MOCK_DEVICE_TYPE}"
MOCK_SOURCE_ID: Final = "test_server_device"

LOCAL_IP: Final = "192.88.99.1"
EVENT_CALLBACK_URL: Final = "http://192.88.99.1/notify"

NEW_DEVICE_LOCATION: Final = "http://192.88.99.7" + "/dmr_description.xml"


@pytest.fixture
def upnp_factory_mock() -> Iterable[Mock]:
    """Mock the UpnpFactory class to construct DMS-style UPnP devices."""
    with patch(
        "homeassistant.components.dlna_dms.dms.UpnpFactory",
        autospec=True,
        spec_set=True,
    ) as upnp_factory:
        upnp_device = create_autospec(UpnpDevice, instance=True)
        upnp_device.name = MOCK_DEVICE_NAME
        upnp_device.udn = MOCK_DEVICE_UDN
        upnp_device.device_url = MOCK_DEVICE_LOCATION
        upnp_device.device_type = MOCK_DEVICE_TYPE
        upnp_device.available = True
        upnp_device.parent_device = None
        upnp_device.root_device = upnp_device
        upnp_device.all_devices = [upnp_device]
        upnp_device.services = {
            "urn:schemas-upnp-org:service:ContentDirectory:1": create_autospec(
                UpnpService,
                instance=True,
                service_type="urn:schemas-upnp-org:service:ContentDirectory:1",
                service_id="urn:upnp-org:serviceId:ContentDirectory",
            ),
            "urn:schemas-upnp-org:service:ConnectionManager:1": create_autospec(
                UpnpService,
                instance=True,
                service_type="urn:schemas-upnp-org:service:ConnectionManager:1",
                service_id="urn:upnp-org:serviceId:ConnectionManager",
            ),
        }
        seal(upnp_device)
        upnp_factory_instance = upnp_factory.return_value
        upnp_factory_instance.async_create_device.return_value = upnp_device

        yield upnp_factory_instance


@pytest.fixture
async def domain_data_mock(
    hass: HomeAssistant, aioclient_mock, upnp_factory_mock
) -> AsyncGenerator[DlnaDmsData, None]:
    """Mock some global data used by this component.

    This includes network clients and library object factories. Mocking it
    prevents network use.

    Yields the actual domain data, for ease of access
    """
    with patch(
        "homeassistant.components.dlna_dms.dms.AiohttpSessionRequester", autospec=True
    ):
        yield get_domain_data(hass)


@pytest.fixture
def config_entry_mock() -> MockConfigEntry:
    """Mock a config entry for this platform."""
    mock_entry = MockConfigEntry(
        unique_id=MOCK_DEVICE_USN,
        domain=DOMAIN,
        data={
            CONF_URL: MOCK_DEVICE_LOCATION,
            CONF_DEVICE_ID: MOCK_DEVICE_USN,
        },
        title=MOCK_DEVICE_NAME,
    )
    return mock_entry


@pytest.fixture
def dms_device_mock(upnp_factory_mock: Mock) -> Iterable[Mock]:
    """Mock the async_upnp_client DMS device, initially connected."""
    with patch(
        "homeassistant.components.dlna_dms.dms.DmsDevice", autospec=True
    ) as constructor:
        device = constructor.return_value
        device.on_event = None
        device.profile_device = upnp_factory_mock.async_create_device.return_value
        device.icon = MOCK_DEVICE_BASE_URL + "/icon.jpg"
        device.udn = "device_udn"
        device.manufacturer = "device_manufacturer"
        device.model_name = "device_model_name"
        device.name = "device_name"
        device.get_absolute_url.side_effect = lambda url: absolute_url(
            MOCK_DEVICE_BASE_URL, url
        )

        yield device


@pytest.fixture(autouse=True)
def ssdp_scanner_mock() -> Iterable[Mock]:
    """Mock the SSDP module."""
    with patch("homeassistant.components.ssdp.Scanner", autospec=True) as mock_scanner:
        reg_callback = mock_scanner.return_value.async_register_callback
        reg_callback.return_value = Mock(return_value=None)
        yield mock_scanner.return_value
