"""The tests for the REST sensor platform."""
import asyncio
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import httpx
import respx

from homeassistant import config as hass_config
from homeassistant.components.homeassistant import SERVICE_UPDATE_ENTITY
from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    DOMAIN,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    CONTENT_TYPE_JSON,
    DATA_MEGABYTES,
    SERVICE_RELOAD,
    STATE_UNKNOWN,
    TEMP_CELSIUS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import get_fixture_path


async def test_setup_missing_config(hass):
    """Test setup with configuration missing required entries."""
    assert await async_setup_component(hass, DOMAIN, {"sensor": {"platform": "rest"}})
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 0


async def test_setup_missing_schema(hass):
    """Test setup with resource missing schema."""
    assert await async_setup_component(
        hass,
        DOMAIN,
        {"sensor": {"platform": "rest", "resource": "localhost", "method": "GET"}},
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 0


@respx.mock
async def test_setup_failed_connect(hass, caplog):
    """Test setup when connection error occurs."""
    respx.get("http://localhost").mock(
        side_effect=httpx.RequestError("server offline", request=MagicMock())
    )
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 0
    assert "server offline" in caplog.text


@respx.mock
async def test_setup_timeout(hass):
    """Test setup when connection timeout occurs."""
    respx.get("http://localhost").mock(side_effect=asyncio.TimeoutError())
    assert await async_setup_component(
        hass,
        DOMAIN,
        {"sensor": {"platform": "rest", "resource": "localhost", "method": "GET"}},
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 0


@respx.mock
async def test_setup_minimum(hass):
    """Test setup with minimum configuration."""
    respx.get("http://localhost") % HTTPStatus.OK
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1


@respx.mock
async def test_manual_update(hass):
    """Test setup with minimum configuration."""
    await async_setup_component(hass, "homeassistant", {})
    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK, json={"data": "first"}
    )
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "sensor": {
                "name": "mysensor",
                "value_template": "{{ value_json.data }}",
                "platform": "rest",
                "resource_template": "{% set url = 'http://localhost' %}{{ url }}",
                "method": "GET",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1
    assert hass.states.get("sensor.mysensor").state == "first"

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK, json={"data": "second"}
    )
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {ATTR_ENTITY_ID: ["sensor.mysensor"]},
        blocking=True,
    )
    assert hass.states.get("sensor.mysensor").state == "second"


@respx.mock
async def test_setup_minimum_resource_template(hass):
    """Test setup with minimum configuration (resource_template)."""
    respx.get("http://localhost") % HTTPStatus.OK
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "sensor": {
                "platform": "rest",
                "resource_template": "{% set url = 'http://localhost' %}{{ url }}",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1


@respx.mock
async def test_setup_duplicate_resource_template(hass):
    """Test setup with duplicate resources."""
    respx.get("http://localhost") % HTTPStatus.OK
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "resource_template": "http://localhost",
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 0


@respx.mock
async def test_setup_get(hass):
    """Test setup with valid configuration."""
    respx.get("http://localhost").respond(status_code=HTTPStatus.OK, json={})
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "name": "foo",
                "unit_of_measurement": TEMP_CELSIUS,
                "verify_ssl": "true",
                "timeout": 30,
                "authentication": "basic",
                "username": "my username",
                "password": "my password",
                "headers": {"Accept": CONTENT_TYPE_JSON},
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            }
        },
    )
    await async_setup_component(hass, "homeassistant", {})

    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1

    assert hass.states.get("sensor.foo").state == ""
    await hass.services.async_call(
        "homeassistant",
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: "sensor.foo"},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.foo")
    assert state.state == ""
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == TEMP_CELSIUS
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.TEMPERATURE
    assert state.attributes[ATTR_STATE_CLASS] is SensorStateClass.MEASUREMENT


@respx.mock
async def test_setup_timestamp(hass, caplog):
    """Test setup with valid configuration."""
    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK, json={"key": "2021-11-11 11:39Z"}
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "device_class": SensorDeviceClass.TIMESTAMP,
                "state_class": SensorStateClass.MEASUREMENT,
            }
        },
    )
    await async_setup_component(hass, "homeassistant", {})

    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1

    state = hass.states.get("sensor.rest_sensor")
    assert state.state == "2021-11-11T11:39:00+00:00"
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.TIMESTAMP
    assert state.attributes[ATTR_STATE_CLASS] is SensorStateClass.MEASUREMENT
    assert "sensor.rest_sensor rendered invalid timestamp" not in caplog.text
    assert "sensor.rest_sensor rendered timestamp without timezone" not in caplog.text

    # Bad response: Not a timestamp
    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK, json={"key": "invalid time stamp"}
    )
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {ATTR_ENTITY_ID: ["sensor.rest_sensor"]},
        blocking=True,
    )
    state = hass.states.get("sensor.rest_sensor")
    assert state.state == "unknown"
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.TIMESTAMP
    assert "sensor.rest_sensor rendered invalid timestamp" in caplog.text

    # Bad response: No timezone
    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK, json={"key": "2021-10-11 11:39"}
    )
    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {ATTR_ENTITY_ID: ["sensor.rest_sensor"]},
        blocking=True,
    )
    state = hass.states.get("sensor.rest_sensor")
    assert state.state == "unknown"
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.TIMESTAMP
    assert "sensor.rest_sensor rendered timestamp without timezone" in caplog.text


@respx.mock
async def test_setup_get_templated_headers_params(hass):
    """Test setup with valid configuration."""
    respx.get("http://localhost").respond(status_code=200, json={})
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "name": "foo",
                "verify_ssl": "true",
                "timeout": 30,
                "headers": {
                    "Accept": CONTENT_TYPE_JSON,
                    "User-Agent": "Mozilla/{{ 3 + 2 }}.0",
                },
                "params": {
                    "start": 0,
                    "end": "{{ 3 + 2 }}",
                },
            }
        },
    )
    await async_setup_component(hass, "homeassistant", {})

    assert respx.calls.last.request.headers["Accept"] == CONTENT_TYPE_JSON
    assert respx.calls.last.request.headers["User-Agent"] == "Mozilla/5.0"
    assert respx.calls.last.request.url.query == b"start=0&end=5"


@respx.mock
async def test_setup_get_digest_auth(hass):
    """Test setup with valid configuration."""
    respx.get("http://localhost").respond(status_code=HTTPStatus.OK, json={})
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
                "authentication": "digest",
                "username": "my username",
                "password": "my password",
                "headers": {"Accept": CONTENT_TYPE_JSON},
            }
        },
    )

    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1


@respx.mock
async def test_setup_post(hass):
    """Test setup with valid configuration."""
    respx.post("http://localhost").respond(status_code=HTTPStatus.OK, json={})
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "POST",
                "value_template": "{{ value_json.key }}",
                "payload": '{ "device": "toaster"}',
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
                "authentication": "basic",
                "username": "my username",
                "password": "my password",
                "headers": {"Accept": CONTENT_TYPE_JSON},
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1


@respx.mock
async def test_setup_get_xml(hass):
    """Test setup with valid xml configuration."""
    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        headers={"content-type": "text/xml"},
        content="<dog>abc</dog>",
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.dog }}",
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1

    state = hass.states.get("sensor.foo")
    assert state.state == "abc"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == DATA_MEGABYTES


@respx.mock
async def test_setup_query_params(hass):
    """Test setup with query params."""
    respx.get("http://localhost", params={"search": "something"}) % HTTPStatus.OK
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "params": {"search": "something"},
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1


@respx.mock
async def test_update_with_json_attrs(hass):
    """Test attributes get extracted from a JSON result."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        json={"key": "some_json_value"},
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "json_attributes": ["key"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1

    state = hass.states.get("sensor.foo")
    assert state.state == "some_json_value"
    assert state.attributes["key"] == "some_json_value"


@respx.mock
async def test_update_with_no_template(hass):
    """Test update when there is no value template."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        json={"key": "some_json_value"},
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "json_attributes": ["key"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
                "headers": {"Accept": "text/xml"},
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1

    state = hass.states.get("sensor.foo")
    assert state.state == '{"key": "some_json_value"}'


@respx.mock
async def test_update_with_json_attrs_no_data(hass, caplog):
    """Test attributes when no JSON result fetched."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        headers={"content-type": CONTENT_TYPE_JSON},
        content="",
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "json_attributes": ["key"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
                "headers": {"Accept": "text/xml"},
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1

    state = hass.states.get("sensor.foo")
    assert state.state == STATE_UNKNOWN
    assert state.attributes == {"unit_of_measurement": "MB", "friendly_name": "foo"}
    assert "Empty reply" in caplog.text


@respx.mock
async def test_update_with_json_attrs_not_dict(hass, caplog):
    """Test attributes get extracted from a JSON result."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        json=["list", "of", "things"],
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "json_attributes": ["key"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
                "headers": {"Accept": "text/xml"},
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1

    state = hass.states.get("sensor.foo")
    assert state.state == ""
    assert state.attributes == {"unit_of_measurement": "MB", "friendly_name": "foo"}
    assert "not a dictionary or list" in caplog.text


@respx.mock
async def test_update_with_json_attrs_bad_JSON(hass, caplog):
    """Test attributes get extracted from a JSON result."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        headers={"content-type": CONTENT_TYPE_JSON},
        content="This is text rather than JSON data.",
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.key }}",
                "json_attributes": ["key"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
                "headers": {"Accept": "text/xml"},
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1

    state = hass.states.get("sensor.foo")
    assert state.state == STATE_UNKNOWN
    assert state.attributes == {"unit_of_measurement": "MB", "friendly_name": "foo"}
    assert "Erroneous JSON" in caplog.text


@respx.mock
async def test_update_with_json_attrs_with_json_attrs_path(hass):
    """Test attributes get extracted from a JSON result with a template for the attributes."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        json={
            "toplevel": {
                "master_value": "master",
                "second_level": {
                    "some_json_key": "some_json_value",
                    "some_json_key2": "some_json_value2",
                },
            },
        },
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.toplevel.master_value }}",
                "json_attributes_path": "$.toplevel.second_level",
                "json_attributes": ["some_json_key", "some_json_key2"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
                "headers": {"Accept": "text/xml"},
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1
    state = hass.states.get("sensor.foo")

    assert state.state == "master"
    assert state.attributes["some_json_key"] == "some_json_value"
    assert state.attributes["some_json_key2"] == "some_json_value2"


@respx.mock
async def test_update_with_xml_convert_json_attrs_with_json_attrs_path(hass):
    """Test attributes get extracted from a JSON result that was converted from XML with a template for the attributes."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        headers={"content-type": "text/xml"},
        content="<toplevel><master_value>master</master_value><second_level><some_json_key>some_json_value</some_json_key><some_json_key2>some_json_value2</some_json_key2></second_level></toplevel>",
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.toplevel.master_value }}",
                "json_attributes_path": "$.toplevel.second_level",
                "json_attributes": ["some_json_key", "some_json_key2"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1
    state = hass.states.get("sensor.foo")

    assert state.state == "master"
    assert state.attributes["some_json_key"] == "some_json_value"
    assert state.attributes["some_json_key2"] == "some_json_value2"


@respx.mock
async def test_update_with_xml_convert_json_attrs_with_jsonattr_template(hass):
    """Test attributes get extracted from a JSON result that was converted from XML."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        headers={"content-type": "text/xml"},
        content='<?xml version="1.0" encoding="utf-8"?><response><scan>0</scan><ver>12556</ver><count>48</count><ssid>alexander</ssid><bss><valid>0</valid><name>0</name><privacy>0</privacy><wlan>bogus</wlan><strength>0</strength></bss><led0>0</led0><led1>0</led1><led2>0</led2><led3>0</led3><led4>0</led4><led5>0</led5><led6>0</led6><led7>0</led7><btn0>up</btn0><btn1>up</btn1><btn2>up</btn2><btn3>up</btn3><pot0>0</pot0><usr0>0</usr0><temp0>0x0XF0x0XF</temp0><time0> 0</time0></response>',
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.response.bss.wlan }}",
                "json_attributes_path": "$.response",
                "json_attributes": ["led0", "led1", "temp0", "time0", "ver"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1
    state = hass.states.get("sensor.foo")

    assert state.state == "bogus"
    assert state.attributes["led0"] == "0"
    assert state.attributes["led1"] == "0"
    assert state.attributes["temp0"] == "0x0XF0x0XF"
    assert state.attributes["time0"] == "0"
    assert state.attributes["ver"] == "12556"


@respx.mock
async def test_update_with_application_xml_convert_json_attrs_with_jsonattr_template(
    hass,
):
    """Test attributes get extracted from a JSON result that was converted from XML with application/xml mime type."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        headers={"content-type": "application/xml"},
        content="<main><dog>1</dog><cat>3</cat></main>",
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.main.dog }}",
                "json_attributes_path": "$.main",
                "json_attributes": ["dog", "cat"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1
    state = hass.states.get("sensor.foo")

    assert state.state == "1"
    assert state.attributes["dog"] == "1"
    assert state.attributes["cat"] == "3"


@respx.mock
async def test_update_with_xml_convert_bad_xml(hass, caplog):
    """Test attributes get extracted from a XML result with bad xml."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        headers={"content-type": "text/xml"},
        content="",
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.toplevel.master_value }}",
                "json_attributes": ["key"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1
    state = hass.states.get("sensor.foo")

    assert state.state == STATE_UNKNOWN
    assert "Erroneous XML" in caplog.text
    assert "Empty reply" in caplog.text


@respx.mock
async def test_update_with_failed_get(hass, caplog):
    """Test attributes get extracted from a XML result with bad xml."""

    respx.get("http://localhost").respond(
        status_code=HTTPStatus.OK,
        headers={"content-type": "text/xml"},
        content="",
    )
    assert await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "resource": "http://localhost",
                "method": "GET",
                "value_template": "{{ value_json.toplevel.master_value }}",
                "json_attributes": ["key"],
                "name": "foo",
                "unit_of_measurement": DATA_MEGABYTES,
                "verify_ssl": "true",
                "timeout": 30,
            }
        },
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 1
    state = hass.states.get("sensor.foo")

    assert state.state == STATE_UNKNOWN
    assert "Erroneous XML" in caplog.text
    assert "Empty reply" in caplog.text


@respx.mock
async def test_reload(hass):
    """Verify we can reload reset sensors."""

    respx.get("http://localhost") % HTTPStatus.OK

    await async_setup_component(
        hass,
        "sensor",
        {
            "sensor": {
                "platform": "rest",
                "method": "GET",
                "name": "mockrest",
                "resource": "http://localhost",
            }
        },
    )
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()

    assert len(hass.states.async_all("sensor")) == 1

    assert hass.states.get("sensor.mockrest")

    yaml_path = get_fixture_path("configuration.yaml", "rest")
    with patch.object(hass_config, "YAML_CONFIG_FILE", yaml_path):
        await hass.services.async_call(
            "rest",
            SERVICE_RELOAD,
            {},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert hass.states.get("sensor.mockreset") is None
    assert hass.states.get("sensor.rollout")


@respx.mock
async def test_entity_config(hass: HomeAssistant) -> None:
    """Test entity configuration."""

    config = {
        DOMAIN: {
            # REST configuration
            "platform": "rest",
            "method": "GET",
            "resource": "http://localhost",
            # Entity configuration
            "icon": "{{'mdi:one_two_three'}}",
            "picture": "{{'blabla.png'}}",
            "device_class": "temperature",
            "name": "{{'REST' + ' ' + 'Sensor'}}",
            "state_class": "measurement",
            "unique_id": "very_unique",
            "unit_of_measurement": "beardsecond",
        },
    }

    respx.get("http://localhost") % HTTPStatus.OK
    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    assert entity_registry.async_get("sensor.rest_sensor").unique_id == "very_unique"

    state = hass.states.get("sensor.rest_sensor")
    assert state.state == ""
    assert state.attributes == {
        "device_class": "temperature",
        "entity_picture": "blabla.png",
        "friendly_name": "REST Sensor",
        "icon": "mdi:one_two_three",
        "state_class": "measurement",
        "unit_of_measurement": "beardsecond",
    }
