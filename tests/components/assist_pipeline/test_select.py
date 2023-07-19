"""Test select entity."""

from __future__ import annotations

import pytest

from homeassistant.components.assist_pipeline import Pipeline
from homeassistant.components.assist_pipeline.pipeline import (
    PipelineData,
    PipelineStorageCollection,
)
from homeassistant.components.assist_pipeline.select import (
    AssistPipelineSelect,
    VadSensitivitySelect,
)
from homeassistant.components.assist_pipeline.vad import VadSensitivity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from tests.common import MockConfigEntry, MockPlatform, mock_entity_platform


class SelectPlatform(MockPlatform):
    """Fake select platform."""

    # pylint: disable=method-hidden
    async def async_setup_entry(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        """Set up fake select platform."""
        pipeline_entity = AssistPipelineSelect(hass, "test")
        pipeline_entity._attr_device_info = DeviceInfo(
            identifiers={("test", "test")},
        )
        sensitivity_entity = VadSensitivitySelect(hass, "test")
        sensitivity_entity._attr_device_info = DeviceInfo(
            identifiers={("test", "test")},
        )
        async_add_entities([pipeline_entity, sensitivity_entity])


@pytest.fixture
async def init_select(hass: HomeAssistant, init_components) -> ConfigEntry:
    """Initialize select entity."""
    mock_entity_platform(hass, "select.assist_pipeline", SelectPlatform())
    config_entry = MockConfigEntry(domain="assist_pipeline")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_forward_entry_setup(config_entry, "select")
    return config_entry


@pytest.fixture
async def pipeline_1(
    hass: HomeAssistant, init_select, pipeline_storage: PipelineStorageCollection
) -> Pipeline:
    """Create a pipeline."""
    return await pipeline_storage.async_create_item(
        {
            "name": "Test 1",
            "language": "en-US",
            "conversation_engine": None,
            "conversation_language": "en-US",
            "tts_engine": None,
            "tts_language": None,
            "tts_voice": None,
            "stt_engine": None,
            "stt_language": None,
        }
    )


@pytest.fixture
async def pipeline_2(
    hass: HomeAssistant, init_select, pipeline_storage: PipelineStorageCollection
) -> Pipeline:
    """Create a pipeline."""
    return await pipeline_storage.async_create_item(
        {
            "name": "Test 2",
            "language": "en-US",
            "conversation_engine": None,
            "conversation_language": "en-US",
            "tts_engine": None,
            "tts_language": None,
            "tts_voice": None,
            "stt_engine": None,
            "stt_language": None,
        }
    )


async def test_select_entity_registering_device(
    hass: HomeAssistant,
    init_select: ConfigEntry,
    pipeline_data: PipelineData,
) -> None:
    """Test entity registering as an assist device."""
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={("test", "test")})
    assert device is not None

    # Test device is registered
    assert pipeline_data.pipeline_devices == {device.id}

    await hass.config_entries.async_remove(init_select.entry_id)
    await hass.async_block_till_done()

    # Test device is removed
    assert pipeline_data.pipeline_devices == set()


async def test_select_entity_changing_pipelines(
    hass: HomeAssistant,
    init_select: ConfigEntry,
    pipeline_1: Pipeline,
    pipeline_2: Pipeline,
    pipeline_storage: PipelineStorageCollection,
) -> None:
    """Test entity tracking pipeline changes."""
    config_entry = init_select  # nicer naming

    state = hass.states.get("select.assist_pipeline_test_pipeline")
    assert state is not None
    assert state.state == "preferred"
    assert state.attributes["options"] == [
        "preferred",
        "Home Assistant",
        pipeline_1.name,
        pipeline_2.name,
    ]

    # Change select to new pipeline
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": "select.assist_pipeline_test_pipeline",
            "option": pipeline_2.name,
        },
        blocking=True,
    )

    state = hass.states.get("select.assist_pipeline_test_pipeline")
    assert state is not None
    assert state.state == pipeline_2.name

    # Reload config entry to test selected option persists
    assert await hass.config_entries.async_forward_entry_unload(config_entry, "select")
    assert await hass.config_entries.async_forward_entry_setup(config_entry, "select")

    state = hass.states.get("select.assist_pipeline_test_pipeline")
    assert state is not None
    assert state.state == pipeline_2.name

    # Remove selected pipeline
    await pipeline_storage.async_delete_item(pipeline_2.id)

    state = hass.states.get("select.assist_pipeline_test_pipeline")
    assert state is not None
    assert state.state == "preferred"
    assert state.attributes["options"] == [
        "preferred",
        "Home Assistant",
        pipeline_1.name,
    ]


async def test_select_entity_changing_vad_sensitivity(
    hass: HomeAssistant,
    init_select: ConfigEntry,
) -> None:
    """Test entity tracking pipeline changes."""
    config_entry = init_select  # nicer naming

    state = hass.states.get("select.assist_pipeline_test_vad_sensitivity")
    assert state is not None
    assert state.state == VadSensitivity.DEFAULT.value

    # Change select to new pipeline
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": "select.assist_pipeline_test_vad_sensitivity",
            "option": VadSensitivity.AGGRESSIVE.value,
        },
        blocking=True,
    )

    state = hass.states.get("select.assist_pipeline_test_vad_sensitivity")
    assert state is not None
    assert state.state == VadSensitivity.AGGRESSIVE.value

    # Reload config entry to test selected option persists
    assert await hass.config_entries.async_forward_entry_unload(config_entry, "select")
    assert await hass.config_entries.async_forward_entry_setup(config_entry, "select")

    state = hass.states.get("select.assist_pipeline_test_vad_sensitivity")
    assert state is not None
    assert state.state == VadSensitivity.AGGRESSIVE.value
