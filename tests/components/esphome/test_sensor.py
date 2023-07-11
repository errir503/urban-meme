"""Test ESPHome sensors."""
import math

from aioesphomeapi import (
    APIClient,
    EntityCategory as ESPHomeEntityCategory,
    LastResetType,
    SensorInfo,
    SensorState,
    SensorStateClass as ESPHomeSensorStateClass,
    TextSensorInfo,
    TextSensorState,
)

from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.const import ATTR_ICON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory


async def test_generic_numeric_sensor(
    hass: HomeAssistant,
    mock_client: APIClient,
    mock_generic_device_entry,
) -> None:
    """Test a generic sensor entity."""
    entity_info = [
        SensorInfo(
            object_id="mysensor",
            key=1,
            name="my sensor",
            unique_id="my_sensor",
        )
    ]
    states = [SensorState(key=1, state=50)]
    user_service = []
    await mock_generic_device_entry(
        mock_client=mock_client,
        entity_info=entity_info,
        user_service=user_service,
        states=states,
    )
    state = hass.states.get("sensor.test_mysensor")
    assert state is not None
    assert state.state == "50"


async def test_generic_numeric_sensor_with_entity_category_and_icon(
    hass: HomeAssistant,
    mock_client: APIClient,
    mock_generic_device_entry,
) -> None:
    """Test a generic sensor entity."""
    entity_info = [
        SensorInfo(
            object_id="mysensor",
            key=1,
            name="my sensor",
            unique_id="my_sensor",
            entity_category=ESPHomeEntityCategory.CONFIG,
            icon="mdi:leaf",
        )
    ]
    states = [SensorState(key=1, state=50)]
    user_service = []
    await mock_generic_device_entry(
        mock_client=mock_client,
        entity_info=entity_info,
        user_service=user_service,
        states=states,
    )
    state = hass.states.get("sensor.test_mysensor")
    assert state is not None
    assert state.state == "50"
    assert state.attributes[ATTR_ICON] == "mdi:leaf"
    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get("sensor.test_mysensor")
    assert entry is not None
    assert entry.unique_id == "my_sensor"
    assert entry.entity_category is EntityCategory.CONFIG


async def test_generic_numeric_sensor_state_class_measurement(
    hass: HomeAssistant,
    mock_client: APIClient,
    mock_generic_device_entry,
) -> None:
    """Test a generic sensor entity."""
    entity_info = [
        SensorInfo(
            object_id="mysensor",
            key=1,
            name="my sensor",
            unique_id="my_sensor",
            state_class=ESPHomeSensorStateClass.MEASUREMENT,
            device_class="power",
            unit_of_measurement="W",
        )
    ]
    states = [SensorState(key=1, state=50)]
    user_service = []
    await mock_generic_device_entry(
        mock_client=mock_client,
        entity_info=entity_info,
        user_service=user_service,
        states=states,
    )
    state = hass.states.get("sensor.test_mysensor")
    assert state is not None
    assert state.state == "50"
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.MEASUREMENT
    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get("sensor.test_mysensor")
    assert entry is not None
    assert entry.unique_id == "my_sensor"
    assert entry.entity_category is None


async def test_generic_numeric_sensor_device_class_timestamp(
    hass: HomeAssistant,
    mock_client: APIClient,
    mock_generic_device_entry,
) -> None:
    """Test a sensor entity that uses timestamp (epoch)."""
    entity_info = [
        SensorInfo(
            object_id="mysensor",
            key=1,
            name="my sensor",
            unique_id="my_sensor",
            device_class="timestamp",
        )
    ]
    states = [SensorState(key=1, state=1687459432.466624)]
    user_service = []
    await mock_generic_device_entry(
        mock_client=mock_client,
        entity_info=entity_info,
        user_service=user_service,
        states=states,
    )
    state = hass.states.get("sensor.test_mysensor")
    assert state is not None
    assert state.state == "2023-06-22T18:43:52+00:00"


async def test_generic_numeric_sensor_legacy_last_reset_convert(
    hass: HomeAssistant,
    mock_client: APIClient,
    mock_generic_device_entry,
) -> None:
    """Test a state class of measurement with last reset type of auto is converted to total increasing."""
    entity_info = [
        SensorInfo(
            object_id="mysensor",
            key=1,
            name="my sensor",
            unique_id="my_sensor",
            last_reset_type=LastResetType.AUTO,
            state_class=ESPHomeSensorStateClass.MEASUREMENT,
        )
    ]
    states = [SensorState(key=1, state=50)]
    user_service = []
    await mock_generic_device_entry(
        mock_client=mock_client,
        entity_info=entity_info,
        user_service=user_service,
        states=states,
    )
    state = hass.states.get("sensor.test_mysensor")
    assert state is not None
    assert state.state == "50"
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL_INCREASING


async def test_generic_numeric_sensor_no_state(
    hass: HomeAssistant, mock_client: APIClient, mock_generic_device_entry
) -> None:
    """Test a generic numeric sensor that has no state."""
    entity_info = [
        SensorInfo(
            object_id="mysensor",
            key=1,
            name="my sensor",
            unique_id="my_sensor",
        )
    ]
    states = []
    user_service = []
    await mock_generic_device_entry(
        mock_client=mock_client,
        entity_info=entity_info,
        user_service=user_service,
        states=states,
    )
    state = hass.states.get("sensor.test_mysensor")
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_generic_numeric_sensor_nan_state(
    hass: HomeAssistant, mock_client: APIClient, mock_generic_device_entry
) -> None:
    """Test a generic numeric sensor that has nan state."""
    entity_info = [
        SensorInfo(
            object_id="mysensor",
            key=1,
            name="my sensor",
            unique_id="my_sensor",
        )
    ]
    states = [SensorState(key=1, state=math.nan, missing_state=False)]
    user_service = []
    await mock_generic_device_entry(
        mock_client=mock_client,
        entity_info=entity_info,
        user_service=user_service,
        states=states,
    )
    state = hass.states.get("sensor.test_mysensor")
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_generic_numeric_sensor_missing_state(
    hass: HomeAssistant, mock_client: APIClient, mock_generic_device_entry
) -> None:
    """Test a generic numeric sensor that is missing state."""
    entity_info = [
        SensorInfo(
            object_id="mysensor",
            key=1,
            name="my sensor",
            unique_id="my_sensor",
        )
    ]
    states = [SensorState(key=1, state=True, missing_state=True)]
    user_service = []
    await mock_generic_device_entry(
        mock_client=mock_client,
        entity_info=entity_info,
        user_service=user_service,
        states=states,
    )
    state = hass.states.get("sensor.test_mysensor")
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_generic_text_sensor(
    hass: HomeAssistant,
    mock_client: APIClient,
    mock_generic_device_entry,
) -> None:
    """Test a generic text sensor entity."""
    entity_info = [
        TextSensorInfo(
            object_id="mysensor",
            key=1,
            name="my sensor",
            unique_id="my_sensor",
        )
    ]
    states = [TextSensorState(key=1, state="i am a teapot")]
    user_service = []
    await mock_generic_device_entry(
        mock_client=mock_client,
        entity_info=entity_info,
        user_service=user_service,
        states=states,
    )
    state = hass.states.get("sensor.test_mysensor")
    assert state is not None
    assert state.state == "i am a teapot"
