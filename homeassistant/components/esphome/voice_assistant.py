"""ESPHome voice assistant support."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Callable
import logging
import socket
from typing import cast

from aioesphomeapi import VoiceAssistantEventType
import async_timeout

from homeassistant.components import stt, tts
from homeassistant.components.assist_pipeline import (
    PipelineEvent,
    PipelineEventType,
    async_pipeline_from_audio_stream,
    select as pipeline_select,
)
from homeassistant.components.media_player import async_process_play_media_url
from homeassistant.core import Context, HomeAssistant, callback

from .const import DOMAIN
from .entry_data import RuntimeEntryData
from .enum_mapper import EsphomeEnumMapper

_LOGGER = logging.getLogger(__name__)

UDP_PORT = 0  # Set to 0 to let the OS pick a free random port
UDP_MAX_PACKET_SIZE = 1024

_VOICE_ASSISTANT_EVENT_TYPES: EsphomeEnumMapper[
    VoiceAssistantEventType, PipelineEventType
] = EsphomeEnumMapper(
    {
        VoiceAssistantEventType.VOICE_ASSISTANT_ERROR: PipelineEventType.ERROR,
        VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START: PipelineEventType.RUN_START,
        VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END: PipelineEventType.RUN_END,
        VoiceAssistantEventType.VOICE_ASSISTANT_STT_START: PipelineEventType.STT_START,
        VoiceAssistantEventType.VOICE_ASSISTANT_STT_END: PipelineEventType.STT_END,
        VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_START: PipelineEventType.INTENT_START,
        VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_END: PipelineEventType.INTENT_END,
        VoiceAssistantEventType.VOICE_ASSISTANT_TTS_START: PipelineEventType.TTS_START,
        VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END: PipelineEventType.TTS_END,
    }
)


class VoiceAssistantUDPServer(asyncio.DatagramProtocol):
    """Receive UDP packets and forward them to the voice assistant."""

    started = False
    queue: asyncio.Queue[bytes] | None = None
    transport: asyncio.DatagramTransport | None = None
    remote_addr: tuple[str, int] | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        entry_data: RuntimeEntryData,
        handle_event: Callable[[VoiceAssistantEventType, dict[str, str] | None], None],
        handle_finished: Callable[[], None],
    ) -> None:
        """Initialize UDP receiver."""
        self.context = Context()
        self.hass = hass

        assert entry_data.device_info is not None
        self.device_info = entry_data.device_info

        self.queue = asyncio.Queue()
        self.handle_event = handle_event
        self.handle_finished = handle_finished
        self._tts_done = asyncio.Event()

    async def start_server(self) -> int:
        """Start accepting connections."""

        def accept_connection() -> VoiceAssistantUDPServer:
            """Accept connection."""
            if self.started:
                raise RuntimeError("Can only start once")
            if self.queue is None:
                raise RuntimeError("No longer accepting connections")

            self.started = True
            return self

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)

        sock.bind(("", UDP_PORT))

        await asyncio.get_running_loop().create_datagram_endpoint(
            accept_connection, sock=sock
        )

        return cast(int, sock.getsockname()[1])

    @callback
    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Store transport for later use."""
        self.transport = cast(asyncio.DatagramTransport, transport)

    @callback
    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle incoming UDP packet."""
        if not self.started:
            return
        if self.remote_addr is None:
            self.remote_addr = addr
        if self.queue is not None:
            self.queue.put_nowait(data)

    def error_received(self, exc: Exception) -> None:
        """Handle when a send or receive operation raises an OSError.

        (Other than BlockingIOError or InterruptedError.)
        """
        _LOGGER.error("ESPHome Voice Assistant UDP server error received: %s", exc)
        self.handle_finished()

    @callback
    def stop(self) -> None:
        """Stop the receiver."""
        if self.queue is not None:
            self.queue.put_nowait(b"")
        self.started = False

    def close(self) -> None:
        """Close the receiver."""
        if self.queue is not None:
            self.queue = None
        if self.transport is not None:
            self.transport.close()

    async def _iterate_packets(self) -> AsyncIterable[bytes]:
        """Iterate over incoming packets."""
        if self.queue is None:
            raise RuntimeError("Already stopped")

        while data := await self.queue.get():
            yield data

    def _event_callback(self, event: PipelineEvent) -> None:
        """Handle pipeline events."""

        try:
            event_type = _VOICE_ASSISTANT_EVENT_TYPES.from_hass(event.type)
        except KeyError:
            _LOGGER.warning("Received unknown pipeline event type: %s", event.type)
            return

        data_to_send = None
        if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_STT_END:
            assert event.data is not None
            data_to_send = {"text": event.data["stt_output"]["text"]}
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_START:
            assert event.data is not None
            data_to_send = {"text": event.data["tts_input"]}
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            assert event.data is not None
            path = event.data["tts_output"]["url"]
            url = async_process_play_media_url(self.hass, path)
            data_to_send = {"url": url}

            if self.device_info.voice_assistant_version >= 2:
                media_id = event.data["tts_output"]["media_id"]
                self.hass.async_create_background_task(
                    self._send_tts(media_id), "esphome_voice_assistant_tts"
                )
            else:
                self._tts_done.set()
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_ERROR:
            assert event.data is not None
            data_to_send = {
                "code": event.data["code"],
                "message": event.data["message"],
            }
            self.handle_finished()

        self.handle_event(event_type, data_to_send)

    async def run_pipeline(
        self,
        pipeline_timeout: float = 30.0,
    ) -> None:
        """Run the Voice Assistant pipeline."""
        try:
            tts_audio_output = (
                "raw" if self.device_info.voice_assistant_version >= 2 else "mp3"
            )
            async with async_timeout.timeout(pipeline_timeout):
                await async_pipeline_from_audio_stream(
                    self.hass,
                    context=self.context,
                    event_callback=self._event_callback,
                    stt_metadata=stt.SpeechMetadata(
                        language="",  # set in async_pipeline_from_audio_stream
                        format=stt.AudioFormats.WAV,
                        codec=stt.AudioCodecs.PCM,
                        bit_rate=stt.AudioBitRates.BITRATE_16,
                        sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
                        channel=stt.AudioChannels.CHANNEL_MONO,
                    ),
                    stt_stream=self._iterate_packets(),
                    pipeline_id=pipeline_select.get_chosen_pipeline(
                        self.hass, DOMAIN, self.device_info.mac_address
                    ),
                    tts_audio_output=tts_audio_output,
                )

                # Block until TTS is done sending
                await self._tts_done.wait()

            _LOGGER.debug("Pipeline finished")
        except asyncio.TimeoutError:
            _LOGGER.warning("Pipeline timeout")
        finally:
            self.handle_finished()

    async def _send_tts(self, media_id: str) -> None:
        """Send TTS audio to device via UDP."""
        try:
            if self.transport is None:
                return

            _extension, audio_bytes = await tts.async_get_media_source_audio(
                self.hass,
                media_id,
            )

            _LOGGER.debug("Sending %d bytes of audio", len(audio_bytes))

            bytes_per_sample = stt.AudioBitRates.BITRATE_16 // 8
            sample_offset = 0
            samples_left = len(audio_bytes) // bytes_per_sample

            while samples_left > 0:
                bytes_offset = sample_offset * bytes_per_sample
                chunk: bytes = audio_bytes[bytes_offset : bytes_offset + 1024]
                samples_in_chunk = len(chunk) // bytes_per_sample
                samples_left -= samples_in_chunk

                self.transport.sendto(chunk, self.remote_addr)
                await asyncio.sleep(
                    samples_in_chunk / stt.AudioSampleRates.SAMPLERATE_16000 * 0.99
                )

                sample_offset += samples_in_chunk

        finally:
            self._tts_done.set()
