"""Test ESPHome voice assistant server."""

import asyncio
import socket
from unittest.mock import Mock, patch

from aioesphomeapi import VoiceAssistantEventType
import async_timeout
import pytest

from homeassistant.components.assist_pipeline import PipelineEvent, PipelineEventType
from homeassistant.components.esphome import DomainData
from homeassistant.components.esphome.voice_assistant import VoiceAssistantUDPServer
from homeassistant.core import HomeAssistant

_TEST_INPUT_TEXT = "This is an input test"
_TEST_OUTPUT_TEXT = "This is an output test"
_TEST_OUTPUT_URL = "output.mp3"
_TEST_MEDIA_ID = "12345"

_ONE_SECOND = 16000 * 2  # 16Khz 16-bit


@pytest.fixture
def voice_assistant_udp_server(
    hass: HomeAssistant,
) -> VoiceAssistantUDPServer:
    """Return the UDP server factory."""

    def _voice_assistant_udp_server(entry):
        entry_data = DomainData.get(hass).get_entry_data(entry)

        server: VoiceAssistantUDPServer = None

        def handle_finished():
            nonlocal server
            assert server is not None
            server.close()

        server = VoiceAssistantUDPServer(hass, entry_data, Mock(), handle_finished)
        return server

    return _voice_assistant_udp_server


@pytest.fixture
def voice_assistant_udp_server_v1(
    voice_assistant_udp_server,
    mock_voice_assistant_v1_entry,
) -> VoiceAssistantUDPServer:
    """Return the UDP server."""
    return voice_assistant_udp_server(entry=mock_voice_assistant_v1_entry)


@pytest.fixture
def voice_assistant_udp_server_v2(
    voice_assistant_udp_server,
    mock_voice_assistant_v2_entry,
) -> VoiceAssistantUDPServer:
    """Return the UDP server."""
    return voice_assistant_udp_server(entry=mock_voice_assistant_v2_entry)


async def test_pipeline_events(
    hass: HomeAssistant,
    voice_assistant_udp_server_v1: VoiceAssistantUDPServer,
) -> None:
    """Test that the pipeline function is called."""

    async def async_pipeline_from_audio_stream(*args, device_id, **kwargs):
        assert device_id == "mock-device-id"

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
        event_type: VoiceAssistantEventType, data: dict[str, str] | None
    ) -> None:
        if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_STT_END:
            assert data is not None
            assert data["text"] == _TEST_INPUT_TEXT
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_START:
            assert data is not None
            assert data["text"] == _TEST_OUTPUT_TEXT
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            assert data is not None
            assert data["url"] == _TEST_OUTPUT_URL

    voice_assistant_udp_server_v1.handle_event = handle_event

    with patch(
        "homeassistant.components.esphome.voice_assistant.async_pipeline_from_audio_stream",
        new=async_pipeline_from_audio_stream,
    ):
        voice_assistant_udp_server_v1.transport = Mock()

        await voice_assistant_udp_server_v1.run_pipeline(
            device_id="mock-device-id", conversation_id=None
        )


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

    voice_assistant_udp_server_v1.handle_event.assert_called_with(
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


async def test_speech_detection(
    hass: HomeAssistant,
    voice_assistant_udp_server_v2: VoiceAssistantUDPServer,
) -> None:
    """Test the UDP server queues incoming data."""

    def is_speech(self, chunk, sample_rate):
        """Anything non-zero is speech."""
        return sum(chunk) > 0

    async def async_pipeline_from_audio_stream(*args, **kwargs):
        stt_stream = kwargs["stt_stream"]
        event_callback = kwargs["event_callback"]
        async for _chunk in stt_stream:
            pass

        # Test empty data
        event_callback(
            PipelineEvent(
                type=PipelineEventType.STT_END,
                data={"stt_output": {"text": _TEST_INPUT_TEXT}},
            )
        )

    with patch(
        "webrtcvad.Vad.is_speech",
        new=is_speech,
    ), patch(
        "homeassistant.components.esphome.voice_assistant.async_pipeline_from_audio_stream",
        new=async_pipeline_from_audio_stream,
    ):
        voice_assistant_udp_server_v2.started = True

        voice_assistant_udp_server_v2.queue.put_nowait(bytes(_ONE_SECOND))
        voice_assistant_udp_server_v2.queue.put_nowait(bytes([255] * _ONE_SECOND * 2))
        voice_assistant_udp_server_v2.queue.put_nowait(bytes([255] * _ONE_SECOND * 2))
        voice_assistant_udp_server_v2.queue.put_nowait(bytes(_ONE_SECOND))

        await voice_assistant_udp_server_v2.run_pipeline(
            device_id="", conversation_id=None, use_vad=True, pipeline_timeout=1.0
        )


async def test_no_speech(
    hass: HomeAssistant,
    voice_assistant_udp_server_v2: VoiceAssistantUDPServer,
) -> None:
    """Test there is no speech."""

    def is_speech(self, chunk, sample_rate):
        """Anything non-zero is speech."""
        return sum(chunk) > 0

    def handle_event(
        event_type: VoiceAssistantEventType, data: dict[str, str] | None
    ) -> None:
        assert event_type == VoiceAssistantEventType.VOICE_ASSISTANT_ERROR
        assert data is not None
        assert data["code"] == "speech-timeout"

    voice_assistant_udp_server_v2.handle_event = handle_event

    with patch(
        "webrtcvad.Vad.is_speech",
        new=is_speech,
    ):
        voice_assistant_udp_server_v2.started = True

        voice_assistant_udp_server_v2.queue.put_nowait(bytes(_ONE_SECOND))

        await voice_assistant_udp_server_v2.run_pipeline(
            device_id="", conversation_id=None, use_vad=True, pipeline_timeout=1.0
        )


async def test_speech_timeout(
    hass: HomeAssistant,
    voice_assistant_udp_server_v2: VoiceAssistantUDPServer,
) -> None:
    """Test when speech was detected, but the pipeline times out."""

    def is_speech(self, chunk, sample_rate):
        """Anything non-zero is speech."""
        return sum(chunk) > 255

    async def async_pipeline_from_audio_stream(*args, **kwargs):
        stt_stream = kwargs["stt_stream"]
        async for _chunk in stt_stream:
            # Stream will end when VAD detects end of "speech"
            pass

    async def segment_audio(*args, **kwargs):
        raise asyncio.TimeoutError()
        async for chunk in []:
            yield chunk

    with patch(
        "webrtcvad.Vad.is_speech",
        new=is_speech,
    ), patch(
        "homeassistant.components.esphome.voice_assistant.async_pipeline_from_audio_stream",
        new=async_pipeline_from_audio_stream,
    ), patch(
        "homeassistant.components.esphome.voice_assistant.VoiceAssistantUDPServer._segment_audio",
        new=segment_audio,
    ):
        voice_assistant_udp_server_v2.started = True

        voice_assistant_udp_server_v2.queue.put_nowait(bytes([255] * (_ONE_SECOND * 2)))

        await voice_assistant_udp_server_v2.run_pipeline(
            device_id="", conversation_id=None, use_vad=True, pipeline_timeout=1.0
        )


async def test_cancelled(
    hass: HomeAssistant,
    voice_assistant_udp_server_v2: VoiceAssistantUDPServer,
) -> None:
    """Test when the server is stopped while waiting for speech."""

    voice_assistant_udp_server_v2.started = True

    voice_assistant_udp_server_v2.queue.put_nowait(b"")

    await voice_assistant_udp_server_v2.run_pipeline(
        device_id="", conversation_id=None, use_vad=True, pipeline_timeout=1.0
    )

    # No events should be sent if cancelled while waiting for speech
    voice_assistant_udp_server_v2.handle_event.assert_not_called()
