"""Support for QNAP NAS Sensors."""
from __future__ import annotations

from datetime import timedelta
import logging

from qnapstats import QNAPStats
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import (
    ATTR_NAME,
    CONF_HOST,
    CONF_MONITORED_CONDITIONS,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_TIMEOUT,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    PERCENTAGE,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

ATTR_DRIVE = "Drive"
ATTR_DRIVE_SIZE = "Drive Size"
ATTR_IP = "IP Address"
ATTR_MAC = "MAC Address"
ATTR_MASK = "Mask"
ATTR_MAX_SPEED = "Max Speed"
ATTR_MEMORY_SIZE = "Memory Size"
ATTR_MODEL = "Model"
ATTR_PACKETS_TX = "Packets (TX)"
ATTR_PACKETS_RX = "Packets (RX)"
ATTR_PACKETS_ERR = "Packets (Err)"
ATTR_SERIAL = "Serial #"
ATTR_TYPE = "Type"
ATTR_UPTIME = "Uptime"
ATTR_VOLUME_SIZE = "Volume Size"

CONF_DRIVES = "drives"
CONF_NICS = "nics"
CONF_VOLUMES = "volumes"
DEFAULT_NAME = "QNAP"
DEFAULT_PORT = 8080
DEFAULT_TIMEOUT = 5

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=1)

NOTIFICATION_ID = "qnap_notification"
NOTIFICATION_TITLE = "QNAP Sensor Setup"

_SYSTEM_MON_COND: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="status",
        name="Status",
        icon="mdi:checkbox-marked-circle-outline",
    ),
    SensorEntityDescription(
        key="system_temp",
        name="System Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
)
_CPU_MON_COND: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="cpu_temp",
        name="CPU Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="cpu_usage",
        name="CPU Usage",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:chip",
    ),
)
_MEMORY_MON_COND: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="memory_free",
        name="Memory Available",
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        icon="mdi:memory",
    ),
    SensorEntityDescription(
        key="memory_used",
        name="Memory Used",
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        icon="mdi:memory",
    ),
    SensorEntityDescription(
        key="memory_percent_used",
        name="Memory Usage",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:memory",
    ),
)
_NETWORK_MON_COND: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="network_link_status",
        name="Network Link",
        icon="mdi:checkbox-marked-circle-outline",
    ),
    SensorEntityDescription(
        key="network_tx",
        name="Network Up",
        native_unit_of_measurement=UnitOfDataRate.MEBIBYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        icon="mdi:upload",
    ),
    SensorEntityDescription(
        key="network_rx",
        name="Network Down",
        native_unit_of_measurement=UnitOfDataRate.MEBIBYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        icon="mdi:download",
    ),
)
_DRIVE_MON_COND: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="drive_smart_status",
        name="SMART Status",
        icon="mdi:checkbox-marked-circle-outline",
    ),
    SensorEntityDescription(
        key="drive_temp",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
)
_VOLUME_MON_COND: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="volume_size_used",
        name="Used Space",
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        icon="mdi:chart-pie",
    ),
    SensorEntityDescription(
        key="volume_size_free",
        name="Free Space",
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        icon="mdi:chart-pie",
    ),
    SensorEntityDescription(
        key="volume_percentage_used",
        name="Volume Used",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:chart-pie",
    ),
)

SENSOR_KEYS: list[str] = [
    desc.key
    for desc in (
        *_SYSTEM_MON_COND,
        *_CPU_MON_COND,
        *_MEMORY_MON_COND,
        *_NETWORK_MON_COND,
        *_DRIVE_MON_COND,
        *_VOLUME_MON_COND,
    )
]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_SSL, default=False): cv.boolean,
        vol.Optional(CONF_VERIFY_SSL, default=True): cv.boolean,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_MONITORED_CONDITIONS): vol.All(
            cv.ensure_list, [vol.In(SENSOR_KEYS)]
        ),
        vol.Optional(CONF_NICS): cv.ensure_list,
        vol.Optional(CONF_DRIVES): cv.ensure_list,
        vol.Optional(CONF_VOLUMES): cv.ensure_list,
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the QNAP NAS sensor."""
    api = QNAPStatsAPI(config)
    api.update()

    # QNAP is not available
    if not api.data:
        raise PlatformNotReady

    monitored_conditions = config[CONF_MONITORED_CONDITIONS]
    sensors: list[QNAPSensor] = []

    # Basic sensors
    sensors.extend(
        [
            QNAPSystemSensor(api, description)
            for description in _SYSTEM_MON_COND
            if description.key in monitored_conditions
        ]
    )
    sensors.extend(
        [
            QNAPCPUSensor(api, description)
            for description in _CPU_MON_COND
            if description.key in monitored_conditions
        ]
    )
    sensors.extend(
        [
            QNAPMemorySensor(api, description)
            for description in _MEMORY_MON_COND
            if description.key in monitored_conditions
        ]
    )

    # Network sensors
    sensors.extend(
        [
            QNAPNetworkSensor(api, description, nic)
            for nic in config.get(CONF_NICS, api.data["system_stats"]["nics"])
            for description in _NETWORK_MON_COND
            if description.key in monitored_conditions
        ]
    )

    # Drive sensors
    sensors.extend(
        [
            QNAPDriveSensor(api, description, drive)
            for drive in config.get(CONF_DRIVES, api.data["smart_drive_health"])
            for description in _DRIVE_MON_COND
            if description.key in monitored_conditions
        ]
    )

    # Volume sensors
    sensors.extend(
        [
            QNAPVolumeSensor(api, description, volume)
            for volume in config.get(CONF_VOLUMES, api.data["volumes"])
            for description in _VOLUME_MON_COND
            if description.key in monitored_conditions
        ]
    )

    add_entities(sensors)


def round_nicely(number):
    """Round a number based on its size (so it looks nice)."""
    if number < 10:
        return round(number, 2)
    if number < 100:
        return round(number, 1)

    return round(number)


class QNAPStatsAPI:
    """Class to interface with the API."""

    def __init__(self, config):
        """Initialize the API wrapper."""

        protocol = "https" if config[CONF_SSL] else "http"
        self._api = QNAPStats(
            f"{protocol}://{config.get(CONF_HOST)}",
            config.get(CONF_PORT),
            config.get(CONF_USERNAME),
            config.get(CONF_PASSWORD),
            verify_ssl=config.get(CONF_VERIFY_SSL),
            timeout=config.get(CONF_TIMEOUT),
        )

        self.data = {}

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Update API information and store locally."""
        try:
            self.data["system_stats"] = self._api.get_system_stats()
            self.data["system_health"] = self._api.get_system_health()
            self.data["smart_drive_health"] = self._api.get_smart_disk_health()
            self.data["volumes"] = self._api.get_volumes()
            self.data["bandwidth"] = self._api.get_bandwidth()
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Failed to fetch QNAP stats from the NAS")


class QNAPSensor(SensorEntity):
    """Base class for a QNAP sensor."""

    def __init__(
        self, api, description: SensorEntityDescription, monitor_device=None
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self.monitor_device = monitor_device
        self._api = api

    @property
    def name(self):
        """Return the name of the sensor, if any."""
        server_name = self._api.data["system_stats"]["system"]["name"]

        if self.monitor_device is not None:
            return (
                f"{server_name} {self.entity_description.name} ({self.monitor_device})"
            )
        return f"{server_name} {self.entity_description.name}"

    def update(self) -> None:
        """Get the latest data for the states."""
        self._api.update()


class QNAPCPUSensor(QNAPSensor):
    """A QNAP sensor that monitors CPU stats."""

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.entity_description.key == "cpu_temp":
            return self._api.data["system_stats"]["cpu"]["temp_c"]
        if self.entity_description.key == "cpu_usage":
            return self._api.data["system_stats"]["cpu"]["usage_percent"]


class QNAPMemorySensor(QNAPSensor):
    """A QNAP sensor that monitors memory stats."""

    @property
    def native_value(self):
        """Return the state of the sensor."""
        free = float(self._api.data["system_stats"]["memory"]["free"]) / 1024
        if self.entity_description.key == "memory_free":
            return round_nicely(free)

        total = float(self._api.data["system_stats"]["memory"]["total"]) / 1024

        used = total - free
        if self.entity_description.key == "memory_used":
            return round_nicely(used)

        if self.entity_description.key == "memory_percent_used":
            return round(used / total * 100)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self._api.data:
            data = self._api.data["system_stats"]["memory"]
            size = round_nicely(float(data["total"]) / 1024)
            return {ATTR_MEMORY_SIZE: f"{size} {UnitOfInformation.GIBIBYTES}"}


class QNAPNetworkSensor(QNAPSensor):
    """A QNAP sensor that monitors network stats."""

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.entity_description.key == "network_link_status":
            nic = self._api.data["system_stats"]["nics"][self.monitor_device]
            return nic["link_status"]

        data = self._api.data["bandwidth"][self.monitor_device]
        if self.entity_description.key == "network_tx":
            return round_nicely(data["tx"] / 1024 / 1024)

        if self.entity_description.key == "network_rx":
            return round_nicely(data["rx"] / 1024 / 1024)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self._api.data:
            data = self._api.data["system_stats"]["nics"][self.monitor_device]
            return {
                ATTR_IP: data["ip"],
                ATTR_MASK: data["mask"],
                ATTR_MAC: data["mac"],
                ATTR_MAX_SPEED: data["max_speed"],
                ATTR_PACKETS_TX: data["tx_packets"],
                ATTR_PACKETS_RX: data["rx_packets"],
                ATTR_PACKETS_ERR: data["err_packets"],
            }


class QNAPSystemSensor(QNAPSensor):
    """A QNAP sensor that monitors overall system health."""

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.entity_description.key == "status":
            return self._api.data["system_health"]

        if self.entity_description.key == "system_temp":
            return int(self._api.data["system_stats"]["system"]["temp_c"])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self._api.data:
            data = self._api.data["system_stats"]
            days = int(data["uptime"]["days"])
            hours = int(data["uptime"]["hours"])
            minutes = int(data["uptime"]["minutes"])

            return {
                ATTR_NAME: data["system"]["name"],
                ATTR_MODEL: data["system"]["model"],
                ATTR_SERIAL: data["system"]["serial_number"],
                ATTR_UPTIME: f"{days:0>2d}d {hours:0>2d}h {minutes:0>2d}m",
            }


class QNAPDriveSensor(QNAPSensor):
    """A QNAP sensor that monitors HDD/SSD drive stats."""

    @property
    def native_value(self):
        """Return the state of the sensor."""
        data = self._api.data["smart_drive_health"][self.monitor_device]

        if self.entity_description.key == "drive_smart_status":
            return data["health"]

        if self.entity_description.key == "drive_temp":
            return int(data["temp_c"]) if data["temp_c"] is not None else 0

    @property
    def name(self):
        """Return the name of the sensor, if any."""
        server_name = self._api.data["system_stats"]["system"]["name"]

        return (
            f"{server_name} {self.entity_description.name} (Drive"
            f" {self.monitor_device})"
        )

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self._api.data:
            data = self._api.data["smart_drive_health"][self.monitor_device]
            return {
                ATTR_DRIVE: data["drive_number"],
                ATTR_MODEL: data["model"],
                ATTR_SERIAL: data["serial"],
                ATTR_TYPE: data["type"],
            }


class QNAPVolumeSensor(QNAPSensor):
    """A QNAP sensor that monitors storage volume stats."""

    @property
    def native_value(self):
        """Return the state of the sensor."""
        data = self._api.data["volumes"][self.monitor_device]

        free_gb = int(data["free_size"]) / 1024 / 1024 / 1024
        if self.entity_description.key == "volume_size_free":
            return round_nicely(free_gb)

        total_gb = int(data["total_size"]) / 1024 / 1024 / 1024

        used_gb = total_gb - free_gb
        if self.entity_description.key == "volume_size_used":
            return round_nicely(used_gb)

        if self.entity_description.key == "volume_percentage_used":
            return round(used_gb / total_gb * 100)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self._api.data:
            data = self._api.data["volumes"][self.monitor_device]
            total_gb = int(data["total_size"]) / 1024 / 1024 / 1024

            return {
                ATTR_VOLUME_SIZE: (
                    f"{round_nicely(total_gb)} {UnitOfInformation.GIBIBYTES}"
                )
            }
