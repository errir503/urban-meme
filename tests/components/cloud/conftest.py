"""Fixtures for cloud tests."""
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import DEFAULT, MagicMock, PropertyMock, patch

from hass_nabucasa import Cloud
from hass_nabucasa.auth import CognitoAuth
from hass_nabucasa.cloudhooks import Cloudhooks
from hass_nabucasa.const import DEFAULT_SERVERS, DEFAULT_VALUES, STATE_CONNECTED
from hass_nabucasa.google_report_state import GoogleReportState
from hass_nabucasa.iot import CloudIoT
from hass_nabucasa.remote import RemoteUI
from hass_nabucasa.voice import Voice
import jwt
import pytest

from homeassistant.components.cloud import CloudClient, const, prefs

from . import mock_cloud, mock_cloud_prefs


@pytest.fixture(name="cloud")
async def cloud_fixture() -> AsyncGenerator[MagicMock, None]:
    """Mock the cloud object.

    See the real hass_nabucasa.Cloud class for how to configure the mock.
    """
    with patch(
        "homeassistant.components.cloud.Cloud", autospec=True
    ) as mock_cloud_class:
        mock_cloud = mock_cloud_class.return_value

        # Attributes set in the constructor without parameters.
        # We spec the mocks with the real classes
        # and set constructor attributes or mock properties as needed.
        mock_cloud.google_report_state = MagicMock(spec=GoogleReportState)
        mock_cloud.cloudhooks = MagicMock(spec=Cloudhooks)
        mock_cloud.remote = MagicMock(
            spec=RemoteUI,
            certificate=None,
            certificate_status=None,
            instance_domain=None,
            is_connected=False,
        )
        mock_cloud.auth = MagicMock(spec=CognitoAuth)
        mock_cloud.iot = MagicMock(
            spec=CloudIoT, last_disconnect_reason=None, state=STATE_CONNECTED
        )
        mock_cloud.voice = MagicMock(spec=Voice)
        mock_cloud.started = None

        def set_up_mock_cloud(
            cloud_client: CloudClient, mode: str, **kwargs: Any
        ) -> DEFAULT:
            """Set up mock cloud with a mock constructor."""

            # Attributes set in the constructor with parameters.
            cloud_client.cloud = mock_cloud
            mock_cloud.client = cloud_client
            default_values = DEFAULT_VALUES[mode]
            servers = {
                f"{name}_server": server
                for name, server in DEFAULT_SERVERS[mode].items()
            }
            mock_cloud.configure_mock(**default_values, **servers, **kwargs)
            mock_cloud.mode = mode

            # Properties that we mock as attributes from the constructor.
            mock_cloud.websession = cloud_client.websession

            return DEFAULT

        mock_cloud_class.side_effect = set_up_mock_cloud

        # Attributes that we mock with default values.

        mock_cloud.id_token = jwt.encode(
            {
                "email": "hello@home-assistant.io",
                "custom:sub-exp": "2018-01-03",
                "cognito:username": "abcdefghjkl",
            },
            "test",
        )
        mock_cloud.access_token = "test_access_token"
        mock_cloud.refresh_token = "test_refresh_token"

        # Properties that we keep as properties.

        def mock_is_logged_in() -> bool:
            """Mock is logged in."""
            return mock_cloud.id_token is not None

        is_logged_in = PropertyMock(side_effect=mock_is_logged_in)
        type(mock_cloud).is_logged_in = is_logged_in

        def mock_claims() -> dict[str, Any]:
            """Mock claims."""
            return Cloud._decode_claims(mock_cloud.id_token)

        claims = PropertyMock(side_effect=mock_claims)
        type(mock_cloud).claims = claims

        # Properties that we mock as attributes.
        mock_cloud.subscription_expired = False

        # Methods that we mock with a custom side effect.

        async def mock_login(email: str, password: str) -> None:
            """Mock login.

            When called, it should call the on_start callback.
            """
            on_start_callback = mock_cloud.register_on_start.call_args[0][0]
            await on_start_callback()

        mock_cloud.login.side_effect = mock_login

        yield mock_cloud


@pytest.fixture(autouse=True)
def mock_tts_cache_dir_autouse(mock_tts_cache_dir):
    """Mock the TTS cache dir with empty dir."""
    return mock_tts_cache_dir


@pytest.fixture(autouse=True)
def mock_user_data():
    """Mock os module."""
    with patch("hass_nabucasa.Cloud._write_user_info") as writer:
        yield writer


@pytest.fixture
def mock_cloud_fixture(hass):
    """Fixture for cloud component."""
    hass.loop.run_until_complete(mock_cloud(hass))
    return mock_cloud_prefs(hass)


@pytest.fixture
async def cloud_prefs(hass):
    """Fixture for cloud preferences."""
    cloud_prefs = prefs.CloudPreferences(hass)
    await cloud_prefs.async_initialize()
    return cloud_prefs


@pytest.fixture
async def mock_cloud_setup(hass):
    """Set up the cloud."""
    await mock_cloud(hass)


@pytest.fixture
def mock_cloud_login(hass, mock_cloud_setup):
    """Mock cloud is logged in."""
    hass.data[const.DOMAIN].id_token = jwt.encode(
        {
            "email": "hello@home-assistant.io",
            "custom:sub-exp": "2300-01-03",
            "cognito:username": "abcdefghjkl",
        },
        "test",
    )
    with patch.object(hass.data[const.DOMAIN].auth, "async_check_token"):
        yield


@pytest.fixture(name="mock_auth")
def mock_auth_fixture():
    """Mock check token."""
    with patch("hass_nabucasa.auth.CognitoAuth.async_check_token"), patch(
        "hass_nabucasa.auth.CognitoAuth.async_renew_access_token"
    ):
        yield


@pytest.fixture
def mock_expired_cloud_login(hass, mock_cloud_setup):
    """Mock cloud is logged in."""
    hass.data[const.DOMAIN].id_token = jwt.encode(
        {
            "email": "hello@home-assistant.io",
            "custom:sub-exp": "2018-01-01",
            "cognito:username": "abcdefghjkl",
        },
        "test",
    )
