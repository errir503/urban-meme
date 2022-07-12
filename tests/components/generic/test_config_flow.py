"""Test The generic (IP Camera) config flow."""

import errno
import os.path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from homeassistant import config_entries, data_entry_flow
from homeassistant.components.camera import async_get_image
from homeassistant.components.generic.config_flow import slug
from homeassistant.components.generic.const import (
    CONF_CONTENT_TYPE,
    CONF_FRAMERATE,
    CONF_LIMIT_REFETCH_TO_URL_CHANGE,
    CONF_STILL_IMAGE_URL,
    CONF_STREAM_SOURCE,
    DOMAIN,
)
from homeassistant.components.stream import (
    CONF_RTSP_TRANSPORT,
    CONF_USE_WALLCLOCK_AS_TIMESTAMPS,
)
from homeassistant.components.stream.worker import StreamWorkerError
from homeassistant.const import (
    CONF_AUTHENTICATION,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    HTTP_BASIC_AUTHENTICATION,
)
from homeassistant.helpers import entity_registry

from tests.common import MockConfigEntry

TESTDATA = {
    CONF_STILL_IMAGE_URL: "http://127.0.0.1/testurl/1",
    CONF_STREAM_SOURCE: "http://127.0.0.1/testurl/2",
    CONF_AUTHENTICATION: HTTP_BASIC_AUTHENTICATION,
    CONF_USERNAME: "fred_flintstone",
    CONF_PASSWORD: "bambam",
    CONF_FRAMERATE: 5,
    CONF_VERIFY_SSL: False,
}

TESTDATA_OPTIONS = {
    CONF_LIMIT_REFETCH_TO_URL_CHANGE: False,
    **TESTDATA,
}

TESTDATA_YAML = {
    CONF_NAME: "Yaml Defined Name",
    **TESTDATA,
}


@respx.mock
async def test_form(hass, fakeimg_png, user_flow, mock_create_stream):
    """Test the form with a normal set of settings."""

    with mock_create_stream as mock_setup, patch(
        "homeassistant.components.generic.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "127_0_0_1"
    assert result2["options"] == {
        CONF_STILL_IMAGE_URL: "http://127.0.0.1/testurl/1",
        CONF_STREAM_SOURCE: "http://127.0.0.1/testurl/2",
        CONF_AUTHENTICATION: HTTP_BASIC_AUTHENTICATION,
        CONF_USERNAME: "fred_flintstone",
        CONF_PASSWORD: "bambam",
        CONF_LIMIT_REFETCH_TO_URL_CHANGE: False,
        CONF_CONTENT_TYPE: "image/png",
        CONF_FRAMERATE: 5,
        CONF_VERIFY_SSL: False,
    }

    await hass.async_block_till_done()
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


@respx.mock
async def test_form_only_stillimage(hass, fakeimg_png, user_flow):
    """Test we complete ok if the user wants still images only."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    data = TESTDATA.copy()
    data.pop(CONF_STREAM_SOURCE)
    with patch("homeassistant.components.generic.async_setup_entry", return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            data,
        )
        await hass.async_block_till_done()
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "127_0_0_1"
    assert result2["options"] == {
        CONF_STILL_IMAGE_URL: "http://127.0.0.1/testurl/1",
        CONF_AUTHENTICATION: HTTP_BASIC_AUTHENTICATION,
        CONF_USERNAME: "fred_flintstone",
        CONF_PASSWORD: "bambam",
        CONF_LIMIT_REFETCH_TO_URL_CHANGE: False,
        CONF_CONTENT_TYPE: "image/png",
        CONF_FRAMERATE: 5,
        CONF_VERIFY_SSL: False,
    }

    assert respx.calls.call_count == 1


@respx.mock
async def test_form_only_stillimage_gif(hass, fakeimg_gif, user_flow):
    """Test we complete ok if the user wants a gif."""
    data = TESTDATA.copy()
    data.pop(CONF_STREAM_SOURCE)
    with patch("homeassistant.components.generic.async_setup_entry", return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            data,
        )
        await hass.async_block_till_done()
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["options"][CONF_CONTENT_TYPE] == "image/gif"


@respx.mock
async def test_form_only_svg_whitespace(hass, fakeimgbytes_svg, user_flow):
    """Test we complete ok if svg starts with whitespace, issue #68889."""
    fakeimgbytes_wspace_svg = bytes("  \n ", encoding="utf-8") + fakeimgbytes_svg
    respx.get("http://127.0.0.1/testurl/1").respond(stream=fakeimgbytes_wspace_svg)
    data = TESTDATA.copy()
    data.pop(CONF_STREAM_SOURCE)
    with patch("homeassistant.components.generic.async_setup_entry", return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            data,
        )
        await hass.async_block_till_done()
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


@respx.mock
@pytest.mark.parametrize(
    "image_file",
    [
        ("sample1_animate.png"),
        ("sample2_jpeg_odd_header.jpg"),
        ("sample3_jpeg_odd_header.jpg"),
        ("sample4_K5-60mileAnim-320x240.gif"),
        ("sample5_webp.webp"),
    ],
)
async def test_form_only_still_sample(hass, user_flow, image_file):
    """Test various sample images #69037."""
    image_path = os.path.join(os.path.dirname(__file__), image_file)
    with open(image_path, "rb") as image:
        respx.get("http://127.0.0.1/testurl/1").respond(stream=image.read())
    data = TESTDATA.copy()
    data.pop(CONF_STREAM_SOURCE)
    with patch("homeassistant.components.generic.async_setup_entry", return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            data,
        )
        await hass.async_block_till_done()
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


@respx.mock
@pytest.mark.parametrize(
    ("template", "url", "expected_result", "expected_errors"),
    [
        # Test we can handle templates in strange parts of the url, #70961.
        (
            "http://localhost:812{{3}}/static/icons/favicon-apple-180x180.png",
            "http://localhost:8123/static/icons/favicon-apple-180x180.png",
            data_entry_flow.FlowResultType.CREATE_ENTRY,
            None,
        ),
        (
            "{% if 1 %}https://bla{% else %}https://yo{% endif %}",
            "https://bla/",
            data_entry_flow.FlowResultType.CREATE_ENTRY,
            None,
        ),
        (
            "http://{{example.org",
            "http://example.org",
            data_entry_flow.FlowResultType.FORM,
            {"still_image_url": "template_error"},
        ),
        (
            "invalid1://invalid:4\\1",
            "invalid1://invalid:4%5c1",
            data_entry_flow.FlowResultType.FORM,
            {"still_image_url": "malformed_url"},
        ),
        (
            "relative/urls/are/not/allowed.jpg",
            "relative/urls/are/not/allowed.jpg",
            data_entry_flow.FlowResultType.FORM,
            {"still_image_url": "relative_url"},
        ),
    ],
)
async def test_still_template(
    hass, user_flow, fakeimgbytes_png, template, url, expected_result, expected_errors
) -> None:
    """Test we can handle various templates."""
    respx.get(url).respond(stream=fakeimgbytes_png)
    data = TESTDATA.copy()
    data.pop(CONF_STREAM_SOURCE)
    data[CONF_STILL_IMAGE_URL] = template
    with patch("homeassistant.components.generic.async_setup_entry", return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            data,
        )
        await hass.async_block_till_done()
    assert result2["type"] == expected_result
    assert result2.get("errors") == expected_errors


@respx.mock
async def test_form_rtsp_mode(hass, fakeimg_png, user_flow, mock_create_stream):
    """Test we complete ok if the user enters a stream url."""
    data = TESTDATA.copy()
    data[CONF_RTSP_TRANSPORT] = "tcp"
    data[CONF_STREAM_SOURCE] = "rtsp://127.0.0.1/testurl/2"
    with mock_create_stream as mock_setup, patch(
        "homeassistant.components.generic.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"], data
        )
    assert "errors" not in result2, f"errors={result2['errors']}"
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "127_0_0_1"
    assert result2["options"] == {
        CONF_STILL_IMAGE_URL: "http://127.0.0.1/testurl/1",
        CONF_AUTHENTICATION: HTTP_BASIC_AUTHENTICATION,
        CONF_STREAM_SOURCE: "rtsp://127.0.0.1/testurl/2",
        CONF_RTSP_TRANSPORT: "tcp",
        CONF_USERNAME: "fred_flintstone",
        CONF_PASSWORD: "bambam",
        CONF_LIMIT_REFETCH_TO_URL_CHANGE: False,
        CONF_CONTENT_TYPE: "image/png",
        CONF_FRAMERATE: 5,
        CONF_VERIFY_SSL: False,
    }

    await hass.async_block_till_done()
    assert len(mock_setup.mock_calls) == 1


async def test_form_only_stream(hass, fakeimgbytes_jpg, mock_create_stream):
    """Test we complete ok if the user wants stream only."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    data = TESTDATA.copy()
    data.pop(CONF_STILL_IMAGE_URL)
    data[CONF_STREAM_SOURCE] = "rtsp://user:pass@127.0.0.1/testurl/2"
    with mock_create_stream as mock_setup:
        result3 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            data,
        )
        await hass.async_block_till_done()

    assert result3["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result3["title"] == "127_0_0_1"
    assert result3["options"] == {
        CONF_AUTHENTICATION: HTTP_BASIC_AUTHENTICATION,
        CONF_STREAM_SOURCE: "rtsp://user:pass@127.0.0.1/testurl/2",
        CONF_USERNAME: "fred_flintstone",
        CONF_PASSWORD: "bambam",
        CONF_LIMIT_REFETCH_TO_URL_CHANGE: False,
        CONF_CONTENT_TYPE: "image/jpeg",
        CONF_FRAMERATE: 5,
        CONF_VERIFY_SSL: False,
    }

    await hass.async_block_till_done()

    with patch(
        "homeassistant.components.generic.camera.GenericCamera.async_camera_image",
        return_value=fakeimgbytes_jpg,
    ):
        image_obj = await async_get_image(hass, "camera.127_0_0_1")
        assert image_obj.content == fakeimgbytes_jpg
    assert len(mock_setup.mock_calls) == 1


async def test_form_still_and_stream_not_provided(hass, user_flow):
    """Test we show a suitable error if neither still or stream URL are provided."""
    result2 = await hass.config_entries.flow.async_configure(
        user_flow["flow_id"],
        {
            CONF_AUTHENTICATION: HTTP_BASIC_AUTHENTICATION,
            CONF_FRAMERATE: 5,
            CONF_VERIFY_SSL: False,
        },
    )
    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["errors"] == {"base": "no_still_image_or_stream_url"}


@respx.mock
async def test_form_image_timeout(hass, user_flow, mock_create_stream):
    """Test we handle invalid image timeout."""
    respx.get("http://127.0.0.1/testurl/1").side_effect = [
        httpx.TimeoutException,
    ]

    with mock_create_stream:
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )
    await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"still_image_url": "unable_still_load"}


@respx.mock
async def test_form_stream_invalidimage(hass, user_flow, mock_create_stream):
    """Test we handle invalid image when a stream is specified."""
    respx.get("http://127.0.0.1/testurl/1").respond(stream=b"invalid")
    with mock_create_stream:
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )
    await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"still_image_url": "invalid_still_image"}


@respx.mock
async def test_form_stream_invalidimage2(hass, user_flow, mock_create_stream):
    """Test we handle invalid image when a stream is specified."""
    respx.get("http://127.0.0.1/testurl/1").respond(content=None)
    with mock_create_stream:
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )
    await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"still_image_url": "unable_still_load"}


@respx.mock
async def test_form_stream_invalidimage3(hass, user_flow, mock_create_stream):
    """Test we handle invalid image when a stream is specified."""
    respx.get("http://127.0.0.1/testurl/1").respond(content=bytes([0xFF]))
    with mock_create_stream:
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )
    await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"still_image_url": "invalid_still_image"}


@respx.mock
async def test_form_stream_timeout(hass, fakeimg_png, user_flow):
    """Test we handle invalid auth."""
    with patch(
        "homeassistant.components.generic.config_flow.create_stream"
    ) as create_stream:
        create_stream.return_value.start = AsyncMock()
        create_stream.return_value.add_provider.return_value.part_recv = AsyncMock()
        create_stream.return_value.add_provider.return_value.part_recv.return_value = (
            False
        )
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )
    assert result2["type"] == "form"
    assert result2["errors"] == {"stream_source": "timeout"}


@respx.mock
async def test_form_stream_worker_error(hass, fakeimg_png, user_flow):
    """Test we handle a StreamWorkerError and pass the message through."""
    with patch(
        "homeassistant.components.generic.config_flow.create_stream",
        side_effect=StreamWorkerError("Some message"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )
    assert result2["type"] == "form"
    assert result2["errors"] == {"stream_source": "Some message"}


@respx.mock
async def test_form_stream_permission_error(hass, fakeimgbytes_png, user_flow):
    """Test we handle permission error."""
    respx.get("http://127.0.0.1/testurl/1").respond(stream=fakeimgbytes_png)
    with patch(
        "homeassistant.components.generic.config_flow.create_stream",
        side_effect=PermissionError(),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )
    assert result2["type"] == "form"
    assert result2["errors"] == {"stream_source": "stream_not_permitted"}


@respx.mock
async def test_form_no_route_to_host(hass, fakeimg_png, user_flow):
    """Test we handle no route to host."""
    with patch(
        "homeassistant.components.generic.config_flow.create_stream",
        side_effect=OSError(errno.EHOSTUNREACH, "No route to host"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )
    assert result2["type"] == "form"
    assert result2["errors"] == {"stream_source": "stream_no_route_to_host"}


@respx.mock
async def test_form_stream_io_error(hass, fakeimg_png, user_flow):
    """Test we handle no io error when setting up stream."""
    with patch(
        "homeassistant.components.generic.config_flow.create_stream",
        side_effect=OSError(errno.EIO, "Input/output error"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )
    assert result2["type"] == "form"
    assert result2["errors"] == {"stream_source": "stream_io_error"}


@respx.mock
async def test_form_oserror(hass, fakeimg_png, user_flow):
    """Test we handle OS error when setting up stream."""
    with patch(
        "homeassistant.components.generic.config_flow.create_stream",
        side_effect=OSError("Some other OSError"),
    ), pytest.raises(OSError):
        await hass.config_entries.flow.async_configure(
            user_flow["flow_id"],
            TESTDATA,
        )


@respx.mock
async def test_options_template_error(hass, fakeimgbytes_png, mock_create_stream):
    """Test the options flow with a template error."""
    respx.get("http://127.0.0.1/testurl/1").respond(stream=fakeimgbytes_png)
    respx.get("http://127.0.0.1/testurl/2").respond(stream=fakeimgbytes_png)

    mock_entry = MockConfigEntry(
        title="Test Camera",
        domain=DOMAIN,
        data={},
        options=TESTDATA,
    )

    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    # try updating the still image url
    data = TESTDATA.copy()
    data[CONF_STILL_IMAGE_URL] = "http://127.0.0.1/testurl/2"
    with mock_create_stream:
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=data,
        )
        assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

        result3 = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result3["type"] == data_entry_flow.FlowResultType.FORM
        assert result3["step_id"] == "init"

        # verify that an invalid template reports the correct UI error.
        data[CONF_STILL_IMAGE_URL] = "http://127.0.0.1/testurl/{{1/0}}"
        result4 = await hass.config_entries.options.async_configure(
            result3["flow_id"],
            user_input=data,
        )
        assert result4.get("type") == data_entry_flow.FlowResultType.FORM
        assert result4["errors"] == {"still_image_url": "template_error"}

        # verify that an invalid template reports the correct UI error.
        data[CONF_STILL_IMAGE_URL] = "http://127.0.0.1/testurl/1"
        data[CONF_STREAM_SOURCE] = "http://127.0.0.2/testurl/{{1/0}}"
        result5 = await hass.config_entries.options.async_configure(
            result4["flow_id"],
            user_input=data,
        )

        assert result5.get("type") == data_entry_flow.FlowResultType.FORM
        assert result5["errors"] == {"stream_source": "template_error"}

        # verify that an relative stream url is rejected.
        data[CONF_STILL_IMAGE_URL] = "http://127.0.0.1/testurl/1"
        data[CONF_STREAM_SOURCE] = "relative/stream.mjpeg"
        result6 = await hass.config_entries.options.async_configure(
            result5["flow_id"],
            user_input=data,
        )
        assert result6.get("type") == data_entry_flow.FlowResultType.FORM
        assert result6["errors"] == {"stream_source": "relative_url"}

        # verify that an malformed stream url is rejected.
        data[CONF_STILL_IMAGE_URL] = "http://127.0.0.1/testurl/1"
        data[CONF_STREAM_SOURCE] = "http://example.com:45:56"
        result7 = await hass.config_entries.options.async_configure(
            result6["flow_id"],
            user_input=data,
        )
    assert result7.get("type") == data_entry_flow.FlowResultType.FORM
    assert result7["errors"] == {"stream_source": "malformed_url"}


async def test_slug(hass, caplog):
    """
    Test that the slug function generates an error in case of invalid template.

    Other paths in the slug function are already tested by other tests.
    """
    result = slug(hass, "http://127.0.0.2/testurl/{{1/0}}")
    assert result is None
    assert "Syntax error in" in caplog.text

    result = slug(hass, "http://example.com:999999999999/stream")
    assert result is None
    assert "Syntax error in" in caplog.text


@respx.mock
async def test_options_only_stream(hass, fakeimgbytes_png, mock_create_stream):
    """Test the options flow without a still_image_url."""
    respx.get("http://127.0.0.1/testurl/2").respond(stream=fakeimgbytes_png)
    data = TESTDATA.copy()
    data.pop(CONF_STILL_IMAGE_URL)

    mock_entry = MockConfigEntry(
        title="Test Camera",
        domain=DOMAIN,
        data={},
        options=data,
    )
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    # try updating the config options
    with mock_create_stream:
        result3 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=data,
        )
    assert result3["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result3["data"][CONF_CONTENT_TYPE] == "image/jpeg"


# These below can be deleted after deprecation period is finished.
@respx.mock
async def test_import(hass, fakeimg_png):
    """Test configuration.yaml import used during migration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data=TESTDATA_YAML
    )
    # duplicate import should be aborted
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data=TESTDATA_YAML
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Yaml Defined Name"
    await hass.async_block_till_done()
    # Any name defined in yaml should end up as the entity id.
    assert hass.states.get("camera.yaml_defined_name")
    assert result2["type"] == data_entry_flow.FlowResultType.ABORT


# These above can be deleted after deprecation period is finished.


async def test_unload_entry(hass, fakeimg_png):
    """Test unloading the generic IP Camera entry."""
    mock_entry = MockConfigEntry(domain=DOMAIN, options=TESTDATA)
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is config_entries.ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is config_entries.ConfigEntryState.NOT_LOADED


async def test_reload_on_title_change(hass) -> None:
    """Test the integration gets reloaded when the title is updated."""

    test_data = TESTDATA_OPTIONS
    test_data[CONF_CONTENT_TYPE] = "image/png"
    mock_entry = MockConfigEntry(
        domain=DOMAIN, unique_id="54321", options=test_data, title="My Title"
    )
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is config_entries.ConfigEntryState.LOADED
    assert hass.states.get("camera.my_title").attributes["friendly_name"] == "My Title"

    hass.config_entries.async_update_entry(mock_entry, title="New Title")
    assert mock_entry.title == "New Title"
    await hass.async_block_till_done()

    assert hass.states.get("camera.my_title").attributes["friendly_name"] == "New Title"


async def test_migrate_existing_ids(hass) -> None:
    """Test that existing ids are migrated for issue #70568."""

    registry = entity_registry.async_get(hass)

    test_data = TESTDATA_OPTIONS.copy()
    test_data[CONF_CONTENT_TYPE] = "image/png"
    old_unique_id = "54321"
    entity_id = "camera.sample_camera"

    mock_entry = MockConfigEntry(
        domain=DOMAIN, unique_id=old_unique_id, options=test_data, title="My Title"
    )
    new_unique_id = mock_entry.entry_id
    mock_entry.add_to_hass(hass)

    entity_entry = registry.async_get_or_create(
        "camera",
        DOMAIN,
        old_unique_id,
        suggested_object_id="sample camera",
        config_entry=mock_entry,
    )
    assert entity_entry.entity_id == entity_id
    assert entity_entry.unique_id == old_unique_id

    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    entity_entry = registry.async_get(entity_id)
    assert entity_entry.unique_id == new_unique_id


@respx.mock
async def test_use_wallclock_as_timestamps_option(
    hass, fakeimg_png, mock_create_stream
):
    """Test the use_wallclock_as_timestamps option flow."""

    mock_entry = MockConfigEntry(
        title="Test Camera",
        domain=DOMAIN,
        data={},
        options=TESTDATA,
    )

    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(
        mock_entry.entry_id, context={"show_advanced_options": True}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"
    with patch(
        "homeassistant.components.generic.async_setup_entry", return_value=True
    ), mock_create_stream:
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_USE_WALLCLOCK_AS_TIMESTAMPS: True, **TESTDATA},
        )
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
