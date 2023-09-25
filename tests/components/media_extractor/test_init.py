"""The tests for Media Extractor integration."""
from typing import Any
from unittest.mock import patch

import pytest
from syrupy import SnapshotAssertion
from yt_dlp import DownloadError

from homeassistant.components.media_extractor import DOMAIN
from homeassistant.components.media_player import SERVICE_PLAY_MEDIA
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component

from tests.common import load_json_object_fixture
from tests.components.media_extractor import (
    YOUTUBE_EMPTY_PLAYLIST,
    YOUTUBE_PLAYLIST,
    YOUTUBE_VIDEO,
    MockYoutubeDL,
)
from tests.components.media_extractor.const import NO_FORMATS_RESPONSE, SOUNDCLOUD_TRACK


async def test_play_media_service_is_registered(hass: HomeAssistant) -> None:
    """Test play media service is registered."""
    await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_PLAY_MEDIA)


@pytest.mark.parametrize(
    "config_fixture", ["empty_media_extractor_config", "audio_media_extractor_config"]
)
@pytest.mark.parametrize(
    ("media_content_id", "media_content_type"),
    [
        (YOUTUBE_VIDEO, "VIDEO"),
        (SOUNDCLOUD_TRACK, "AUDIO"),
        (NO_FORMATS_RESPONSE, "AUDIO"),
    ],
)
async def test_play_media_service(
    hass: HomeAssistant,
    mock_youtube_dl: MockYoutubeDL,
    calls: list[ServiceCall],
    snapshot: SnapshotAssertion,
    request: pytest.FixtureRequest,
    config_fixture: str,
    media_content_id: str,
    media_content_type: str,
) -> None:
    """Test play media service is registered."""
    config: dict[str, Any] = request.getfixturevalue(config_fixture)
    await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY_MEDIA,
        {
            "entity_id": "media_player.bedroom",
            "media_content_type": media_content_type,
            "media_content_id": media_content_id,
        },
    )
    await hass.async_block_till_done()

    assert calls[0].data == snapshot


async def test_download_error(
    hass: HomeAssistant,
    empty_media_extractor_config: dict[str, Any],
    calls: list[ServiceCall],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling DownloadError."""

    with patch(
        "homeassistant.components.media_extractor.YoutubeDL.extract_info",
        side_effect=DownloadError("Message"),
    ):
        await async_setup_component(hass, DOMAIN, empty_media_extractor_config)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                "entity_id": "media_player.bedroom",
                "media_content_type": "VIDEO",
                "media_content_id": YOUTUBE_VIDEO,
            },
        )
        await hass.async_block_till_done()

    assert len(calls) == 0
    assert f"Could not retrieve data for the URL: {YOUTUBE_VIDEO}" in caplog.text


async def test_no_target_entity(
    hass: HomeAssistant,
    mock_youtube_dl: MockYoutubeDL,
    empty_media_extractor_config: dict[str, Any],
    calls: list[ServiceCall],
    snapshot: SnapshotAssertion,
) -> None:
    """Test having no target entity."""

    await async_setup_component(hass, DOMAIN, empty_media_extractor_config)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY_MEDIA,
        {
            "device_id": "fb034c3a9fefe47c584c32a6b51817eb",
            "media_content_type": "VIDEO",
            "media_content_id": YOUTUBE_VIDEO,
        },
    )
    await hass.async_block_till_done()

    assert calls[0].data == snapshot


async def test_playlist(
    hass: HomeAssistant,
    mock_youtube_dl: MockYoutubeDL,
    empty_media_extractor_config: dict[str, Any],
    calls: list[ServiceCall],
    snapshot: SnapshotAssertion,
) -> None:
    """Test extracting a playlist."""

    await async_setup_component(hass, DOMAIN, empty_media_extractor_config)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY_MEDIA,
        {
            "entity_id": "media_player.bedroom",
            "media_content_type": "VIDEO",
            "media_content_id": YOUTUBE_PLAYLIST,
        },
    )
    await hass.async_block_till_done()

    assert calls[0].data == snapshot


async def test_playlist_no_entries(
    hass: HomeAssistant,
    mock_youtube_dl: MockYoutubeDL,
    empty_media_extractor_config: dict[str, Any],
    calls: list[ServiceCall],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test extracting a playlist without entries."""

    await async_setup_component(hass, DOMAIN, empty_media_extractor_config)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_PLAY_MEDIA,
        {
            "entity_id": "media_player.bedroom",
            "media_content_type": "VIDEO",
            "media_content_id": YOUTUBE_EMPTY_PLAYLIST,
        },
    )
    await hass.async_block_till_done()

    assert len(calls) == 0
    assert (
        f"Could not retrieve data for the URL: {YOUTUBE_EMPTY_PLAYLIST}" in caplog.text
    )


async def test_query_error(
    hass: HomeAssistant,
    empty_media_extractor_config: dict[str, Any],
    calls: list[ServiceCall],
) -> None:
    """Test handling error with query."""

    with patch(
        "homeassistant.components.media_extractor.YoutubeDL.extract_info",
        return_value=load_json_object_fixture("media_extractor/youtube_1_info.json"),
    ), patch(
        "homeassistant.components.media_extractor.YoutubeDL.process_ie_result",
        side_effect=DownloadError("Message"),
    ):
        await async_setup_component(hass, DOMAIN, empty_media_extractor_config)
        await hass.async_block_till_done()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                "entity_id": "media_player.bedroom",
                "media_content_type": "VIDEO",
                "media_content_id": YOUTUBE_VIDEO,
            },
        )
        await hass.async_block_till_done()

    assert len(calls) == 0
