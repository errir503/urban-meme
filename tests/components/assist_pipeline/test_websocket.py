"""Websocket tests for Voice Assistant integration."""
import asyncio
from unittest.mock import ANY, patch

from syrupy.assertion import SnapshotAssertion

from homeassistant.components.assist_pipeline.const import DOMAIN
from homeassistant.components.assist_pipeline.pipeline import Pipeline, PipelineData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import MockWakeWordEntity, MockWakeWordEntity2

from tests.typing import WebSocketGenerator


async def test_text_only_pipeline(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test events from a pipeline run with text input (no STT/TTS)."""
    events = []
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "start_stage": "intent",
            "end_stage": "intent",
            "input": {"text": "Are the lights on?"},
            "conversation_id": "mock-conversation-id",
            "device_id": "mock-device-id",
        }
    )

    # result
    msg = await client.receive_json()
    assert msg["success"]

    # run start
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-start"
    msg["event"]["data"]["pipeline"] = ANY
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # intent
    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # run end
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_id = list(pipeline_data.pipeline_debug)[0]
    pipeline_run_id = list(pipeline_data.pipeline_debug[pipeline_id])[0]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_audio_pipeline(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test events from a pipeline run with audio input/output."""
    events = []
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "start_stage": "stt",
            "end_stage": "tts",
            "input": {
                "sample_rate": 44100,
            },
        }
    )

    # result
    msg = await client.receive_json()
    assert msg["success"]

    # run start
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-start"
    msg["event"]["data"]["pipeline"] = ANY
    assert msg["event"]["data"] == snapshot
    handler_id = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
    events.append(msg["event"])

    # stt
    msg = await client.receive_json()
    assert msg["event"]["type"] == "stt-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # End of audio stream (handler id + empty payload)
    await client.send_bytes(bytes([handler_id]))

    msg = await client.receive_json()
    assert msg["event"]["type"] == "stt-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # intent
    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # text-to-speech
    msg = await client.receive_json()
    assert msg["event"]["type"] == "tts-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    msg = await client.receive_json()
    assert msg["event"]["type"] == "tts-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # run end
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_id = list(pipeline_data.pipeline_debug)[0]
    pipeline_run_id = list(pipeline_data.pipeline_debug[pipeline_id])[0]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_audio_pipeline_with_wake_word_timeout(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test timeout from a pipeline run with audio input/output + wake word."""
    events = []
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "start_stage": "wake_word",
            "end_stage": "tts",
            "input": {
                "sample_rate": 16000,
                "timeout": 1,
            },
        }
    )

    # result
    msg = await client.receive_json()
    assert msg["success"], msg

    # run start
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-start"
    msg["event"]["data"]["pipeline"] = ANY
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # wake_word
    msg = await client.receive_json()
    assert msg["event"]["type"] == "wake_word-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # 2 seconds of silence
    await client.send_bytes(bytes([1]) + bytes(16000 * 2 * 2))

    # Time out error
    msg = await client.receive_json()
    assert msg["event"]["type"] == "error"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # run end
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])


async def test_audio_pipeline_with_wake_word_no_timeout(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test events from a pipeline run with audio input/output + wake word with no timeout."""
    events = []
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "start_stage": "wake_word",
            "end_stage": "tts",
            "input": {
                "sample_rate": 16000,
                "timeout": 0,
                "no_vad": True,
                "no_chunking": True,
            },
        }
    )

    # result
    msg = await client.receive_json()
    assert msg["success"], msg

    # run start
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-start"
    msg["event"]["data"]["pipeline"] = ANY
    assert msg["event"]["data"] == snapshot
    handler_id = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
    events.append(msg["event"])

    # wake_word
    msg = await client.receive_json()
    assert msg["event"]["type"] == "wake_word-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # "audio"
    await client.send_bytes(bytes([handler_id]) + b"wake word")

    msg = await client.receive_json()
    assert msg["event"]["type"] == "wake_word-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # stt
    msg = await client.receive_json()
    assert msg["event"]["type"] == "stt-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # End of audio stream (handler id + empty payload)
    await client.send_bytes(bytes([handler_id]))

    msg = await client.receive_json()
    assert msg["event"]["type"] == "stt-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # intent
    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # text-to-speech
    msg = await client.receive_json()
    assert msg["event"]["type"] == "tts-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    msg = await client.receive_json()
    assert msg["event"]["type"] == "tts-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # run end
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_id = list(pipeline_data.pipeline_debug)[0]
    pipeline_run_id = list(pipeline_data.pipeline_debug[pipeline_id])[0]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_audio_pipeline_no_wake_word_engine(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test timeout from a pipeline run with audio input/output + wake word."""
    client = await hass_ws_client(hass)

    with patch(
        "homeassistant.components.wake_word.async_default_entity", return_value=None
    ):
        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "wake_word",
                "end_stage": "tts",
                "input": {
                    "sample_rate": 16000,
                },
            }
        )

        # error
        msg = await client.receive_json()
        assert not msg["success"]
        assert "error" in msg
        assert msg["error"] == snapshot


async def test_audio_pipeline_no_wake_word_entity(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test timeout from a pipeline run with audio input/output + wake word."""
    client = await hass_ws_client(hass)

    with patch(
        "homeassistant.components.wake_word.async_default_entity",
        return_value="wake_word.bad-entity-id",
    ), patch(
        "homeassistant.components.wake_word.async_get_wake_word_detection_entity",
        return_value=None,
    ):
        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "wake_word",
                "end_stage": "tts",
                "input": {
                    "sample_rate": 16000,
                },
            }
        )

        # error
        msg = await client.receive_json()
        assert not msg["success"]
        assert "error" in msg
        assert msg["error"] == snapshot


async def test_intent_timeout(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test partial pipeline run with conversation agent timeout."""
    events = []
    client = await hass_ws_client(hass)

    async def sleepy_converse(*args, **kwargs):
        await asyncio.sleep(3600)

    with patch(
        "homeassistant.components.conversation.async_converse",
        new=sleepy_converse,
    ):
        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "intent",
                "end_stage": "intent",
                "input": {"text": "Are the lights on?"},
                "timeout": 0.1,
            }
        )

        # result
        msg = await client.receive_json()
        assert msg["success"]

        # run start
        msg = await client.receive_json()
        assert msg["event"]["type"] == "run-start"
        msg["event"]["data"]["pipeline"] = ANY
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

        # intent
        msg = await client.receive_json()
        assert msg["event"]["type"] == "intent-start"
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

        # run-end
        msg = await client.receive_json()
        assert msg["event"]["type"] == "run-end"
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

        # timeout error
        msg = await client.receive_json()
        assert msg["event"]["type"] == "error"
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_id = list(pipeline_data.pipeline_debug)[0]
    pipeline_run_id = list(pipeline_data.pipeline_debug[pipeline_id])[0]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_text_pipeline_timeout(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test text-only pipeline run with immediate timeout."""
    events = []
    client = await hass_ws_client(hass)

    async def sleepy_run(*args, **kwargs):
        await asyncio.sleep(3600)

    with patch(
        "homeassistant.components.assist_pipeline.pipeline.PipelineInput.execute",
        new=sleepy_run,
    ):
        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "intent",
                "end_stage": "intent",
                "input": {"text": "Are the lights on?"},
                "timeout": 0.0001,
            }
        )

        # result
        msg = await client.receive_json()
        assert msg["success"]

        # timeout error
        msg = await client.receive_json()
        assert msg["event"]["type"] == "error"
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_id = list(pipeline_data.pipeline_debug)[0]
    pipeline_run_id = list(pipeline_data.pipeline_debug[pipeline_id])[0]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_intent_failed(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test text-only pipeline run with conversation agent error."""
    events = []
    client = await hass_ws_client(hass)

    with patch(
        "homeassistant.components.conversation.async_converse",
        side_effect=RuntimeError,
    ):
        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "intent",
                "end_stage": "intent",
                "input": {"text": "Are the lights on?"},
            }
        )

        # result
        msg = await client.receive_json()
        assert msg["success"]

        # run start
        msg = await client.receive_json()
        assert msg["event"]["type"] == "run-start"
        msg["event"]["data"]["pipeline"] = ANY
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

        # intent start
        msg = await client.receive_json()
        assert msg["event"]["type"] == "intent-start"
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

        # intent error
        msg = await client.receive_json()
        assert msg["event"]["type"] == "error"
        assert msg["event"]["data"]["code"] == "intent-failed"
        events.append(msg["event"])

        # run end
        msg = await client.receive_json()
        assert msg["event"]["type"] == "run-end"
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_id = list(pipeline_data.pipeline_debug)[0]
    pipeline_run_id = list(pipeline_data.pipeline_debug[pipeline_id])[0]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_audio_pipeline_timeout(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test audio pipeline run with immediate timeout."""
    events = []
    client = await hass_ws_client(hass)

    async def sleepy_run(*args, **kwargs):
        await asyncio.sleep(3600)

    with patch(
        "homeassistant.components.assist_pipeline.pipeline.PipelineInput.execute",
        new=sleepy_run,
    ):
        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "stt",
                "end_stage": "tts",
                "input": {
                    "sample_rate": 44100,
                },
                "timeout": 0.0001,
            }
        )

        # result
        msg = await client.receive_json()
        assert msg["success"]

        # timeout error
        msg = await client.receive_json()
        assert msg["event"]["type"] == "error"
        assert msg["event"]["data"]["code"] == "timeout"
        events.append(msg["event"])

    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_id = list(pipeline_data.pipeline_debug)[0]
    pipeline_run_id = list(pipeline_data.pipeline_debug[pipeline_id])[0]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_stt_provider_missing(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test events from a pipeline run with a non-existent STT provider."""
    with patch(
        "homeassistant.components.stt.async_get_provider",
        return_value=None,
    ):
        client = await hass_ws_client(hass)

        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "stt",
                "end_stage": "tts",
                "input": {
                    "sample_rate": 44100,
                },
            }
        )

        # result
        msg = await client.receive_json()
        assert not msg["success"]
        assert msg["error"]["code"] == "stt-provider-missing"


async def test_stt_provider_bad_metadata(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    mock_stt_provider,
    snapshot: SnapshotAssertion,
) -> None:
    """Test events from a pipeline run with wrong metadata."""
    with patch.object(mock_stt_provider, "check_metadata", return_value=False):
        client = await hass_ws_client(hass)

        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "stt",
                "end_stage": "tts",
                "input": {
                    "sample_rate": 12345,
                },
            }
        )

        # result
        msg = await client.receive_json()
        assert not msg["success"]
        assert msg["error"]["code"] == "stt-provider-unsupported-metadata"


async def test_stt_stream_failed(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test events from a pipeline run with a non-existent STT provider."""
    events = []
    client = await hass_ws_client(hass)

    with patch(
        "tests.components.assist_pipeline.conftest.MockSttProvider.async_process_audio_stream",
        side_effect=RuntimeError,
    ):
        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "stt",
                "end_stage": "tts",
                "input": {
                    "sample_rate": 44100,
                },
            }
        )

        # result
        msg = await client.receive_json()
        assert msg["success"]

        # run start
        msg = await client.receive_json()
        assert msg["event"]["type"] == "run-start"
        msg["event"]["data"]["pipeline"] = ANY
        assert msg["event"]["data"] == snapshot
        handler_id = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
        events.append(msg["event"])

        # stt
        msg = await client.receive_json()
        assert msg["event"]["type"] == "stt-start"
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

        # End of audio stream (handler id + empty payload)
        await client.send_bytes(bytes([handler_id]))

        # stt error
        msg = await client.receive_json()
        assert msg["event"]["type"] == "error"
        assert msg["event"]["data"]["code"] == "stt-stream-failed"
        events.append(msg["event"])

        # run end
        msg = await client.receive_json()
        assert msg["event"]["type"] == "run-end"
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_id = list(pipeline_data.pipeline_debug)[0]
    pipeline_run_id = list(pipeline_data.pipeline_debug[pipeline_id])[0]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_tts_failed(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test pipeline run with text-to-speech error."""
    events = []
    client = await hass_ws_client(hass)

    with patch(
        "homeassistant.components.media_source.async_resolve_media",
        side_effect=RuntimeError,
    ):
        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "tts",
                "end_stage": "tts",
                "input": {"text": "Lights are on."},
            }
        )

        # result
        msg = await client.receive_json()
        assert msg["success"]

        # run start
        msg = await client.receive_json()
        assert msg["event"]["type"] == "run-start"
        msg["event"]["data"]["pipeline"] = ANY
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

        # tts start
        msg = await client.receive_json()
        assert msg["event"]["type"] == "tts-start"
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

        # tts error
        msg = await client.receive_json()
        assert msg["event"]["type"] == "error"
        assert msg["event"]["data"]["code"] == "tts-failed"
        events.append(msg["event"])

        # run end
        msg = await client.receive_json()
        assert msg["event"]["type"] == "run-end"
        assert msg["event"]["data"] == snapshot
        events.append(msg["event"])

    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_id = list(pipeline_data.pipeline_debug)[0]
    pipeline_run_id = list(pipeline_data.pipeline_debug[pipeline_id])[0]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_tts_provider_missing(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    mock_tts_provider,
    snapshot: SnapshotAssertion,
) -> None:
    """Test pipeline run with text-to-speech error."""
    client = await hass_ws_client(hass)

    with patch(
        "homeassistant.components.tts.async_support_options",
        side_effect=HomeAssistantError,
    ):
        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "tts",
                "end_stage": "tts",
                "input": {"text": "Lights are on."},
            }
        )

        # result
        msg = await client.receive_json()
        assert not msg["success"]
        assert msg["error"]["code"] == "tts-not-supported"


async def test_tts_provider_bad_options(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    mock_tts_provider,
    snapshot: SnapshotAssertion,
) -> None:
    """Test pipeline run with text-to-speech error."""
    client = await hass_ws_client(hass)

    with patch(
        "homeassistant.components.tts.async_support_options",
        return_value=False,
    ):
        await client.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "tts",
                "end_stage": "tts",
                "input": {"text": "Lights are on."},
            }
        )

        # result
        msg = await client.receive_json()
        assert not msg["success"]
        assert msg["error"]["code"] == "tts-not-supported"


async def test_invalid_stage_order(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, init_components
) -> None:
    """Test pipeline run with invalid stage order."""
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "start_stage": "tts",
            "end_stage": "stt",
            "input": {"text": "Lights are on."},
        }
    )

    # result
    msg = await client.receive_json()
    assert not msg["success"]


async def test_add_pipeline(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, init_components
) -> None:
    """Test we can add a pipeline."""
    client = await hass_ws_client(hass)
    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_store = pipeline_data.pipeline_store

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "conversation_engine": "test_conversation_engine",
            "conversation_language": "test_language",
            "language": "test_language",
            "name": "test_name",
            "stt_engine": "test_stt_engine",
            "stt_language": "test_language",
            "tts_engine": "test_tts_engine",
            "tts_language": "test_language",
            "tts_voice": "Arnold Schwarzenegger",
            "wake_word_entity": "wakeword_entity_1",
            "wake_word_id": "wakeword_id_1",
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {
        "conversation_engine": "test_conversation_engine",
        "conversation_language": "test_language",
        "id": ANY,
        "language": "test_language",
        "name": "test_name",
        "stt_engine": "test_stt_engine",
        "stt_language": "test_language",
        "tts_engine": "test_tts_engine",
        "tts_language": "test_language",
        "tts_voice": "Arnold Schwarzenegger",
        "wake_word_entity": "wakeword_entity_1",
        "wake_word_id": "wakeword_id_1",
    }

    assert len(pipeline_store.data) == 2
    pipeline = pipeline_store.data[msg["result"]["id"]]
    assert pipeline == Pipeline(
        conversation_engine="test_conversation_engine",
        conversation_language="test_language",
        id=msg["result"]["id"],
        language="test_language",
        name="test_name",
        stt_engine="test_stt_engine",
        stt_language="test_language",
        tts_engine="test_tts_engine",
        tts_language="test_language",
        tts_voice="Arnold Schwarzenegger",
        wake_word_entity="wakeword_entity_1",
        wake_word_id="wakeword_id_1",
    )

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "language": "test_language",
            "name": "test_name",
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]


async def test_add_pipeline_missing_language(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, init_components
) -> None:
    """Test we can't add a pipeline without specifying stt or tts language."""
    client = await hass_ws_client(hass)
    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_store = pipeline_data.pipeline_store
    assert len(pipeline_store.data) == 1

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "conversation_engine": "test_conversation_engine",
            "conversation_language": "test_language",
            "language": "test_language",
            "name": "test_name",
            "stt_engine": "test_stt_engine",
            "stt_language": None,
            "tts_engine": "test_tts_engine",
            "tts_language": "test_language",
            "tts_voice": "Arnold Schwarzenegger",
            "wake_word_entity": "wakeword_entity_1",
            "wake_word_id": "wakeword_id_1",
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert len(pipeline_store.data) == 1

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "conversation_engine": "test_conversation_engine",
            "conversation_language": "test_language",
            "language": "test_language",
            "name": "test_name",
            "stt_engine": "test_stt_engine",
            "stt_language": "test_language",
            "tts_engine": "test_tts_engine",
            "tts_language": None,
            "tts_voice": "Arnold Schwarzenegger",
            "wake_word_entity": "wakeword_entity_1",
            "wake_word_id": "wakeword_id_1",
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert len(pipeline_store.data) == 1


async def test_delete_pipeline(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, init_components
) -> None:
    """Test we can delete a pipeline."""
    client = await hass_ws_client(hass)
    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_store = pipeline_data.pipeline_store

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "conversation_engine": "test_conversation_engine",
            "conversation_language": "test_language",
            "language": "test_language",
            "name": "test_name",
            "stt_engine": "test_stt_engine",
            "stt_language": "test_language",
            "tts_engine": "test_tts_engine",
            "tts_language": "test_language",
            "tts_voice": "Arnold Schwarzenegger",
            "wake_word_entity": "wakeword_entity_1",
            "wake_word_id": "wakeword_id_1",
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    pipeline_id_1 = msg["result"]["id"]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "conversation_engine": "test_conversation_engine",
            "conversation_language": "test_language",
            "language": "test_language",
            "name": "test_name",
            "stt_engine": "test_stt_engine",
            "stt_language": "test_language",
            "tts_engine": "test_tts_engine",
            "tts_language": "test_language",
            "tts_voice": "Arnold Schwarzenegger",
            "wake_word_entity": "wakeword_entity_2",
            "wake_word_id": "wakeword_id_2",
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    pipeline_id_2 = msg["result"]["id"]

    assert len(pipeline_store.data) == 3

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/set_preferred",
            "pipeline_id": pipeline_id_1,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/delete",
            "pipeline_id": pipeline_id_1,
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"] == {
        "code": "not_allowed",
        "message": f"Item {pipeline_id_1} preferred.",
    }

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/delete",
            "pipeline_id": pipeline_id_2,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert len(pipeline_store.data) == 2

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/delete",
            "pipeline_id": pipeline_id_2,
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"] == {
        "code": "not_found",
        "message": f"Unable to find pipeline_id {pipeline_id_2}",
    }


async def test_get_pipeline(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, init_components
) -> None:
    """Test we can get a pipeline."""
    client = await hass_ws_client(hass)
    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_store = pipeline_data.pipeline_store

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/get",
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {
        "conversation_engine": "homeassistant",
        "conversation_language": "en",
        "id": ANY,
        "language": "en",
        "name": "Home Assistant",
        "stt_engine": "test",
        "stt_language": "en-US",
        "tts_engine": "test",
        "tts_language": "en-US",
        "tts_voice": "james_earl_jones",
        "wake_word_entity": None,
        "wake_word_id": None,
    }

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/get",
            "pipeline_id": "no_such_pipeline",
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"] == {
        "code": "not_found",
        "message": "Unable to find pipeline_id no_such_pipeline",
    }

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "conversation_engine": "test_conversation_engine",
            "conversation_language": "test_language",
            "language": "test_language",
            "name": "test_name",
            "stt_engine": "test_stt_engine",
            "stt_language": "test_language",
            "tts_engine": "test_tts_engine",
            "tts_language": "test_language",
            "tts_voice": "Arnold Schwarzenegger",
            "wake_word_entity": "wakeword_entity_1",
            "wake_word_id": "wakeword_id_1",
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    pipeline_id = msg["result"]["id"]
    assert len(pipeline_store.data) == 2

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/get",
            "pipeline_id": pipeline_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {
        "conversation_engine": "test_conversation_engine",
        "conversation_language": "test_language",
        "id": pipeline_id,
        "language": "test_language",
        "name": "test_name",
        "stt_engine": "test_stt_engine",
        "stt_language": "test_language",
        "tts_engine": "test_tts_engine",
        "tts_language": "test_language",
        "tts_voice": "Arnold Schwarzenegger",
        "wake_word_entity": "wakeword_entity_1",
        "wake_word_id": "wakeword_id_1",
    }


async def test_list_pipelines(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, init_components
) -> None:
    """Test we can list pipelines."""
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "assist_pipeline/pipeline/list"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {
        "pipelines": [
            {
                "conversation_engine": "homeassistant",
                "conversation_language": "en",
                "id": ANY,
                "language": "en",
                "name": "Home Assistant",
                "stt_engine": "test",
                "stt_language": "en-US",
                "tts_engine": "test",
                "tts_language": "en-US",
                "tts_voice": "james_earl_jones",
                "wake_word_entity": None,
                "wake_word_id": None,
            }
        ],
        "preferred_pipeline": ANY,
    }


async def test_update_pipeline(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, init_components
) -> None:
    """Test we can list pipelines."""
    client = await hass_ws_client(hass)
    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_store = pipeline_data.pipeline_store

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/update",
            "conversation_engine": "new_conversation_engine",
            "conversation_language": "new_conversation_language",
            "language": "new_language",
            "name": "new_name",
            "pipeline_id": "no_such_pipeline",
            "stt_engine": "new_stt_engine",
            "stt_language": "new_stt_language",
            "tts_engine": "new_tts_engine",
            "tts_language": "new_tts_language",
            "tts_voice": "new_tts_voice",
            "wake_word_entity": "new_wakeword_entity",
            "wake_word_id": "new_wakeword_id",
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"] == {
        "code": "not_found",
        "message": "Unable to find pipeline_id no_such_pipeline",
    }

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "conversation_engine": "test_conversation_engine",
            "conversation_language": "test_language",
            "language": "test_language",
            "name": "test_name",
            "stt_engine": "test_stt_engine",
            "stt_language": "test_language",
            "tts_engine": "test_tts_engine",
            "tts_language": "test_language",
            "tts_voice": "Arnold Schwarzenegger",
            "wake_word_entity": "wakeword_entity_1",
            "wake_word_id": "wakeword_id_1",
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    pipeline_id = msg["result"]["id"]
    assert len(pipeline_store.data) == 2

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/update",
            "conversation_engine": "new_conversation_engine",
            "conversation_language": "new_conversation_language",
            "language": "new_language",
            "name": "new_name",
            "pipeline_id": pipeline_id,
            "stt_engine": "new_stt_engine",
            "stt_language": "new_stt_language",
            "tts_engine": "new_tts_engine",
            "tts_language": "new_tts_language",
            "tts_voice": "new_tts_voice",
            "wake_word_entity": "new_wakeword_entity",
            "wake_word_id": "new_wakeword_id",
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {
        "conversation_engine": "new_conversation_engine",
        "conversation_language": "new_conversation_language",
        "id": pipeline_id,
        "language": "new_language",
        "name": "new_name",
        "stt_engine": "new_stt_engine",
        "stt_language": "new_stt_language",
        "tts_engine": "new_tts_engine",
        "tts_language": "new_tts_language",
        "tts_voice": "new_tts_voice",
        "wake_word_entity": "new_wakeword_entity",
        "wake_word_id": "new_wakeword_id",
    }

    assert len(pipeline_store.data) == 2
    pipeline = pipeline_store.data[pipeline_id]
    assert pipeline == Pipeline(
        conversation_engine="new_conversation_engine",
        conversation_language="new_conversation_language",
        id=pipeline_id,
        language="new_language",
        name="new_name",
        stt_engine="new_stt_engine",
        stt_language="new_stt_language",
        tts_engine="new_tts_engine",
        tts_language="new_tts_language",
        tts_voice="new_tts_voice",
        wake_word_entity="new_wakeword_entity",
        wake_word_id="new_wakeword_id",
    )

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/update",
            "conversation_engine": "new_conversation_engine",
            "conversation_language": "new_conversation_language",
            "language": "new_language",
            "name": "new_name",
            "pipeline_id": pipeline_id,
            "stt_engine": None,
            "stt_language": None,
            "tts_engine": None,
            "tts_language": None,
            "tts_voice": None,
            "wake_word_entity": None,
            "wake_word_id": None,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {
        "conversation_engine": "new_conversation_engine",
        "conversation_language": "new_conversation_language",
        "id": pipeline_id,
        "language": "new_language",
        "name": "new_name",
        "stt_engine": None,
        "stt_language": None,
        "tts_engine": None,
        "tts_language": None,
        "tts_voice": None,
        "wake_word_entity": None,
        "wake_word_id": None,
    }

    pipeline = pipeline_store.data[pipeline_id]
    assert pipeline == Pipeline(
        conversation_engine="new_conversation_engine",
        conversation_language="new_conversation_language",
        id=pipeline_id,
        language="new_language",
        name="new_name",
        stt_engine=None,
        stt_language=None,
        tts_engine=None,
        tts_language=None,
        tts_voice=None,
        wake_word_entity=None,
        wake_word_id=None,
    )


async def test_set_preferred_pipeline(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, init_components
) -> None:
    """Test updating the preferred pipeline."""
    client = await hass_ws_client(hass)
    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_store = pipeline_data.pipeline_store

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "conversation_engine": "test_conversation_engine",
            "conversation_language": "test_language",
            "language": "test_language",
            "name": "test_name",
            "stt_engine": "test_stt_engine",
            "stt_language": "test_language",
            "tts_engine": "test_tts_engine",
            "tts_language": "test_language",
            "tts_voice": "Arnold Schwarzenegger",
            "wake_word_entity": "wakeword_entity_1",
            "wake_word_id": "wakeword_id_1",
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    pipeline_id_1 = msg["result"]["id"]

    assert pipeline_store.async_get_preferred_item() != pipeline_id_1

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/set_preferred",
            "pipeline_id": pipeline_id_1,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]

    assert pipeline_store.async_get_preferred_item() == pipeline_id_1


async def test_set_preferred_pipeline_wrong_id(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, init_components
) -> None:
    """Test updating the preferred pipeline."""
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": "assist_pipeline/pipeline/set_preferred", "pipeline_id": "don_t_exist"}
    )
    msg = await client.receive_json()
    assert msg["error"]["code"] == "not_found"


async def test_audio_pipeline_debug(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test debug listing events from a pipeline run with audio input/output."""
    events = []
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "start_stage": "stt",
            "end_stage": "tts",
            "input": {
                "sample_rate": 44100,
            },
        }
    )

    # result
    msg = await client.receive_json()
    assert msg["success"]

    # run start
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-start"
    msg["event"]["data"]["pipeline"] = ANY
    assert msg["event"]["data"] == snapshot
    handler_id = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
    events.append(msg["event"])

    # stt
    msg = await client.receive_json()
    assert msg["event"]["type"] == "stt-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # End of audio stream (handler id + empty payload)
    await client.send_bytes(bytes([handler_id]))

    msg = await client.receive_json()
    assert msg["event"]["type"] == "stt-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # intent
    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # text-to-speech
    msg = await client.receive_json()
    assert msg["event"]["type"] == "tts-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    msg = await client.receive_json()
    assert msg["event"]["type"] == "tts-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # run end
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # Get the id of the pipeline
    await client.send_json_auto_id({"type": "assist_pipeline/pipeline/list"})
    msg = await client.receive_json()
    assert msg["success"]
    assert len(msg["result"]["pipelines"]) == 1

    pipeline_id = msg["result"]["pipelines"][0]["id"]

    # Get the id for the run
    await client.send_json_auto_id(
        {"type": "assist_pipeline/pipeline_debug/list", "pipeline_id": pipeline_id}
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"pipeline_runs": [ANY]}

    pipeline_run_id = msg["result"]["pipeline_runs"][0]["pipeline_run_id"]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_pipeline_debug_list_runs_wrong_pipeline(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
) -> None:
    """Test debug listing events from a pipeline."""
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": "assist_pipeline/pipeline_debug/list", "pipeline_id": "blah"}
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"pipeline_runs": []}


async def test_pipeline_debug_get_run_wrong_pipeline(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
) -> None:
    """Test debug listing events from a pipeline."""
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": "blah",
            "pipeline_run_id": "blah",
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"] == {
        "code": "not_found",
        "message": "pipeline_id blah not found",
    }


async def test_pipeline_debug_get_run_wrong_pipeline_run(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
) -> None:
    """Test debug listing events from a pipeline."""
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "start_stage": "intent",
            "end_stage": "intent",
            "input": {"text": "Are the lights on?"},
        }
    )

    # result
    msg = await client.receive_json()
    assert msg["success"]

    # consume events
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-start"

    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-start"

    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-end"

    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-end"

    # Get the id of the pipeline
    await client.send_json_auto_id({"type": "assist_pipeline/pipeline/list"})
    msg = await client.receive_json()
    assert msg["success"]
    assert len(msg["result"]["pipelines"]) == 1
    pipeline_id = msg["result"]["pipelines"][0]["id"]

    # get debug data for the wrong run
    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": "blah",
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"] == {
        "code": "not_found",
        "message": "pipeline_run_id blah not found",
    }


async def test_list_pipeline_languages(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
) -> None:
    """Test listing pipeline languages."""
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "assist_pipeline/language/list"})

    # result
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"languages": ["en"]}


async def test_list_pipeline_languages_with_aliases(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
) -> None:
    """Test listing pipeline languages using aliases."""
    client = await hass_ws_client(hass)

    with patch(
        "homeassistant.components.conversation.async_get_conversation_languages",
        return_value={"he", "nb"},
    ), patch(
        "homeassistant.components.stt.async_get_speech_to_text_languages",
        return_value={"he", "no"},
    ), patch(
        "homeassistant.components.tts.async_get_text_to_speech_languages",
        return_value={"iw", "nb"},
    ):
        await client.send_json_auto_id({"type": "assist_pipeline/language/list"})

        # result
        msg = await client.receive_json()
        assert msg["success"]
        assert msg["result"] == {"languages": ["he", "nb"]}


async def test_audio_pipeline_with_enhancements(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_components,
    snapshot: SnapshotAssertion,
) -> None:
    """Test events from a pipeline run with audio input/output."""
    events = []
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "start_stage": "stt",
            "end_stage": "tts",
            "input": {
                "sample_rate": 16000,
                # Enhancements
                "noise_suppression_level": 2,
                "auto_gain_dbfs": 15,
                "volume_multiplier": 2.0,
            },
        }
    )

    # result
    msg = await client.receive_json()
    assert msg["success"]

    # run start
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-start"
    msg["event"]["data"]["pipeline"] = ANY
    assert msg["event"]["data"] == snapshot
    handler_id = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
    events.append(msg["event"])

    # stt
    msg = await client.receive_json()
    assert msg["event"]["type"] == "stt-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # One second of silence.
    # This will pass through the audio enhancement pipeline, but we don't test
    # the actual output.
    await client.send_bytes(bytes([handler_id]) + bytes(16000 * 2))

    # End of audio stream (handler id + empty payload)
    await client.send_bytes(bytes([handler_id]))

    msg = await client.receive_json()
    assert msg["event"]["type"] == "stt-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # intent
    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    msg = await client.receive_json()
    assert msg["event"]["type"] == "intent-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # text-to-speech
    msg = await client.receive_json()
    assert msg["event"]["type"] == "tts-start"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    msg = await client.receive_json()
    assert msg["event"]["type"] == "tts-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    # run end
    msg = await client.receive_json()
    assert msg["event"]["type"] == "run-end"
    assert msg["event"]["data"] == snapshot
    events.append(msg["event"])

    pipeline_data: PipelineData = hass.data[DOMAIN]
    pipeline_id = list(pipeline_data.pipeline_debug)[0]
    pipeline_run_id = list(pipeline_data.pipeline_debug[pipeline_id])[0]

    await client.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline_debug/get",
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"] == {"events": events}


async def test_wake_word_cooldown_same_id(
    hass: HomeAssistant,
    init_components,
    mock_wake_word_provider_entity: MockWakeWordEntity,
    hass_ws_client: WebSocketGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """Test that duplicate wake word detections with the same id are blocked during the cooldown period."""
    client_1 = await hass_ws_client(hass)
    client_2 = await hass_ws_client(hass)

    await client_1.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "start_stage": "wake_word",
            "end_stage": "tts",
            "input": {
                "sample_rate": 16000,
                "no_vad": True,
                "no_chunking": True,
            },
        }
    )

    await client_2.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "start_stage": "wake_word",
            "end_stage": "tts",
            "input": {
                "sample_rate": 16000,
                "no_vad": True,
                "no_chunking": True,
            },
        }
    )

    # result
    msg = await client_1.receive_json()
    assert msg["success"], msg

    msg = await client_2.receive_json()
    assert msg["success"], msg

    # run start
    msg = await client_1.receive_json()
    assert msg["event"]["type"] == "run-start"
    msg["event"]["data"]["pipeline"] = ANY
    handler_id_1 = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
    assert msg["event"]["data"] == snapshot

    msg = await client_2.receive_json()
    assert msg["event"]["type"] == "run-start"
    msg["event"]["data"]["pipeline"] = ANY
    handler_id_2 = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
    assert msg["event"]["data"] == snapshot

    # wake_word
    msg = await client_1.receive_json()
    assert msg["event"]["type"] == "wake_word-start"
    assert msg["event"]["data"] == snapshot

    msg = await client_2.receive_json()
    assert msg["event"]["type"] == "wake_word-start"
    assert msg["event"]["data"] == snapshot

    # Wake both up at the same time
    await client_1.send_bytes(bytes([handler_id_1]) + b"wake word")
    await client_2.send_bytes(bytes([handler_id_2]) + b"wake word")

    # Get response events
    msg = await client_1.receive_json()
    event_type_1 = msg["event"]["type"]

    msg = await client_2.receive_json()
    event_type_2 = msg["event"]["type"]

    # One should be a wake up, one should be an error
    assert {event_type_1, event_type_2} == {"wake_word-end", "error"}


async def test_wake_word_cooldown_different_ids(
    hass: HomeAssistant,
    init_components,
    mock_wake_word_provider_entity: MockWakeWordEntity,
    hass_ws_client: WebSocketGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """Test that duplicate wake word detections are allowed with different ids."""
    with patch.object(mock_wake_word_provider_entity, "alternate_detections", True):
        client_1 = await hass_ws_client(hass)
        client_2 = await hass_ws_client(hass)

        await client_1.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "wake_word",
                "end_stage": "tts",
                "input": {
                    "sample_rate": 16000,
                    "no_vad": True,
                    "no_chunking": True,
                },
            }
        )

        await client_2.send_json_auto_id(
            {
                "type": "assist_pipeline/run",
                "start_stage": "wake_word",
                "end_stage": "tts",
                "input": {
                    "sample_rate": 16000,
                    "no_vad": True,
                    "no_chunking": True,
                },
            }
        )

        # result
        msg = await client_1.receive_json()
        assert msg["success"], msg

        msg = await client_2.receive_json()
        assert msg["success"], msg

        # run start
        msg = await client_1.receive_json()
        assert msg["event"]["type"] == "run-start"
        msg["event"]["data"]["pipeline"] = ANY
        handler_id_1 = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
        assert msg["event"]["data"] == snapshot

        msg = await client_2.receive_json()
        assert msg["event"]["type"] == "run-start"
        msg["event"]["data"]["pipeline"] = ANY
        handler_id_2 = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
        assert msg["event"]["data"] == snapshot

        # wake_word
        msg = await client_1.receive_json()
        assert msg["event"]["type"] == "wake_word-start"
        assert msg["event"]["data"] == snapshot

        msg = await client_2.receive_json()
        assert msg["event"]["type"] == "wake_word-start"
        assert msg["event"]["data"] == snapshot

        # Wake both up at the same time, but they will have different wake word ids
        await client_1.send_bytes(bytes([handler_id_1]) + b"wake word")
        await client_2.send_bytes(bytes([handler_id_2]) + b"wake word")

        # Get response events
        msg = await client_1.receive_json()
        event_type_1 = msg["event"]["type"]
        assert msg["event"]["data"] == snapshot

        msg = await client_2.receive_json()
        event_type_2 = msg["event"]["type"]
        assert msg["event"]["data"] == snapshot

        # Both should wake up now
        assert {event_type_1, event_type_2} == {"wake_word-end"}


async def test_wake_word_cooldown_different_entities(
    hass: HomeAssistant,
    init_components,
    mock_wake_word_provider_entity: MockWakeWordEntity,
    mock_wake_word_provider_entity2: MockWakeWordEntity2,
    hass_ws_client: WebSocketGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """Test that duplicate wake word detections are allowed with different entities."""
    client_pipeline = await hass_ws_client(hass)
    await client_pipeline.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "conversation_engine": "homeassistant",
            "conversation_language": "en-US",
            "language": "en",
            "name": "pipeline_with_wake_word_1",
            "stt_engine": "test",
            "stt_language": "en-US",
            "tts_engine": "test",
            "tts_language": "en-US",
            "tts_voice": "Arnold Schwarzenegger",
            "wake_word_entity": mock_wake_word_provider_entity.entity_id,
            "wake_word_id": "test_ww",
        }
    )
    msg = await client_pipeline.receive_json()
    assert msg["success"]
    pipeline_id_1 = msg["result"]["id"]

    await client_pipeline.send_json_auto_id(
        {
            "type": "assist_pipeline/pipeline/create",
            "conversation_engine": "homeassistant",
            "conversation_language": "en-US",
            "language": "en",
            "name": "pipeline_with_wake_word_2",
            "stt_engine": "test",
            "stt_language": "en-US",
            "tts_engine": "test",
            "tts_language": "en-US",
            "tts_voice": "Arnold Schwarzenegger",
            "wake_word_entity": mock_wake_word_provider_entity2.entity_id,
            "wake_word_id": "test_ww",
        }
    )
    msg = await client_pipeline.receive_json()
    assert msg["success"]
    pipeline_id_2 = msg["result"]["id"]

    # Wake word clients
    client_1 = await hass_ws_client(hass)
    client_2 = await hass_ws_client(hass)

    await client_1.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "pipeline": pipeline_id_1,
            "start_stage": "wake_word",
            "end_stage": "tts",
            "input": {
                "sample_rate": 16000,
                "no_vad": True,
                "no_chunking": True,
            },
        }
    )

    # Use different wake word entity
    await client_2.send_json_auto_id(
        {
            "type": "assist_pipeline/run",
            "pipeline": pipeline_id_2,
            "start_stage": "wake_word",
            "end_stage": "tts",
            "input": {
                "sample_rate": 16000,
                "no_vad": True,
                "no_chunking": True,
            },
        }
    )

    # result
    msg = await client_1.receive_json()
    assert msg["success"], msg

    msg = await client_2.receive_json()
    assert msg["success"], msg

    # run start
    msg = await client_1.receive_json()
    assert msg["event"]["type"] == "run-start"
    msg["event"]["data"]["pipeline"] = ANY
    handler_id_1 = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
    assert msg["event"]["data"] == snapshot

    msg = await client_2.receive_json()
    assert msg["event"]["type"] == "run-start"
    msg["event"]["data"]["pipeline"] = ANY
    handler_id_2 = msg["event"]["data"]["runner_data"]["stt_binary_handler_id"]
    assert msg["event"]["data"] == snapshot

    # wake_word
    msg = await client_1.receive_json()
    assert msg["event"]["type"] == "wake_word-start"
    assert msg["event"]["data"] == snapshot

    msg = await client_2.receive_json()
    assert msg["event"]["type"] == "wake_word-start"
    assert msg["event"]["data"] == snapshot

    # Wake both up at the same time.
    # They will have the same wake word id, but different entities.
    await client_1.send_bytes(bytes([handler_id_1]) + b"wake word")
    await client_2.send_bytes(bytes([handler_id_2]) + b"wake word")

    # Get response events
    msg = await client_1.receive_json()
    assert msg["event"]["type"] == "wake_word-end", msg
    ww_id_1 = msg["event"]["data"]["wake_word_output"]["wake_word_id"]
    assert msg["event"]["data"] == snapshot

    msg = await client_2.receive_json()
    assert msg["event"]["type"] == "wake_word-end", msg
    ww_id_2 = msg["event"]["data"]["wake_word_output"]["wake_word_id"]
    assert msg["event"]["data"] == snapshot

    # Wake words should be the same
    assert ww_id_1 == ww_id_2
