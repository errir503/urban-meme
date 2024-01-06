"""The tests for the rest command platform."""
import asyncio
import base64
from http import HTTPStatus
from unittest.mock import patch

import aiohttp
import pytest

import homeassistant.components.rest_command as rc
from homeassistant.const import (
    CONTENT_TYPE_JSON,
    CONTENT_TYPE_TEXT_PLAIN,
    SERVICE_RELOAD,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import setup_component

from tests.common import assert_setup_component, get_test_home_assistant


class TestRestCommandSetup:
    """Test the rest command component."""

    def setup_method(self):
        """Set up things to be run when tests are started."""
        self.hass = get_test_home_assistant()

        self.config = {rc.DOMAIN: {"test_get": {"url": "http://example.com/"}}}

    def teardown_method(self):
        """Stop everything that was started."""
        self.hass.stop()

    def test_setup_component(self):
        """Test setup component."""
        with assert_setup_component(1):
            setup_component(self.hass, rc.DOMAIN, self.config)

    def test_setup_component_timeout(self):
        """Test setup component timeout."""
        self.config[rc.DOMAIN]["test_get"]["timeout"] = 10

        with assert_setup_component(1):
            setup_component(self.hass, rc.DOMAIN, self.config)

    def test_setup_component_test_service(self):
        """Test setup component and check if service exits."""
        with assert_setup_component(1):
            setup_component(self.hass, rc.DOMAIN, self.config)

        assert self.hass.services.has_service(rc.DOMAIN, "test_get")

    def test_reload(self):
        """Verify we can reload rest_command integration."""

        with assert_setup_component(1):
            setup_component(self.hass, rc.DOMAIN, self.config)

        assert self.hass.services.has_service(rc.DOMAIN, "test_get")
        assert not self.hass.services.has_service(rc.DOMAIN, "new_test")

        new_config = {
            rc.DOMAIN: {
                "new_test": {"url": "https://example.org", "method": "get"},
            }
        }
        with patch(
            "homeassistant.config.load_yaml_config_file",
            autospec=True,
            return_value=new_config,
        ):
            self.hass.services.call(rc.DOMAIN, SERVICE_RELOAD, blocking=True)

        assert self.hass.services.has_service(rc.DOMAIN, "new_test")
        assert not self.hass.services.has_service(rc.DOMAIN, "get_test")


class TestRestCommandComponent:
    """Test the rest command component."""

    def setup_method(self):
        """Set up things to be run when tests are started."""
        self.url = "https://example.com/"
        self.config = {
            rc.DOMAIN: {
                "get_test": {"url": self.url, "method": "get"},
                "patch_test": {"url": self.url, "method": "patch"},
                "post_test": {"url": self.url, "method": "post"},
                "put_test": {"url": self.url, "method": "put"},
                "delete_test": {"url": self.url, "method": "delete"},
            }
        }

        self.hass = get_test_home_assistant()

    def teardown_method(self):
        """Stop everything that was started."""
        self.hass.stop()

    def test_setup_tests(self):
        """Set up test config and test it."""
        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        assert self.hass.services.has_service(rc.DOMAIN, "get_test")
        assert self.hass.services.has_service(rc.DOMAIN, "post_test")
        assert self.hass.services.has_service(rc.DOMAIN, "put_test")
        assert self.hass.services.has_service(rc.DOMAIN, "delete_test")

    def test_rest_command_timeout(self, aioclient_mock):
        """Call a rest command with timeout."""
        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.get(self.url, exc=asyncio.TimeoutError())

        with pytest.raises(
            HomeAssistantError,
            match=r"^Timeout when calling resource 'https://example.com/'$",
        ):
            self.hass.services.call(rc.DOMAIN, "get_test", {}, blocking=True)

        assert len(aioclient_mock.mock_calls) == 1

    def test_rest_command_aiohttp_error(self, aioclient_mock):
        """Call a rest command with aiohttp exception."""
        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.get(self.url, exc=aiohttp.ClientError())

        with pytest.raises(
            HomeAssistantError,
            match=r"^Client error occurred when calling resource 'https://example.com/'$",
        ):
            self.hass.services.call(rc.DOMAIN, "get_test", {}, blocking=True)

        assert len(aioclient_mock.mock_calls) == 1

    def test_rest_command_http_error(self, aioclient_mock):
        """Call a rest command with status code 400."""
        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.get(self.url, status=HTTPStatus.BAD_REQUEST)

        self.hass.services.call(rc.DOMAIN, "get_test", {})
        self.hass.block_till_done()

        assert len(aioclient_mock.mock_calls) == 1

    def test_rest_command_auth(self, aioclient_mock):
        """Call a rest command with auth credential."""
        data = {"username": "test", "password": "123456"}
        self.config[rc.DOMAIN]["get_test"].update(data)

        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.get(self.url, content=b"success")

        self.hass.services.call(rc.DOMAIN, "get_test", {})
        self.hass.block_till_done()

        assert len(aioclient_mock.mock_calls) == 1

    def test_rest_command_form_data(self, aioclient_mock):
        """Call a rest command with post form data."""
        data = {"payload": "test"}
        self.config[rc.DOMAIN]["post_test"].update(data)

        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.post(self.url, content=b"success")

        self.hass.services.call(rc.DOMAIN, "post_test", {})
        self.hass.block_till_done()

        assert len(aioclient_mock.mock_calls) == 1
        assert aioclient_mock.mock_calls[0][2] == b"test"

    def test_rest_command_get(self, aioclient_mock):
        """Call a rest command with get."""
        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.get(self.url, content=b"success")

        self.hass.services.call(rc.DOMAIN, "get_test", {})
        self.hass.block_till_done()

        assert len(aioclient_mock.mock_calls) == 1

    def test_rest_command_delete(self, aioclient_mock):
        """Call a rest command with delete."""
        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.delete(self.url, content=b"success")

        self.hass.services.call(rc.DOMAIN, "delete_test", {})
        self.hass.block_till_done()

        assert len(aioclient_mock.mock_calls) == 1

    def test_rest_command_patch(self, aioclient_mock):
        """Call a rest command with patch."""
        data = {"payload": "data"}
        self.config[rc.DOMAIN]["patch_test"].update(data)

        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.patch(self.url, content=b"success")

        self.hass.services.call(rc.DOMAIN, "patch_test", {})
        self.hass.block_till_done()

        assert len(aioclient_mock.mock_calls) == 1
        assert aioclient_mock.mock_calls[0][2] == b"data"

    def test_rest_command_post(self, aioclient_mock):
        """Call a rest command with post."""
        data = {"payload": "data"}
        self.config[rc.DOMAIN]["post_test"].update(data)

        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.post(self.url, content=b"success")

        self.hass.services.call(rc.DOMAIN, "post_test", {})
        self.hass.block_till_done()

        assert len(aioclient_mock.mock_calls) == 1
        assert aioclient_mock.mock_calls[0][2] == b"data"

    def test_rest_command_put(self, aioclient_mock):
        """Call a rest command with put."""
        data = {"payload": "data"}
        self.config[rc.DOMAIN]["put_test"].update(data)

        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.put(self.url, content=b"success")

        self.hass.services.call(rc.DOMAIN, "put_test", {})
        self.hass.block_till_done()

        assert len(aioclient_mock.mock_calls) == 1
        assert aioclient_mock.mock_calls[0][2] == b"data"

    def test_rest_command_headers(self, aioclient_mock):
        """Call a rest command with custom headers and content types."""
        header_config_variations = {
            rc.DOMAIN: {
                "no_headers_test": {},
                "content_type_test": {"content_type": CONTENT_TYPE_TEXT_PLAIN},
                "headers_test": {
                    "headers": {
                        "Accept": CONTENT_TYPE_JSON,
                        "User-Agent": "Mozilla/5.0",
                    }
                },
                "headers_and_content_type_test": {
                    "headers": {"Accept": CONTENT_TYPE_JSON},
                    "content_type": CONTENT_TYPE_TEXT_PLAIN,
                },
                "headers_and_content_type_override_test": {
                    "headers": {
                        "Accept": CONTENT_TYPE_JSON,
                        aiohttp.hdrs.CONTENT_TYPE: "application/pdf",
                    },
                    "content_type": CONTENT_TYPE_TEXT_PLAIN,
                },
                "headers_template_test": {
                    "headers": {
                        "Accept": CONTENT_TYPE_JSON,
                        "User-Agent": "Mozilla/{{ 3 + 2 }}.0",
                    }
                },
                "headers_and_content_type_override_template_test": {
                    "headers": {
                        "Accept": "application/{{ 1 + 1 }}json",
                        aiohttp.hdrs.CONTENT_TYPE: "application/pdf",
                    },
                    "content_type": "text/json",
                },
            }
        }

        # add common parameters
        for variation in header_config_variations[rc.DOMAIN].values():
            variation.update(
                {"url": self.url, "method": "post", "payload": "test data"}
            )

        with assert_setup_component(7):
            setup_component(self.hass, rc.DOMAIN, header_config_variations)

        # provide post request data
        aioclient_mock.post(self.url, content=b"success")

        for test_service in [
            "no_headers_test",
            "content_type_test",
            "headers_test",
            "headers_and_content_type_test",
            "headers_and_content_type_override_test",
            "headers_template_test",
            "headers_and_content_type_override_template_test",
        ]:
            self.hass.services.call(rc.DOMAIN, test_service, {})

        self.hass.block_till_done()
        assert len(aioclient_mock.mock_calls) == 7

        # no_headers_test
        assert aioclient_mock.mock_calls[0][3] is None

        # content_type_test
        assert len(aioclient_mock.mock_calls[1][3]) == 1
        assert (
            aioclient_mock.mock_calls[1][3].get(aiohttp.hdrs.CONTENT_TYPE)
            == CONTENT_TYPE_TEXT_PLAIN
        )

        # headers_test
        assert len(aioclient_mock.mock_calls[2][3]) == 2
        assert aioclient_mock.mock_calls[2][3].get("Accept") == CONTENT_TYPE_JSON
        assert aioclient_mock.mock_calls[2][3].get("User-Agent") == "Mozilla/5.0"

        # headers_and_content_type_test
        assert len(aioclient_mock.mock_calls[3][3]) == 2
        assert (
            aioclient_mock.mock_calls[3][3].get(aiohttp.hdrs.CONTENT_TYPE)
            == CONTENT_TYPE_TEXT_PLAIN
        )
        assert aioclient_mock.mock_calls[3][3].get("Accept") == CONTENT_TYPE_JSON

        # headers_and_content_type_override_test
        assert len(aioclient_mock.mock_calls[4][3]) == 2
        assert (
            aioclient_mock.mock_calls[4][3].get(aiohttp.hdrs.CONTENT_TYPE)
            == CONTENT_TYPE_TEXT_PLAIN
        )
        assert aioclient_mock.mock_calls[4][3].get("Accept") == CONTENT_TYPE_JSON

        # headers_template_test
        assert len(aioclient_mock.mock_calls[5][3]) == 2
        assert aioclient_mock.mock_calls[5][3].get("Accept") == CONTENT_TYPE_JSON
        assert aioclient_mock.mock_calls[5][3].get("User-Agent") == "Mozilla/5.0"

        # headers_and_content_type_override_template_test
        assert len(aioclient_mock.mock_calls[6][3]) == 2
        assert (
            aioclient_mock.mock_calls[6][3].get(aiohttp.hdrs.CONTENT_TYPE)
            == "text/json"
        )
        assert aioclient_mock.mock_calls[6][3].get("Accept") == "application/2json"

    def test_rest_command_get_response_plaintext(self, aioclient_mock):
        """Get rest_command response, text."""
        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.get(
            self.url, content=b"success", headers={"content-type": "text/plain"}
        )

        response = self.hass.services.call(
            rc.DOMAIN, "get_test", {}, blocking=True, return_response=True
        )
        self.hass.block_till_done()

        assert len(aioclient_mock.mock_calls) == 1
        assert response["content"] == "success"
        assert response["status"] == 200

    def test_rest_command_get_response_json(self, aioclient_mock):
        """Get rest_command response, json."""
        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.get(
            self.url,
            json={"status": "success", "number": 42},
            headers={"content-type": "application/json"},
        )

        response = self.hass.services.call(
            rc.DOMAIN, "get_test", {}, blocking=True, return_response=True
        )
        self.hass.block_till_done()

        assert len(aioclient_mock.mock_calls) == 1
        assert response["content"]["status"] == "success"
        assert response["content"]["number"] == 42
        assert response["status"] == 200

    def test_rest_command_get_response_malformed_json(self, aioclient_mock):
        """Get rest_command response, malformed json."""
        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        aioclient_mock.get(
            self.url,
            content='{"status": "failure", 42',
            headers={"content-type": "application/json"},
        )

        # No problem without 'return_response'
        response = self.hass.services.call(rc.DOMAIN, "get_test", {}, blocking=True)
        self.hass.block_till_done()
        assert not response

        # Throws error when requesting response
        with pytest.raises(
            HomeAssistantError,
            match=r"^Response of 'https://example.com/' could not be decoded as JSON$",
        ):
            response = self.hass.services.call(
                rc.DOMAIN, "get_test", {}, blocking=True, return_response=True
            )
            self.hass.block_till_done()

    def test_rest_command_get_response_none(self, aioclient_mock):
        """Get rest_command response, other."""
        with assert_setup_component(5):
            setup_component(self.hass, rc.DOMAIN, self.config)

        png = base64.decodebytes(
            b"iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAAFiUAABYlAUlSJPAAAAAPSURBVBhXY/h/ku////8AECAE1JZPvDAAAAAASUVORK5CYII="
        )

        aioclient_mock.get(
            self.url,
            content=png,
            headers={"content-type": "text/plain"},
        )

        # No problem without 'return_response'
        response = self.hass.services.call(rc.DOMAIN, "get_test", {}, blocking=True)
        self.hass.block_till_done()
        assert not response

        # Throws Decode error when requesting response
        with pytest.raises(
            HomeAssistantError,
            match=r"^Response of 'https://example.com/' could not be decoded as text$",
        ):
            response = self.hass.services.call(
                rc.DOMAIN, "get_test", {}, blocking=True, return_response=True
            )
            self.hass.block_till_done()

        assert not response
