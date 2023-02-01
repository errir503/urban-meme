"""Tests for ZHA config flow."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
import serial.tools.list_ports
from zigpy.backups import BackupManager
import zigpy.config
from zigpy.config import CONF_DEVICE_PATH
import zigpy.types

from homeassistant import config_entries
from homeassistant.components.usb import UsbServiceInfo
from homeassistant.components.zha import radio_manager
from homeassistant.components.zha.core.const import DOMAIN, RadioType
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

PROBE_FUNCTION_PATH = "zigbee.application.ControllerApplication.probe"


@pytest.fixture(autouse=True)
def disable_platform_only():
    """Disable platforms to speed up tests."""
    with patch("homeassistant.components.zha.PLATFORMS", []):
        yield


@pytest.fixture(autouse=True)
def reduce_reconnect_timeout():
    """Reduces reconnect timeout to speed up tests."""
    with patch("homeassistant.components.zha.radio_manager.CONNECT_DELAY_S", 0.0001):
        yield


@pytest.fixture(autouse=True)
def mock_app():
    """Mock zigpy app interface."""
    mock_app = AsyncMock()
    mock_app.backups = create_autospec(BackupManager, instance=True)
    mock_app.backups.backups = []

    with patch(
        "zigpy.application.ControllerApplication.new", AsyncMock(return_value=mock_app)
    ):
        yield mock_app


@pytest.fixture
def backup():
    """Zigpy network backup with non-default settings."""
    backup = zigpy.backups.NetworkBackup()
    backup.node_info.ieee = zigpy.types.EUI64.convert("AA:BB:CC:DD:11:22:33:44")

    return backup


def mock_detect_radio_type(radio_type=RadioType.ezsp, ret=True):
    """Mock `detect_radio_type` that just sets the appropriate attributes."""

    async def detect(self):
        self.radio_type = radio_type
        self.device_settings = radio_type.controller.SCHEMA_DEVICE(
            {CONF_DEVICE_PATH: self.device_path}
        )

        return ret

    return detect


def com_port(device="/dev/ttyUSB1234"):
    """Mock of a serial port."""
    port = serial.tools.list_ports_common.ListPortInfo("/dev/ttyUSB1234")
    port.serial_number = "1234"
    port.manufacturer = "Virtual serial port"
    port.device = device
    port.description = "Some serial port"

    return port


@pytest.fixture
def mock_connect_zigpy_app() -> Generator[None, None, None]:
    """Mock the radio connection."""

    mock_connect_app = MagicMock()
    mock_connect_app.__aenter__.return_value.backups.backups = [MagicMock()]
    mock_connect_app.__aenter__.return_value.backups.create_backup.return_value = (
        MagicMock()
    )

    with patch(
        "homeassistant.components.zha.radio_manager.ZhaRadioManager._connect_zigpy_app",
        return_value=mock_connect_app,
    ):
        yield


@patch("homeassistant.components.zha.async_setup_entry", AsyncMock(return_value=True))
async def test_migrate_matching_port(
    hass: HomeAssistant,
    mock_connect_zigpy_app,
) -> None:
    """Test automatic migration."""
    # Set up the config entry
    config_entry = MockConfigEntry(
        data={"device": {"path": "/dev/ttyTEST123"}, "radio_type": "ezsp"},
        domain=DOMAIN,
        options={},
        title="Test",
        version=3,
    )
    config_entry.add_to_hass(hass)

    migration_data = {
        "new_discovery_info": {
            "name": "Test Updated",
            "port": {
                "path": "socket://some/virtual_port",
                "baudrate": 115200,
                "flow_control": "hardware",
            },
            "radio_type": "efr32",
        },
        "old_discovery_info": {
            "hw": {
                "name": "Test",
                "port": {
                    "path": "/dev/ttyTEST123",
                    "baudrate": 115200,
                    "flow_control": "hardware",
                },
                "radio_type": "efr32",
            }
        },
    }

    migration_helper = radio_manager.ZhaMultiPANMigrationHelper(hass, config_entry)
    assert await migration_helper.async_initiate_migration(migration_data)

    # Check the ZHA config entry data is updated
    assert config_entry.data == {
        "device": {
            "path": "socket://some/virtual_port",
            "baudrate": 115200,
            "flow_control": "hardware",
        },
        "radio_type": "ezsp",
    }
    assert config_entry.title == "Test Updated"

    await migration_helper.async_finish_migration()


@patch(
    "homeassistant.components.zha.radio_manager.ZhaRadioManager.detect_radio_type",
    mock_detect_radio_type(),
)
@patch("homeassistant.components.zha.async_setup_entry", AsyncMock(return_value=True))
async def test_migrate_matching_port_usb(
    hass: HomeAssistant,
    mock_connect_zigpy_app,
) -> None:
    """Test automatic migration."""
    # Set up the config entry
    config_entry = MockConfigEntry(
        data={"device": {"path": "/dev/ttyTEST123"}, "radio_type": "ezsp"},
        domain=DOMAIN,
        options={},
        title="Test",
        version=3,
    )
    config_entry.add_to_hass(hass)

    migration_data = {
        "new_discovery_info": {
            "name": "Test Updated",
            "port": {
                "path": "socket://some/virtual_port",
                "baudrate": 115200,
                "flow_control": "hardware",
            },
            "radio_type": "efr32",
        },
        "old_discovery_info": {
            "usb": UsbServiceInfo("/dev/ttyTEST123", "blah", "blah", None, None, None)
        },
    }

    migration_helper = radio_manager.ZhaMultiPANMigrationHelper(hass, config_entry)
    assert await migration_helper.async_initiate_migration(migration_data)

    # Check the ZHA config entry data is updated
    assert config_entry.data == {
        "device": {
            "path": "socket://some/virtual_port",
            "baudrate": 115200,
            "flow_control": "hardware",
        },
        "radio_type": "ezsp",
    }
    assert config_entry.title == "Test Updated"

    await migration_helper.async_finish_migration()


async def test_migrate_matching_port_config_entry_not_loaded(
    hass: HomeAssistant,
    mock_connect_zigpy_app,
) -> None:
    """Test automatic migration."""
    # Set up the config entry
    config_entry = MockConfigEntry(
        data={"device": {"path": "/dev/ttyTEST123"}, "radio_type": "ezsp"},
        domain=DOMAIN,
        options={},
        title="Test",
    )
    config_entry.add_to_hass(hass)
    config_entry.state = config_entries.ConfigEntryState.SETUP_IN_PROGRESS

    migration_data = {
        "new_discovery_info": {
            "name": "Test Updated",
            "port": {
                "path": "socket://some/virtual_port",
                "baudrate": 115200,
                "flow_control": "hardware",
            },
            "radio_type": "efr32",
        },
        "old_discovery_info": {
            "hw": {
                "name": "Test",
                "port": {
                    "path": "/dev/ttyTEST123",
                    "baudrate": 115200,
                    "flow_control": "hardware",
                },
                "radio_type": "efr32",
            }
        },
    }

    migration_helper = radio_manager.ZhaMultiPANMigrationHelper(hass, config_entry)
    assert await migration_helper.async_initiate_migration(migration_data)

    # Check the ZHA config entry data is updated
    assert config_entry.data == {
        "device": {
            "path": "socket://some/virtual_port",
            "baudrate": 115200,
            "flow_control": "hardware",
        },
        "radio_type": "ezsp",
    }
    assert config_entry.title == "Test Updated"

    await migration_helper.async_finish_migration()


@patch(
    "homeassistant.components.zha.radio_manager.ZhaRadioManager.async_restore_backup_step_1",
    side_effect=OSError,
)
async def test_migrate_matching_port_retry(
    mock_restore_backup_step_1,
    hass: HomeAssistant,
    mock_connect_zigpy_app,
) -> None:
    """Test automatic migration."""
    # Set up the config entry
    config_entry = MockConfigEntry(
        data={"device": {"path": "/dev/ttyTEST123"}, "radio_type": "ezsp"},
        domain=DOMAIN,
        options={},
        title="Test",
    )
    config_entry.add_to_hass(hass)
    config_entry.state = config_entries.ConfigEntryState.SETUP_IN_PROGRESS

    migration_data = {
        "new_discovery_info": {
            "name": "Test Updated",
            "port": {
                "path": "socket://some/virtual_port",
                "baudrate": 115200,
                "flow_control": "hardware",
            },
            "radio_type": "efr32",
        },
        "old_discovery_info": {
            "hw": {
                "name": "Test",
                "port": {
                    "path": "/dev/ttyTEST123",
                    "baudrate": 115200,
                    "flow_control": "hardware",
                },
                "radio_type": "efr32",
            }
        },
    }

    migration_helper = radio_manager.ZhaMultiPANMigrationHelper(hass, config_entry)
    assert await migration_helper.async_initiate_migration(migration_data)

    # Check the ZHA config entry data is updated
    assert config_entry.data == {
        "device": {
            "path": "socket://some/virtual_port",
            "baudrate": 115200,
            "flow_control": "hardware",
        },
        "radio_type": "ezsp",
    }
    assert config_entry.title == "Test Updated"

    with pytest.raises(OSError):
        await migration_helper.async_finish_migration()
    assert mock_restore_backup_step_1.call_count == 100


async def test_migrate_non_matching_port(
    hass: HomeAssistant,
    mock_connect_zigpy_app,
) -> None:
    """Test automatic migration."""
    # Set up the config entry
    config_entry = MockConfigEntry(
        data={"device": {"path": "/dev/ttyTEST123"}, "radio_type": "ezsp"},
        domain=DOMAIN,
        options={},
        title="Test",
    )
    config_entry.add_to_hass(hass)

    migration_data = {
        "new_discovery_info": {
            "name": "Test Updated",
            "port": {
                "path": "socket://some/virtual_port",
                "baudrate": 115200,
                "flow_control": "hardware",
            },
            "radio_type": "efr32",
        },
        "old_discovery_info": {
            "hw": {
                "name": "Test",
                "port": {
                    "path": "/dev/ttyTEST456",
                    "baudrate": 115200,
                    "flow_control": "hardware",
                },
                "radio_type": "efr32",
            }
        },
    }

    migration_helper = radio_manager.ZhaMultiPANMigrationHelper(hass, config_entry)
    assert not await migration_helper.async_initiate_migration(migration_data)

    # Check the ZHA config entry data is not updated
    assert config_entry.data == {
        "device": {"path": "/dev/ttyTEST123"},
        "radio_type": "ezsp",
    }
    assert config_entry.title == "Test"
