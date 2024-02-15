"""Test System Monitor sensor."""

from datetime import timedelta
import socket
from unittest.mock import Mock, patch

from freezegun.api import FrozenDateTimeFactory
from psutil._common import sdiskusage, shwtemp, snetio, snicaddr
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.systemmonitor.const import DOMAIN
from homeassistant.components.systemmonitor.sensor import get_cpu_icon
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from .conftest import MockProcess, svmem

from tests.common import MockConfigEntry, async_fire_time_changed


async def test_sensor(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_psutil: Mock,
    mock_os: Mock,
    mock_util: Mock,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the sensor."""
    mock_config_entry = MockConfigEntry(
        title="System Monitor",
        domain=DOMAIN,
        data={},
        options={
            "binary_sensor": {"process": ["python3", "pip"]},
            "sensor": {"process": ["python3", "pip"]},
            "resources": [
                "disk_use_percent_/",
                "disk_use_percent_/home/notexist/",
                "memory_free_",
                "network_out_eth0",
                "process_python3",
            ],
        },
    )
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    memory_sensor = hass.states.get("sensor.system_monitor_memory_free")
    assert memory_sensor is not None
    assert memory_sensor.state == "40.0"
    assert memory_sensor.attributes == {
        "state_class": "measurement",
        "unit_of_measurement": "MiB",
        "device_class": "data_size",
        "icon": "mdi:memory",
        "friendly_name": "System Monitor Memory free",
    }

    process_sensor = hass.states.get("sensor.system_monitor_process_python3")
    assert process_sensor is not None
    assert process_sensor.state == STATE_ON

    for entity in er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    ):
        if entity.domain == SENSOR_DOMAIN:
            state = hass.states.get(entity.entity_id)
            assert state.state == snapshot(name=f"{state.name} - state")
            assert state.attributes == snapshot(name=f"{state.name} - attributes")


async def test_process_sensor_not_loaded(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_psutil: Mock,
    mock_os: Mock,
    mock_util: Mock,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the process sensor is not loaded once migrated."""
    mock_config_entry = MockConfigEntry(
        title="System Monitor",
        domain=DOMAIN,
        data={},
        options={
            "binary_sensor": {"process": ["python3", "pip"]},
            "resources": [
                "disk_use_percent_/",
                "disk_use_percent_/home/notexist/",
                "memory_free_",
                "network_out_eth0",
                "process_python3",
            ],
        },
    )
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    process_sensor = hass.states.get("sensor.system_monitor_process_python3")
    assert process_sensor is None


async def test_sensor_not_loading_veth_networks(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_added_config_entry: ConfigEntry,
) -> None:
    """Test the sensor."""
    network_sensor_1 = hass.states.get("sensor.system_monitor_network_out_eth1")
    network_sensor_2 = hass.states.get(
        "sensor.sensor.system_monitor_network_out_vethxyzxyz"
    )
    assert network_sensor_1 is not None
    assert network_sensor_1.state == "200.0"
    assert network_sensor_2 is None


async def test_sensor_icon(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_util: Mock,
    mock_psutil: Mock,
    mock_os: Mock,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the sensor icon for 32bit/64bit system."""

    get_cpu_icon.cache_clear()
    with patch("sys.maxsize", 2**32):
        assert get_cpu_icon() == "mdi:cpu-32-bit"
    get_cpu_icon.cache_clear()
    with patch("sys.maxsize", 2**64):
        assert get_cpu_icon() == "mdi:cpu-64-bit"


async def test_sensor_yaml(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_psutil: Mock,
    mock_os: Mock,
    mock_util: Mock,
) -> None:
    """Test the sensor imported from YAML."""
    config = {
        "sensor": {
            "platform": "systemmonitor",
            "resources": [
                {"type": "disk_use_percent"},
                {"type": "disk_use_percent", "arg": "/media/share"},
                {"type": "memory_free", "arg": "/"},
                {"type": "network_out", "arg": "eth0"},
                {"type": "process", "arg": "python3"},
            ],
        }
    }
    assert await async_setup_component(hass, "sensor", config)
    await hass.async_block_till_done()
    memory_sensor = hass.states.get("sensor.system_monitor_memory_free")
    assert memory_sensor is not None
    assert memory_sensor.state == "40.0"

    process_sensor = hass.states.get("binary_sensor.system_monitor_process_python3")
    assert process_sensor is not None
    assert process_sensor.state == STATE_ON


async def test_sensor_yaml_fails_missing_argument(
    caplog: pytest.LogCaptureFixture,
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_psutil: Mock,
    mock_os: Mock,
    mock_util: Mock,
) -> None:
    """Test the sensor imported from YAML fails on missing mandatory argument."""
    config = {
        "sensor": {
            "platform": "systemmonitor",
            "resources": [
                {"type": "network_in"},
            ],
        }
    }
    assert await async_setup_component(hass, "sensor", config)
    await hass.async_block_till_done()

    assert "Mandatory 'arg' is missing for sensor type 'network_in'" in caplog.text


async def test_sensor_updating(
    hass: HomeAssistant,
    mock_psutil: Mock,
    mock_os: Mock,
    mock_util: Mock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the sensor."""
    mock_config_entry = MockConfigEntry(
        title="System Monitor",
        domain=DOMAIN,
        data={},
        options={
            "binary_sensor": {"process": ["python3", "pip"]},
            "sensor": {"process": ["python3", "pip"]},
            "resources": [
                "disk_use_percent_/",
                "disk_use_percent_/home/notexist/",
                "memory_free_",
                "network_out_eth0",
                "process_python3",
            ],
        },
    )
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    memory_sensor = hass.states.get("sensor.system_monitor_memory_free")
    assert memory_sensor is not None
    assert memory_sensor.state == "40.0"

    process_sensor = hass.states.get("sensor.system_monitor_process_python3")
    assert process_sensor is not None
    assert process_sensor.state == STATE_ON

    mock_psutil.virtual_memory.side_effect = Exception("Failed to update")
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    memory_sensor = hass.states.get("sensor.system_monitor_memory_free")
    assert memory_sensor is not None
    assert memory_sensor.state == STATE_UNAVAILABLE

    mock_psutil.virtual_memory.side_effect = None
    mock_psutil.virtual_memory.return_value = svmem(
        100 * 1024**2,
        25 * 1024**2,
        25.0,
        60 * 1024**2,
        30 * 1024**2,
        1,
        1,
        1,
        1,
        1,
        1,
    )
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    memory_sensor = hass.states.get("sensor.system_monitor_memory_free")
    assert memory_sensor is not None
    assert memory_sensor.state == "25.0"


async def test_sensor_process_fails(
    hass: HomeAssistant,
    mock_psutil: Mock,
    mock_os: Mock,
    mock_util: Mock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test process not exist failure."""
    mock_config_entry = MockConfigEntry(
        title="System Monitor",
        domain=DOMAIN,
        data={},
        options={
            "binary_sensor": {"process": ["python3", "pip"]},
            "sensor": {"process": ["python3", "pip"]},
            "resources": [
                "disk_use_percent_/",
                "disk_use_percent_/home/notexist/",
                "memory_free_",
                "network_out_eth0",
                "process_python3",
            ],
        },
    )
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    process_sensor = hass.states.get("sensor.system_monitor_process_python3")
    assert process_sensor is not None
    assert process_sensor.state == STATE_ON

    _process = MockProcess("python3", True)

    mock_psutil.process_iter.return_value = [_process]

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    process_sensor = hass.states.get("sensor.system_monitor_process_python3")
    assert process_sensor is not None
    assert process_sensor.state == STATE_OFF

    assert "Failed to load process with ID: 1, old name: python3" in caplog.text


async def test_sensor_network_sensors(
    freezer: FrozenDateTimeFactory,
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_added_config_entry: ConfigEntry,
    mock_psutil: Mock,
) -> None:
    """Test process not exist failure."""
    network_out_sensor = hass.states.get("sensor.system_monitor_network_out_eth1")
    packets_out_sensor = hass.states.get("sensor.system_monitor_packets_out_eth1")
    throughput_network_out_sensor = hass.states.get(
        "sensor.system_monitor_network_throughput_out_eth1"
    )

    assert network_out_sensor is not None
    assert packets_out_sensor is not None
    assert throughput_network_out_sensor is not None
    assert network_out_sensor.state == "200.0"
    assert packets_out_sensor.state == "150"
    assert throughput_network_out_sensor.state == STATE_UNKNOWN

    mock_psutil.net_io_counters.return_value = {
        "eth0": snetio(200 * 1024**2, 200 * 1024**2, 100, 100, 0, 0, 0, 0),
        "eth1": snetio(400 * 1024**2, 400 * 1024**2, 300, 300, 0, 0, 0, 0),
    }

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    network_out_sensor = hass.states.get("sensor.system_monitor_network_out_eth1")
    packets_out_sensor = hass.states.get("sensor.system_monitor_packets_out_eth1")
    throughput_network_out_sensor = hass.states.get(
        "sensor.system_monitor_network_throughput_out_eth1"
    )

    assert network_out_sensor is not None
    assert packets_out_sensor is not None
    assert throughput_network_out_sensor is not None
    assert network_out_sensor.state == "400.0"
    assert packets_out_sensor.state == "300"
    assert float(throughput_network_out_sensor.state) == pytest.approx(3.493, rel=0.1)

    mock_psutil.net_io_counters.return_value = {
        "eth0": snetio(100 * 1024**2, 100 * 1024**2, 50, 50, 0, 0, 0, 0),
    }
    mock_psutil.net_if_addrs.return_value = {
        "eth0": [
            snicaddr(
                socket.AF_INET,
                "192.168.1.1",
                "255.255.255.0",
                "255.255.255.255",
                None,
            )
        ],
    }

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    network_out_sensor = hass.states.get("sensor.system_monitor_network_out_eth1")
    packets_out_sensor = hass.states.get("sensor.system_monitor_packets_out_eth1")
    throughput_network_out_sensor = hass.states.get(
        "sensor.system_monitor_network_throughput_out_eth1"
    )

    assert network_out_sensor is not None
    assert packets_out_sensor is not None
    assert throughput_network_out_sensor is not None
    assert network_out_sensor.state == STATE_UNKNOWN
    assert packets_out_sensor.state == STATE_UNKNOWN
    assert throughput_network_out_sensor.state == STATE_UNKNOWN


async def test_missing_cpu_temperature(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_util: Mock,
    mock_psutil: Mock,
    mock_os: Mock,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the sensor when temperature missing."""
    mock_psutil.sensors_temperatures.return_value = {
        "not_exist": [shwtemp("not_exist", 50.0, 60.0, 70.0)]
    }
    mock_util.sensors_temperatures.return_value = {
        "not_exist": [shwtemp("not_exist", 50.0, 60.0, 70.0)]
    }
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # assert "Cannot read CPU / processor temperature information" in caplog.text
    temp_sensor = hass.states.get("sensor.system_monitor_processor_temperature")
    assert temp_sensor is None


async def test_processor_temperature(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_util: Mock,
    mock_psutil: Mock,
    mock_os: Mock,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the disk failures."""

    with patch("sys.platform", "linux"):
        mock_psutil.sensors_temperatures.return_value = {
            "cpu0-thermal": [shwtemp("cpu0-thermal", 50.0, 60.0, 70.0)]
        }
        mock_psutil.sensors_temperatures.side_effect = None
        mock_config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        temp_entity = hass.states.get("sensor.system_monitor_processor_temperature")
        assert temp_entity.state == "50.0"
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    with patch("sys.platform", "nt"):
        mock_psutil.sensors_temperatures.return_value = None
        mock_psutil.sensors_temperatures.side_effect = AttributeError(
            "sensors_temperatures not exist"
        )
        mock_config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        temp_entity = hass.states.get("sensor.system_monitor_processor_temperature")
        assert temp_entity.state == STATE_UNAVAILABLE
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    with patch("sys.platform", "darwin"):
        mock_psutil.sensors_temperatures.return_value = {
            "cpu0-thermal": [shwtemp("cpu0-thermal", 50.0, 60.0, 70.0)]
        }
        mock_psutil.sensors_temperatures.side_effect = None
        mock_config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        temp_entity = hass.states.get("sensor.system_monitor_processor_temperature")
        assert temp_entity.state == "50.0"
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()


async def test_exception_handling_disk_sensor(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_psutil: Mock,
    mock_added_config_entry: ConfigEntry,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the sensor."""
    disk_sensor = hass.states.get("sensor.system_monitor_disk_free")
    assert disk_sensor is not None
    assert disk_sensor.state == "200.0"  # GiB

    mock_psutil.disk_usage.return_value = None
    mock_psutil.disk_usage.side_effect = OSError("Could not update /")

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert (
        "Error fetching System Monitor Disk / coordinator data: OS error for /"
        in caplog.text
    )

    disk_sensor = hass.states.get("sensor.system_monitor_disk_free")
    assert disk_sensor is not None
    assert disk_sensor.state == STATE_UNAVAILABLE

    mock_psutil.disk_usage.return_value = None
    mock_psutil.disk_usage.side_effect = PermissionError("No access to /")

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert (
        "Error fetching System Monitor Disk / coordinator data: OS error for /"
        in caplog.text
    )

    disk_sensor = hass.states.get("sensor.system_monitor_disk_free")
    assert disk_sensor is not None
    assert disk_sensor.state == STATE_UNAVAILABLE

    mock_psutil.disk_usage.return_value = sdiskusage(
        500 * 1024**3, 350 * 1024**3, 150 * 1024**3, 70.0
    )
    mock_psutil.disk_usage.side_effect = None

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    disk_sensor = hass.states.get("sensor.system_monitor_disk_free")
    assert disk_sensor is not None
    assert disk_sensor.state == "150.0"
    assert disk_sensor.attributes["unit_of_measurement"] == "GiB"

    disk_sensor = hass.states.get("sensor.system_monitor_disk_usage")
    assert disk_sensor is not None
    assert disk_sensor.state == "70.0"
    assert disk_sensor.attributes["unit_of_measurement"] == "%"


async def test_cpu_percentage_is_zero_returns_unknown(
    hass: HomeAssistant,
    entity_registry_enabled_by_default: None,
    mock_psutil: Mock,
    mock_added_config_entry: ConfigEntry,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the sensor."""
    cpu_sensor = hass.states.get("sensor.system_monitor_processor_use")
    assert cpu_sensor is not None
    assert cpu_sensor.state == "10"

    mock_psutil.cpu_percent.return_value = 0.0

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    cpu_sensor = hass.states.get("sensor.system_monitor_processor_use")
    assert cpu_sensor is not None
    assert cpu_sensor.state == STATE_UNKNOWN

    mock_psutil.cpu_percent.return_value = 15.0

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    cpu_sensor = hass.states.get("sensor.system_monitor_processor_use")
    assert cpu_sensor is not None
    assert cpu_sensor.state == "15"
