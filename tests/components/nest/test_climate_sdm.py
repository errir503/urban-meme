"""
Test for Nest climate platform for the Smart Device Management API.

These tests fake out the subscriber/devicemanager, and are not using a real
pubsub subscriber.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from google_nest_sdm.auth import AbstractAuth
from google_nest_sdm.event import EventMessage
import pytest

from homeassistant.components.climate.const import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODES,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_OFF,
    FAN_LOW,
    FAN_OFF,
    FAN_ON,
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_HEAT_COOL,
    HVAC_MODE_OFF,
    PRESET_ECO,
    PRESET_NONE,
    PRESET_SLEEP,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant

from .common import (
    DEVICE_COMMAND,
    DEVICE_ID,
    CreateDevice,
    FakeSubscriber,
    PlatformSetup,
)
from .conftest import FakeAuth

from tests.components.climate import common

CreateEvent = Callable[[dict[str, Any]], Awaitable[None]]

EVENT_ID = "some-event-id"


@pytest.fixture
def platforms() -> list[str]:
    """Fixture to specify platforms to test."""
    return ["climate"]


@pytest.fixture
def device_traits() -> dict[str, Any]:
    """Fixture that sets default traits used for devices."""
    return {"sdm.devices.traits.Info": {"customName": "My Thermostat"}}


@pytest.fixture
async def create_event(
    hass: HomeAssistant,
    auth: AbstractAuth,
    subscriber: FakeSubscriber,
) -> CreateEvent:
    """Fixture to send a pub/sub event."""

    async def create_event(traits: dict[str, Any]) -> None:
        await subscriber.async_receive_event(
            EventMessage(
                {
                    "eventId": EVENT_ID,
                    "timestamp": "2019-01-01T00:00:01Z",
                    "resourceUpdate": {
                        "name": DEVICE_ID,
                        "traits": traits,
                    },
                },
                auth=auth,
            )
        )
        await hass.async_block_till_done()

    return create_event


async def test_no_devices(hass: HomeAssistant, setup_platform: PlatformSetup) -> None:
    """Test no devices returned by the api."""
    await setup_platform()
    assert len(hass.states.async_all()) == 0


async def test_climate_devices(
    hass: HomeAssistant, setup_platform: PlatformSetup, create_device: CreateDevice
) -> None:
    """Test no eligible climate devices returned by the api."""
    create_device.create({"sdm.devices.traits.CameraImage": {}})
    await setup_platform()
    assert len(hass.states.async_all()) == 0


async def test_thermostat_off(
    hass: HomeAssistant, setup_platform: PlatformSetup, create_device: CreateDevice
):
    """Test a thermostat that is not running."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 16.2,
            },
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 16.2
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_TEMPERATURE] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] is None
    assert ATTR_PRESET_MODE not in thermostat.attributes
    assert ATTR_PRESET_MODES not in thermostat.attributes
    assert ATTR_FAN_MODE not in thermostat.attributes
    assert ATTR_FAN_MODES not in thermostat.attributes


async def test_thermostat_heat(
    hass: HomeAssistant, setup_platform: PlatformSetup, create_device: CreateDevice
):
    """Test a thermostat that is heating."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {
                "status": "HEATING",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEAT",
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 16.2,
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "heatCelsius": 22.0,
            },
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_HEAT
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 16.2
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_TEMPERATURE] == 22.0
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] is None
    assert ATTR_PRESET_MODE not in thermostat.attributes
    assert ATTR_PRESET_MODES not in thermostat.attributes


async def test_thermostat_cool(
    hass: HomeAssistant, setup_platform: PlatformSetup, create_device: CreateDevice
):
    """Test a thermostat that is cooling."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {
                "status": "COOLING",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "COOL",
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 29.9,
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "coolCelsius": 28.0,
            },
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_COOL
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_COOL
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 29.9
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_TEMPERATURE] == 28.0
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] is None
    assert ATTR_PRESET_MODE not in thermostat.attributes
    assert ATTR_PRESET_MODES not in thermostat.attributes


async def test_thermostat_heatcool(
    hass: HomeAssistant, setup_platform: PlatformSetup, create_device: CreateDevice
):
    """Test a thermostat that is cooling in heatcool mode."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {
                "status": "COOLING",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEATCOOL",
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 29.9,
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "heatCelsius": 22.0,
                "coolCelsius": 28.0,
            },
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT_COOL
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_COOL
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 29.9
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] == 22.0
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] == 28.0
    assert thermostat.attributes[ATTR_TEMPERATURE] is None
    assert ATTR_PRESET_MODE not in thermostat.attributes
    assert ATTR_PRESET_MODES not in thermostat.attributes


async def test_thermostat_eco_off(
    hass: HomeAssistant, setup_platform: PlatformSetup, create_device: CreateDevice
) -> None:
    """Test a thermostat cooling with eco off."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {
                "status": "COOLING",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEATCOOL",
            },
            "sdm.devices.traits.ThermostatEco": {
                "availableModes": ["MANUAL_ECO", "OFF"],
                "mode": "OFF",
                "heatCelsius": 20.0,
                "coolCelsius": 22.0,
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 29.9,
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "heatCelsius": 22.0,
                "coolCelsius": 28.0,
            },
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT_COOL
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_COOL
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 29.9
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] == 22.0
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] == 28.0
    assert thermostat.attributes[ATTR_TEMPERATURE] is None
    assert thermostat.attributes[ATTR_PRESET_MODE] == PRESET_NONE
    assert thermostat.attributes[ATTR_PRESET_MODES] == [PRESET_ECO, PRESET_NONE]


async def test_thermostat_eco_on(
    hass: HomeAssistant, setup_platform: PlatformSetup, create_device: CreateDevice
) -> None:
    """Test a thermostat in eco mode."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {
                "status": "COOLING",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEATCOOL",
            },
            "sdm.devices.traits.ThermostatEco": {
                "availableModes": ["MANUAL_ECO", "OFF"],
                "mode": "MANUAL_ECO",
                "heatCelsius": 21.0,
                "coolCelsius": 29.0,
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 29.9,
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "heatCelsius": 22.0,
                "coolCelsius": 28.0,
            },
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT_COOL
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_COOL
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 29.9
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] == 21.0
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] == 29.0
    assert thermostat.attributes[ATTR_TEMPERATURE] is None
    assert thermostat.attributes[ATTR_PRESET_MODE] == PRESET_ECO
    assert thermostat.attributes[ATTR_PRESET_MODES] == [PRESET_ECO, PRESET_NONE]


async def test_thermostat_eco_heat_only(
    hass: HomeAssistant, setup_platform: PlatformSetup, create_device: CreateDevice
) -> None:
    """Test a thermostat in eco mode that only supports heat."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {
                "status": "OFF",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "OFF"],
                "mode": "HEAT",
            },
            "sdm.devices.traits.ThermostatEco": {
                "availableModes": ["MANUAL_ECO", "OFF"],
                "mode": "MANUAL_ECO",
                "heatCelsius": 21.0,
                "coolCelsius": 29.0,
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 29.9,
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {},
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_IDLE
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 29.9
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_TEMPERATURE] == 21.0
    assert ATTR_TARGET_TEMP_LOW not in thermostat.attributes
    assert ATTR_TARGET_TEMP_HIGH not in thermostat.attributes
    assert thermostat.attributes[ATTR_PRESET_MODE] == PRESET_ECO
    assert thermostat.attributes[ATTR_PRESET_MODES] == [PRESET_ECO, PRESET_NONE]


async def test_thermostat_set_hvac_mode(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    auth: FakeAuth,
    create_device: CreateDevice,
    create_event: CreateEvent,
) -> None:
    """Test a thermostat changing hvac modes."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF

    await common.async_set_hvac_mode(hass, HVAC_MODE_HEAT)
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.ThermostatMode.SetMode",
        "params": {"mode": "HEAT"},
    }

    # Local state does not reflect the update
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF

    # Simulate pubsub message when mode changes
    await create_event(
        {
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEAT",
            },
        }
    )

    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_IDLE

    # Simulate pubsub message when the thermostat starts heating
    await create_event(
        {
            "sdm.devices.traits.ThermostatHvac": {
                "status": "HEATING",
            },
        }
    )

    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_HEAT


async def test_thermostat_invalid_hvac_mode(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    auth: FakeAuth,
    create_device: CreateDevice,
) -> None:
    """Test setting an hvac_mode that is not supported."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF

    with pytest.raises(ValueError):
        await common.async_set_hvac_mode(hass, HVAC_MODE_DRY)
        await hass.async_block_till_done()

    assert thermostat.state == HVAC_MODE_OFF
    assert auth.method is None  # No communication with API


async def test_thermostat_set_eco_preset(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    auth: FakeAuth,
    create_device: CreateDevice,
    create_event: CreateEvent,
) -> None:
    """Test a thermostat put into eco mode."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatEco": {
                "availableModes": ["MANUAL_ECO", "OFF"],
                "mode": "OFF",
                "heatCelsius": 15.0,
                "coolCelsius": 28.0,
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF
    assert thermostat.attributes[ATTR_PRESET_MODE] == PRESET_NONE

    # Turn on eco mode
    await common.async_set_preset_mode(hass, PRESET_ECO)
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.ThermostatEco.SetMode",
        "params": {"mode": "MANUAL_ECO"},
    }

    # Local state does not reflect the update
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF
    assert thermostat.attributes[ATTR_PRESET_MODE] == PRESET_NONE

    # Simulate pubsub message when mode changes
    await create_event(
        {
            "sdm.devices.traits.ThermostatEco": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "MANUAL_ECO",
                "heatCelsius": 15.0,
                "coolCelsius": 28.0,
            },
        }
    )

    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF
    assert thermostat.attributes[ATTR_PRESET_MODE] == PRESET_ECO

    # Turn off eco mode
    await common.async_set_preset_mode(hass, PRESET_NONE)
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.ThermostatEco.SetMode",
        "params": {"mode": "OFF"},
    }


async def test_thermostat_set_cool(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    auth: FakeAuth,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat in cool mode with a temperature change."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "COOL",
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "coolCelsius": 25.0,
            },
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_COOL

    await common.async_set_temperature(hass, temperature=24.0)
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetCool",
        "params": {"coolCelsius": 24.0},
    }


async def test_thermostat_set_heat(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    auth: FakeAuth,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat heating mode with a temperature change."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEAT",
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "heatCelsius": 19.0,
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT

    await common.async_set_temperature(hass, temperature=20.0)
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetHeat",
        "params": {"heatCelsius": 20.0},
    }


async def test_thermostat_set_temperature_hvac_mode(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    auth: FakeAuth,
    create_device: CreateDevice,
) -> None:
    """Test setting HVAC mode while setting temperature."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "coolCelsius": 25.0,
            },
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF

    await common.async_set_temperature(hass, temperature=24.0, hvac_mode=HVAC_MODE_COOL)
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetCool",
        "params": {"coolCelsius": 24.0},
    }

    await common.async_set_temperature(hass, temperature=26.0, hvac_mode=HVAC_MODE_HEAT)
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetHeat",
        "params": {"heatCelsius": 26.0},
    }

    await common.async_set_temperature(
        hass, target_temp_low=20.0, target_temp_high=24.0, hvac_mode=HVAC_MODE_HEAT_COOL
    )
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetRange",
        "params": {"heatCelsius": 20.0, "coolCelsius": 24.0},
    }


async def test_thermostat_set_heat_cool(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    auth: FakeAuth,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat in heatcool mode with a temperature change."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEATCOOL",
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "heatCelsius": 19.0,
                "coolCelsius": 25.0,
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT_COOL

    await common.async_set_temperature(
        hass, target_temp_low=20.0, target_temp_high=24.0
    )
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetRange",
        "params": {"heatCelsius": 20.0, "coolCelsius": 24.0},
    }


async def test_thermostat_fan_off(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat with the fan not running."""
    create_device.create(
        {
            "sdm.devices.traits.Fan": {
                "timerMode": "OFF",
                "timerTimeout": "2019-05-10T03:22:54Z",
            },
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 16.2,
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 16.2
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_FAN_ONLY,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_FAN_MODE] == FAN_OFF
    assert thermostat.attributes[ATTR_FAN_MODES] == [FAN_ON, FAN_OFF]


async def test_thermostat_fan_on(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat with the fan running."""
    create_device.create(
        {
            "sdm.devices.traits.Fan": {
                "timerMode": "ON",
                "timerTimeout": "2019-05-10T03:22:54Z",
            },
            "sdm.devices.traits.ThermostatHvac": {
                "status": "OFF",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 16.2,
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_FAN_ONLY
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_IDLE
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 16.2
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_FAN_ONLY,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_FAN_MODE] == FAN_ON
    assert thermostat.attributes[ATTR_FAN_MODES] == [FAN_ON, FAN_OFF]


async def test_thermostat_cool_with_fan(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat cooling while the fan is on."""
    create_device.create(
        {
            "sdm.devices.traits.Fan": {
                "timerMode": "ON",
                "timerTimeout": "2019-05-10T03:22:54Z",
            },
            "sdm.devices.traits.ThermostatHvac": {
                "status": "OFF",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "COOL",
            },
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_COOL
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_IDLE
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_FAN_ONLY,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_FAN_MODE] == FAN_ON
    assert thermostat.attributes[ATTR_FAN_MODES] == [FAN_ON, FAN_OFF]


async def test_thermostat_set_fan(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    auth: FakeAuth,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat enabling the fan."""
    create_device.create(
        {
            "sdm.devices.traits.Fan": {
                "timerMode": "ON",
                "timerTimeout": "2019-05-10T03:22:54Z",
            },
            "sdm.devices.traits.ThermostatHvac": {
                "status": "OFF",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_FAN_ONLY
    assert thermostat.attributes[ATTR_FAN_MODE] == FAN_ON
    assert thermostat.attributes[ATTR_FAN_MODES] == [FAN_ON, FAN_OFF]

    # Turn off fan mode
    await common.async_set_fan_mode(hass, FAN_OFF)
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.Fan.SetTimer",
        "params": {"timerMode": "OFF"},
    }

    # Turn on fan mode
    await common.async_set_fan_mode(hass, FAN_ON)
    await hass.async_block_till_done()

    assert auth.method == "post"
    assert auth.url == DEVICE_COMMAND
    assert auth.json == {
        "command": "sdm.devices.commands.Fan.SetTimer",
        "params": {
            "duration": "43200s",
            "timerMode": "ON",
        },
    }


async def test_thermostat_fan_empty(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
) -> None:
    """Test a fan trait with an empty response."""
    create_device.create(
        {
            "sdm.devices.traits.Fan": {},
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 16.2,
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 16.2
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_OFF,
    }
    assert ATTR_FAN_MODE not in thermostat.attributes
    assert ATTR_FAN_MODES not in thermostat.attributes

    # Ignores set_fan_mode since it is lacking SUPPORT_FAN_MODE
    await common.async_set_fan_mode(hass, FAN_ON)
    await hass.async_block_till_done()

    assert ATTR_FAN_MODE not in thermostat.attributes
    assert ATTR_FAN_MODES not in thermostat.attributes


async def test_thermostat_invalid_fan_mode(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
) -> None:
    """Test setting a fan mode that is not supported."""
    create_device.create(
        {
            "sdm.devices.traits.Fan": {
                "timerMode": "ON",
                "timerTimeout": "2019-05-10T03:22:54Z",
            },
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 16.2,
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_FAN_ONLY
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_IDLE
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 16.2
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_FAN_ONLY,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_FAN_MODE] == FAN_ON
    assert thermostat.attributes[ATTR_FAN_MODES] == [FAN_ON, FAN_OFF]

    with pytest.raises(ValueError):
        await common.async_set_fan_mode(hass, FAN_LOW)
        await hass.async_block_till_done()


async def test_thermostat_set_hvac_fan_only(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    auth: FakeAuth,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat enabling the fan via hvac_mode."""
    create_device.create(
        {
            "sdm.devices.traits.Fan": {
                "timerMode": "OFF",
                "timerTimeout": "2019-05-10T03:22:54Z",
            },
            "sdm.devices.traits.ThermostatHvac": {
                "status": "OFF",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "OFF",
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_FAN_MODE] == FAN_OFF
    assert thermostat.attributes[ATTR_FAN_MODES] == [FAN_ON, FAN_OFF]

    await common.async_set_hvac_mode(hass, HVAC_MODE_FAN_ONLY)
    await hass.async_block_till_done()

    assert len(auth.captured_requests) == 2

    (method, url, json, headers) = auth.captured_requests.pop(0)
    assert method == "post"
    assert url == DEVICE_COMMAND
    assert json == {
        "command": "sdm.devices.commands.Fan.SetTimer",
        "params": {"duration": "43200s", "timerMode": "ON"},
    }
    (method, url, json, headers) = auth.captured_requests.pop(0)
    assert method == "post"
    assert url == DEVICE_COMMAND
    assert json == {
        "command": "sdm.devices.commands.ThermostatMode.SetMode",
        "params": {"mode": "OFF"},
    }


async def test_thermostat_target_temp(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
    create_event: CreateEvent,
) -> None:
    """Test a thermostat changing hvac modes and affected on target temps."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {
                "status": "HEATING",
            },
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEAT",
            },
            "sdm.devices.traits.Temperature": {
                "ambientTemperatureCelsius": 20.1,
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "heatCelsius": 23.0,
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT
    assert thermostat.attributes[ATTR_TEMPERATURE] == 23.0
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] is None

    # Simulate pubsub message changing modes
    await create_event(
        {
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEATCOOL",
            },
            "sdm.devices.traits.ThermostatTemperatureSetpoint": {
                "heatCelsius": 22.0,
                "coolCelsius": 28.0,
            },
        }
    )

    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT_COOL
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] == 22.0
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] == 28.0
    assert thermostat.attributes[ATTR_TEMPERATURE] is None


async def test_thermostat_missing_mode_traits(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat missing many thermostat traits in api response."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] is None
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == set()
    assert ATTR_TEMPERATURE not in thermostat.attributes
    assert ATTR_TARGET_TEMP_LOW not in thermostat.attributes
    assert ATTR_TARGET_TEMP_HIGH not in thermostat.attributes
    assert ATTR_PRESET_MODE not in thermostat.attributes
    assert ATTR_PRESET_MODES not in thermostat.attributes
    assert ATTR_FAN_MODE not in thermostat.attributes
    assert ATTR_FAN_MODES not in thermostat.attributes

    await common.async_set_temperature(hass, temperature=24.0)
    await hass.async_block_till_done()
    assert ATTR_TEMPERATURE not in thermostat.attributes

    await common.async_set_preset_mode(hass, PRESET_ECO)
    await hass.async_block_till_done()
    assert ATTR_PRESET_MODE not in thermostat.attributes


async def test_thermostat_missing_temperature_trait(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat missing many thermostat traits in api response."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEAT",
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_IDLE
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] is None
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_TEMPERATURE] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] is None
    assert ATTR_PRESET_MODE not in thermostat.attributes
    assert ATTR_PRESET_MODES not in thermostat.attributes
    assert ATTR_FAN_MODE not in thermostat.attributes
    assert ATTR_FAN_MODES not in thermostat.attributes

    await common.async_set_temperature(hass, temperature=24.0)
    await hass.async_block_till_done()
    assert thermostat.attributes[ATTR_TEMPERATURE] is None


async def test_thermostat_unexpected_hvac_status(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat missing many thermostat traits in api response."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "UNEXPECTED"},
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert ATTR_HVAC_ACTION not in thermostat.attributes
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] is None
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == set()
    assert ATTR_TEMPERATURE not in thermostat.attributes
    assert ATTR_TARGET_TEMP_LOW not in thermostat.attributes
    assert ATTR_TARGET_TEMP_HIGH not in thermostat.attributes
    assert ATTR_PRESET_MODE not in thermostat.attributes
    assert ATTR_PRESET_MODES not in thermostat.attributes
    assert ATTR_FAN_MODE not in thermostat.attributes
    assert ATTR_FAN_MODES not in thermostat.attributes

    with pytest.raises(ValueError):
        await common.async_set_hvac_mode(hass, HVAC_MODE_DRY)
        await hass.async_block_till_done()
    assert thermostat.state == HVAC_MODE_OFF


async def test_thermostat_missing_set_point(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat missing many thermostat traits in api response."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"],
                "mode": "HEATCOOL",
            },
        },
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_HEAT_COOL
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_IDLE
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] is None
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_TEMPERATURE] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] is None
    assert ATTR_PRESET_MODE not in thermostat.attributes
    assert ATTR_PRESET_MODES not in thermostat.attributes
    assert ATTR_FAN_MODE not in thermostat.attributes
    assert ATTR_FAN_MODES not in thermostat.attributes


async def test_thermostat_unexepected_hvac_mode(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat missing many thermostat traits in api response."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatMode": {
                "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF", "UNEXPECTED"],
                "mode": "UNEXPECTED",
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_HVAC_ACTION] == CURRENT_HVAC_OFF
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] is None
    assert set(thermostat.attributes[ATTR_HVAC_MODES]) == {
        HVAC_MODE_HEAT,
        HVAC_MODE_COOL,
        HVAC_MODE_HEAT_COOL,
        HVAC_MODE_OFF,
    }
    assert thermostat.attributes[ATTR_TEMPERATURE] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_LOW] is None
    assert thermostat.attributes[ATTR_TARGET_TEMP_HIGH] is None
    assert ATTR_PRESET_MODE not in thermostat.attributes
    assert ATTR_PRESET_MODES not in thermostat.attributes
    assert ATTR_FAN_MODE not in thermostat.attributes
    assert ATTR_FAN_MODES not in thermostat.attributes


async def test_thermostat_invalid_set_preset_mode(
    hass: HomeAssistant,
    setup_platform: PlatformSetup,
    auth: FakeAuth,
    create_device: CreateDevice,
) -> None:
    """Test a thermostat set with an invalid preset mode."""
    create_device.create(
        {
            "sdm.devices.traits.ThermostatHvac": {"status": "OFF"},
            "sdm.devices.traits.ThermostatEco": {
                "availableModes": ["MANUAL_ECO", "OFF"],
                "mode": "OFF",
                "heatCelsius": 15.0,
                "coolCelsius": 28.0,
            },
        }
    )
    await setup_platform()

    assert len(hass.states.async_all()) == 1
    thermostat = hass.states.get("climate.my_thermostat")
    assert thermostat is not None
    assert thermostat.state == HVAC_MODE_OFF
    assert thermostat.attributes[ATTR_PRESET_MODE] == PRESET_NONE
    assert thermostat.attributes[ATTR_PRESET_MODES] == [PRESET_ECO, PRESET_NONE]

    # Set preset mode that is invalid
    with pytest.raises(ValueError):
        await common.async_set_preset_mode(hass, PRESET_SLEEP)
        await hass.async_block_till_done()

    # No RPC sent
    assert auth.method is None

    # Preset is unchanged
    assert thermostat.attributes[ATTR_PRESET_MODE] == PRESET_NONE
    assert thermostat.attributes[ATTR_PRESET_MODES] == [PRESET_ECO, PRESET_NONE]
