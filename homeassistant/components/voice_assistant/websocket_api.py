"""Voice Assistant Websocket API."""
import asyncio
import audioop  # pylint: disable=deprecated-module
from collections.abc import Callable
import logging
from typing import Any

import async_timeout
import voluptuous as vol

from homeassistant.components import stt, websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

from .pipeline import (
    PipelineError,
    PipelineEvent,
    PipelineEventType,
    PipelineInput,
    PipelineRun,
    PipelineStage,
    async_get_pipeline,
)
from .vad import VoiceCommandSegmenter

DEFAULT_TIMEOUT = 30

_LOGGER = logging.getLogger(__name__)


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register the websocket API."""
    websocket_api.async_register_command(
        hass,
        "voice_assistant/run",
        websocket_run,
        vol.All(
            websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
                {
                    vol.Required("type"): "voice_assistant/run",
                    # pylint: disable-next=unnecessary-lambda
                    vol.Required("start_stage"): lambda val: PipelineStage(val),
                    # pylint: disable-next=unnecessary-lambda
                    vol.Required("end_stage"): lambda val: PipelineStage(val),
                    vol.Optional("input"): dict,
                    vol.Optional("language"): str,
                    vol.Optional("pipeline"): str,
                    vol.Optional("conversation_id"): vol.Any(str, None),
                    vol.Optional("timeout"): vol.Any(float, int),
                },
            ),
            cv.key_value_schemas(
                "start_stage",
                {
                    PipelineStage.STT: vol.Schema(
                        {vol.Required("input"): {vol.Required("sample_rate"): int}},
                        extra=vol.ALLOW_EXTRA,
                    ),
                    PipelineStage.INTENT: vol.Schema(
                        {vol.Required("input"): {"text": str}},
                        extra=vol.ALLOW_EXTRA,
                    ),
                    PipelineStage.TTS: vol.Schema(
                        {vol.Required("input"): {"text": str}},
                        extra=vol.ALLOW_EXTRA,
                    ),
                },
            ),
        ),
    )


@websocket_api.async_response
async def websocket_run(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run a pipeline."""
    language = msg.get("language", hass.config.language)

    # Temporary workaround for language codes
    if language == "en":
        language = "en-US"

    pipeline_id = msg.get("pipeline")
    pipeline = await async_get_pipeline(
        hass,
        pipeline_id=pipeline_id,
        language=language,
    )
    if pipeline is None:
        connection.send_error(
            msg["id"],
            "pipeline-not-found",
            f"Pipeline not found: id={pipeline_id}, language={language}",
        )
        return

    timeout = msg.get("timeout", DEFAULT_TIMEOUT)
    start_stage = PipelineStage(msg["start_stage"])
    end_stage = PipelineStage(msg["end_stage"])
    handler_id: int | None = None
    unregister_handler: Callable[[], None] | None = None

    # Arguments to PipelineInput
    input_args: dict[str, Any] = {
        "conversation_id": msg.get("conversation_id"),
    }

    if start_stage == PipelineStage.STT:
        # Audio pipeline that will receive audio as binary websocket messages
        audio_queue: "asyncio.Queue[bytes]" = asyncio.Queue()
        incoming_sample_rate = msg["input"]["sample_rate"]

        async def stt_stream():
            state = None
            segmenter = VoiceCommandSegmenter()

            # Yield until we receive an empty chunk
            while chunk := await audio_queue.get():
                chunk, state = audioop.ratecv(
                    chunk, 2, 1, incoming_sample_rate, 16000, state
                )
                if not segmenter.process(chunk):
                    # Voice command is finished
                    break

                yield chunk

        def handle_binary(_hass, _connection, data: bytes):
            # Forward to STT audio stream
            audio_queue.put_nowait(data)

        handler_id, unregister_handler = connection.async_register_binary_handler(
            handle_binary
        )

        # Audio input must be raw PCM at 16Khz with 16-bit mono samples
        input_args["stt_metadata"] = stt.SpeechMetadata(
            language=language,
            format=stt.AudioFormats.WAV,
            codec=stt.AudioCodecs.PCM,
            bit_rate=stt.AudioBitRates.BITRATE_16,
            sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
            channel=stt.AudioChannels.CHANNEL_MONO,
        )
        input_args["stt_stream"] = stt_stream()
    elif start_stage == PipelineStage.INTENT:
        # Input to conversation agent
        input_args["intent_input"] = msg["input"]["text"]
    elif start_stage == PipelineStage.TTS:
        # Input to text to speech system
        input_args["tts_input"] = msg["input"]["text"]

    input_args["run"] = PipelineRun(
        hass,
        context=connection.context(msg),
        pipeline=pipeline,
        start_stage=start_stage,
        end_stage=end_stage,
        event_callback=lambda event: connection.send_event(msg["id"], event.as_dict()),
        runner_data={
            "stt_binary_handler_id": handler_id,
            "timeout": timeout,
        },
    )

    pipeline_input = PipelineInput(**input_args)

    try:
        await pipeline_input.validate()
    except PipelineError as error:
        # Report more specific error when possible
        connection.send_error(msg["id"], error.code, error.message)
        return

    # Confirm subscription
    connection.send_result(msg["id"])

    run_task = hass.async_create_task(pipeline_input.execute())

    # Cancel pipeline if user unsubscribes
    connection.subscriptions[msg["id"]] = run_task.cancel

    try:
        # Task contains a timeout
        async with async_timeout.timeout(timeout):
            await run_task
    except asyncio.TimeoutError:
        connection.send_event(
            msg["id"],
            PipelineEvent(
                PipelineEventType.ERROR,
                {"code": "timeout", "message": "Timeout running pipeline"},
            ),
        )
    finally:
        if unregister_handler is not None:
            # Unregister binary handler
            unregister_handler()
