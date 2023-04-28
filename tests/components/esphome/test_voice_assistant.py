"""Test ESPHome voice assistant server."""

import asyncio
import socket
from unittest.mock import Mock, patch

from aioesphomeapi import VoiceAssistantEventType
import async_timeout
import pytest

from homeassistant.components import esphome
from homeassistant.components.assist_pipeline import PipelineEvent, PipelineEventType
from homeassistant.components.esphome import DomainData
from homeassistant.components.esphome.voice_assistant import VoiceAssistantUDPServer
from homeassistant.core import HomeAssistant

_TEST_INPUT_TEXT = "This is an input test"
_TEST_OUTPUT_TEXT = "This is an output test"
_TEST_OUTPUT_URL = "output.mp3"
_TEST_MEDIA_ID = "12345"


@pytest.fixture
def voice_assistant_udp_server_v1(
    hass: HomeAssistant,
    mock_voice_assistant_v1_entry,
) -> VoiceAssistantUDPServer:
    """Return the UDP server."""
    entry_data = DomainData.get(hass).get_entry_data(mock_voice_assistant_v1_entry)

    server: VoiceAssistantUDPServer = None

    def handle_finished():
        nonlocal server
        assert server is not None
        server.close()

    server = VoiceAssistantUDPServer(hass, entry_data, Mock(), handle_finished)
    return server


@pytest.fixture
def voice_assistant_udp_server_v2(
    hass: HomeAssistant,
    mock_voice_assistant_v2_entry,
) -> VoiceAssistantUDPServer:
    """Return the UDP server."""
    entry_data = DomainData.get(hass).get_entry_data(mock_voice_assistant_v2_entry)

    server: VoiceAssistantUDPServer = None

    def handle_finished():
        nonlocal server
        assert server is not None
        server.close()

    server = VoiceAssistantUDPServer(hass, entry_data, Mock(), handle_finished)
    return server


async def test_pipeline_events(
    hass: HomeAssistant,
    voice_assistant_udp_server_v1: VoiceAssistantUDPServer,
) -> None:
    """Test that the pipeline function is called."""

    async def async_pipeline_from_audio_stream(*args, **kwargs):
        event_callback = kwargs["event_callback"]

        # Fake events
        event_callback(
            PipelineEvent(
                type=PipelineEventType.STT_START,
                data={},
            )
        )

        event_callback(
            PipelineEvent(
                type=PipelineEventType.STT_END,
                data={"stt_output": {"text": _TEST_INPUT_TEXT}},
            )
        )

        event_callback(
            PipelineEvent(
                type=PipelineEventType.TTS_START,
                data={"tts_input": _TEST_OUTPUT_TEXT},
            )
        )

        event_callback(
            PipelineEvent(
                type=PipelineEventType.TTS_END,
                data={"tts_output": {"url": _TEST_OUTPUT_URL}},
            )
        )

    def handle_event(
        event_type: esphome.VoiceAssistantEventType, data: dict[str, str] | None
    ) -> None:
        if event_type == esphome.VoiceAssistantEventType.VOICE_ASSISTANT_STT_END:
            assert data is not None
            assert data["text"] == _TEST_INPUT_TEXT
        elif event_type == esphome.VoiceAssistantEventType.VOICE_ASSISTANT_TTS_START:
            assert data is not None
            assert data["text"] == _TEST_OUTPUT_TEXT
        elif event_type == esphome.VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            assert data is not None
            assert data["url"] == _TEST_OUTPUT_URL

    voice_assistant_udp_server_v1.handle_event = handle_event

    with patch(
        "homeassistant.components.esphome.voice_assistant.async_pipeline_from_audio_stream",
        new=async_pipeline_from_audio_stream,
    ):
        voice_assistant_udp_server_v1.transport = Mock()

        await voice_assistant_udp_server_v1.run_pipeline()


async def test_udp_server(
    hass: HomeAssistant,
    socket_enabled,
    unused_udp_port_factory,
    voice_assistant_udp_server_v1: VoiceAssistantUDPServer,
) -> None:
    """Test the UDP server runs and queues incoming data."""
    port_to_use = unused_udp_port_factory()

    with patch(
        "homeassistant.components.esphome.voice_assistant.UDP_PORT", new=port_to_use
    ):
        port = await voice_assistant_udp_server_v1.start_server()
        assert port == port_to_use

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        assert voice_assistant_udp_server_v1.queue.qsize() == 0
        sock.sendto(b"test", ("127.0.0.1", port))

        # Give the socket some time to send/receive the data
        async with async_timeout.timeout(1):
            while voice_assistant_udp_server_v1.queue.qsize() == 0:
                await asyncio.sleep(0.1)

        assert voice_assistant_udp_server_v1.queue.qsize() == 1

        voice_assistant_udp_server_v1.stop()
        voice_assistant_udp_server_v1.close()

        assert voice_assistant_udp_server_v1.transport.is_closing()


async def test_udp_server_queue(
    hass: HomeAssistant,
    voice_assistant_udp_server_v1: VoiceAssistantUDPServer,
) -> None:
    """Test the UDP server queues incoming data."""

    voice_assistant_udp_server_v1.started = True

    assert voice_assistant_udp_server_v1.queue.qsize() == 0

    voice_assistant_udp_server_v1.datagram_received(bytes(1024), ("localhost", 0))
    assert voice_assistant_udp_server_v1.queue.qsize() == 1

    voice_assistant_udp_server_v1.datagram_received(bytes(1024), ("localhost", 0))
    assert voice_assistant_udp_server_v1.queue.qsize() == 2

    async for data in voice_assistant_udp_server_v1._iterate_packets():
        assert data == bytes(1024)
        break
    assert voice_assistant_udp_server_v1.queue.qsize() == 1  # One message removed

    voice_assistant_udp_server_v1.stop()
    assert (
        voice_assistant_udp_server_v1.queue.qsize() == 2
    )  # An empty message added by stop

    voice_assistant_udp_server_v1.datagram_received(bytes(1024), ("localhost", 0))
    assert (
        voice_assistant_udp_server_v1.queue.qsize() == 2
    )  # No new messages added after stop

    voice_assistant_udp_server_v1.close()

    with pytest.raises(RuntimeError):
        async for data in voice_assistant_udp_server_v1._iterate_packets():
            assert data == bytes(1024)


async def test_error_calls_handle_finished(
    hass: HomeAssistant,
    voice_assistant_udp_server_v1: VoiceAssistantUDPServer,
) -> None:
    """Test that the handle_finished callback is called when an error occurs."""
    voice_assistant_udp_server_v1.handle_finished = Mock()

    voice_assistant_udp_server_v1.error_received(Exception())

    voice_assistant_udp_server_v1.handle_finished.assert_called()


async def test_udp_server_multiple(
    hass: HomeAssistant,
    socket_enabled,
    unused_udp_port_factory,
    voice_assistant_udp_server_v1: VoiceAssistantUDPServer,
) -> None:
    """Test that the UDP server raises an error if started twice."""
    with patch(
        "homeassistant.components.esphome.voice_assistant.UDP_PORT",
        new=unused_udp_port_factory(),
    ):
        await voice_assistant_udp_server_v1.start_server()

    with patch(
        "homeassistant.components.esphome.voice_assistant.UDP_PORT",
        new=unused_udp_port_factory(),
    ), pytest.raises(RuntimeError):
        pass
        await voice_assistant_udp_server_v1.start_server()


async def test_udp_server_after_stopped(
    hass: HomeAssistant,
    socket_enabled,
    unused_udp_port_factory,
    voice_assistant_udp_server_v1: VoiceAssistantUDPServer,
) -> None:
    """Test that the UDP server raises an error if started after stopped."""
    voice_assistant_udp_server_v1.close()
    with patch(
        "homeassistant.components.esphome.voice_assistant.UDP_PORT",
        new=unused_udp_port_factory(),
    ), pytest.raises(RuntimeError):
        await voice_assistant_udp_server_v1.start_server()


async def test_unknown_event_type(
    hass: HomeAssistant,
    voice_assistant_udp_server_v1: VoiceAssistantUDPServer,
) -> None:
    """Test the UDP server does not call handle_event for unknown events."""
    voice_assistant_udp_server_v1._event_callback(
        PipelineEvent(
            type="unknown-event",
            data={},
        )
    )

    assert not voice_assistant_udp_server_v1.handle_event.called


async def test_error_event_type(
    hass: HomeAssistant,
    voice_assistant_udp_server_v1: VoiceAssistantUDPServer,
) -> None:
    """Test the UDP server calls event handler with error."""
    voice_assistant_udp_server_v1._event_callback(
        PipelineEvent(
            type=PipelineEventType.ERROR,
            data={"code": "code", "message": "message"},
        )
    )

    assert voice_assistant_udp_server_v1.handle_event.called_with(
        VoiceAssistantEventType.VOICE_ASSISTANT_ERROR,
        {"code": "code", "message": "message"},
    )


async def test_send_tts_not_called(
    hass: HomeAssistant,
    voice_assistant_udp_server_v1: VoiceAssistantUDPServer,
) -> None:
    """Test the UDP server with a v1 device does not call _send_tts."""
    with patch(
        "homeassistant.components.esphome.voice_assistant.VoiceAssistantUDPServer._send_tts"
    ) as mock_send_tts:
        voice_assistant_udp_server_v1._event_callback(
            PipelineEvent(
                type=PipelineEventType.TTS_END,
                data={
                    "tts_output": {"media_id": _TEST_MEDIA_ID, "url": _TEST_OUTPUT_URL}
                },
            )
        )

        mock_send_tts.assert_not_called()


async def test_send_tts_called(
    hass: HomeAssistant,
    voice_assistant_udp_server_v2: VoiceAssistantUDPServer,
) -> None:
    """Test the UDP server with a v2 device calls _send_tts."""
    with patch(
        "homeassistant.components.esphome.voice_assistant.VoiceAssistantUDPServer._send_tts"
    ) as mock_send_tts:
        voice_assistant_udp_server_v2._event_callback(
            PipelineEvent(
                type=PipelineEventType.TTS_END,
                data={
                    "tts_output": {"media_id": _TEST_MEDIA_ID, "url": _TEST_OUTPUT_URL}
                },
            )
        )

        mock_send_tts.assert_called_with(_TEST_MEDIA_ID)


async def test_send_tts(
    hass: HomeAssistant,
    voice_assistant_udp_server_v2: VoiceAssistantUDPServer,
) -> None:
    """Test the UDP server calls sendto to transmit audio data to device."""
    with patch(
        "homeassistant.components.esphome.voice_assistant.tts.async_get_media_source_audio",
        return_value=("raw", bytes(1024)),
    ):
        voice_assistant_udp_server_v2.transport = Mock(spec=asyncio.DatagramTransport)

        voice_assistant_udp_server_v2._event_callback(
            PipelineEvent(
                type=PipelineEventType.TTS_END,
                data={
                    "tts_output": {"media_id": _TEST_MEDIA_ID, "url": _TEST_OUTPUT_URL}
                },
            )
        )

        await voice_assistant_udp_server_v2._tts_done.wait()

        voice_assistant_udp_server_v2.transport.sendto.assert_called()
