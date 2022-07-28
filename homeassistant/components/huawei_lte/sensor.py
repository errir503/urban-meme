"""Support for Huawei LTE sensors."""
from __future__ import annotations

from bisect import bisect
from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import re
from typing import NamedTuple

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DATA_BYTES,
    DATA_RATE_BYTES_PER_SECOND,
    FREQUENCY_MEGAHERTZ,
    PERCENTAGE,
    STATE_UNKNOWN,
    TIME_SECONDS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import HuaweiLteBaseEntityWithDevice
from .const import (
    DOMAIN,
    KEY_DEVICE_INFORMATION,
    KEY_DEVICE_SIGNAL,
    KEY_MONITORING_CHECK_NOTIFICATIONS,
    KEY_MONITORING_MONTH_STATISTICS,
    KEY_MONITORING_STATUS,
    KEY_MONITORING_TRAFFIC_STATISTICS,
    KEY_NET_CURRENT_PLMN,
    KEY_NET_NET_MODE,
    KEY_SMS_SMS_COUNT,
    SENSOR_KEYS,
)

_LOGGER = logging.getLogger(__name__)


class SensorMeta(NamedTuple):
    """Metadata for defining sensors."""

    name: str | None = None
    device_class: SensorDeviceClass | None = None
    icon: str | Callable[[StateType], str] | None = None
    native_unit_of_measurement: str | None = None
    state_class: SensorStateClass | None = None
    entity_registry_enabled_default: bool = False
    entity_category: EntityCategory | None = None
    include: re.Pattern[str] | None = None
    exclude: re.Pattern[str] | None = None
    formatter: Callable[[str], tuple[StateType, str | None]] | None = None


SENSOR_META: dict[str | tuple[str, str], SensorMeta] = {
    #
    # Device information
    #
    KEY_DEVICE_INFORMATION: SensorMeta(
        include=re.compile(r"^(WanIP.*Address|uptime)$", re.IGNORECASE)
    ),
    (KEY_DEVICE_INFORMATION, "uptime"): SensorMeta(
        name="Uptime",
        icon="mdi:timer-outline",
        native_unit_of_measurement=TIME_SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_INFORMATION, "WanIPAddress"): SensorMeta(
        name="WAN IP address",
        icon="mdi:ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=True,
    ),
    (KEY_DEVICE_INFORMATION, "WanIPv6Address"): SensorMeta(
        name="WAN IPv6 address",
        icon="mdi:ip",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    #
    # Signal
    #
    (KEY_DEVICE_SIGNAL, "band"): SensorMeta(
        name="Band",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "cell_id"): SensorMeta(
        name="Cell ID",
        icon="mdi:transmission-tower",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "cqi0"): SensorMeta(
        name="CQI 0",
        icon="mdi:speedometer",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "cqi1"): SensorMeta(
        name="CQI 1",
        icon="mdi:speedometer",
    ),
    (KEY_DEVICE_SIGNAL, "dl_mcs"): SensorMeta(
        name="Downlink MCS",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "dlbandwidth"): SensorMeta(
        name="Downlink bandwidth",
        icon=lambda x: (
            "mdi:speedometer-slow",
            "mdi:speedometer-medium",
            "mdi:speedometer",
        )[bisect((8, 15), x if x is not None else -1000)],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "earfcn"): SensorMeta(
        name="EARFCN",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "ecio"): SensorMeta(
        name="EC/IO",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        # https://wiki.teltonika.lt/view/EC/IO
        icon=lambda x: (
            "mdi:signal-cellular-outline",
            "mdi:signal-cellular-1",
            "mdi:signal-cellular-2",
            "mdi:signal-cellular-3",
        )[bisect((-20, -10, -6), x if x is not None else -1000)],
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "enodeb_id"): SensorMeta(
        name="eNodeB ID",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "lac"): SensorMeta(
        name="LAC",
        icon="mdi:map-marker",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "ltedlfreq"): SensorMeta(
        name="Downlink frequency",
        formatter=lambda x: (
            round(int(x) / 10) if x is not None else None,
            FREQUENCY_MEGAHERTZ,
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "lteulfreq"): SensorMeta(
        name="Uplink frequency",
        formatter=lambda x: (
            round(int(x) / 10) if x is not None else None,
            FREQUENCY_MEGAHERTZ,
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "mode"): SensorMeta(
        name="Mode",
        formatter=lambda x: ({"0": "2G", "2": "3G", "7": "4G"}.get(x, "Unknown"), None),
        icon=lambda x: (
            {"2G": "mdi:signal-2g", "3G": "mdi:signal-3g", "4G": "mdi:signal-4g"}.get(
                str(x), "mdi:signal"
            )
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "pci"): SensorMeta(
        name="PCI",
        icon="mdi:transmission-tower",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "plmn"): SensorMeta(
        name="PLMN",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "rac"): SensorMeta(
        name="RAC",
        icon="mdi:map-marker",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "rrc_status"): SensorMeta(
        name="RRC status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "rscp"): SensorMeta(
        name="RSCP",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        # https://wiki.teltonika.lt/view/RSCP
        icon=lambda x: (
            "mdi:signal-cellular-outline",
            "mdi:signal-cellular-1",
            "mdi:signal-cellular-2",
            "mdi:signal-cellular-3",
        )[bisect((-95, -85, -75), x if x is not None else -1000)],
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "rsrp"): SensorMeta(
        name="RSRP",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        # http://www.lte-anbieter.info/technik/rsrp.php
        icon=lambda x: (
            "mdi:signal-cellular-outline",
            "mdi:signal-cellular-1",
            "mdi:signal-cellular-2",
            "mdi:signal-cellular-3",
        )[bisect((-110, -95, -80), x if x is not None else -1000)],
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=True,
    ),
    (KEY_DEVICE_SIGNAL, "rsrq"): SensorMeta(
        name="RSRQ",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        # http://www.lte-anbieter.info/technik/rsrq.php
        icon=lambda x: (
            "mdi:signal-cellular-outline",
            "mdi:signal-cellular-1",
            "mdi:signal-cellular-2",
            "mdi:signal-cellular-3",
        )[bisect((-11, -8, -5), x if x is not None else -1000)],
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=True,
    ),
    (KEY_DEVICE_SIGNAL, "rssi"): SensorMeta(
        name="RSSI",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        # https://eyesaas.com/wi-fi-signal-strength/
        icon=lambda x: (
            "mdi:signal-cellular-outline",
            "mdi:signal-cellular-1",
            "mdi:signal-cellular-2",
            "mdi:signal-cellular-3",
        )[bisect((-80, -70, -60), x if x is not None else -1000)],
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=True,
    ),
    (KEY_DEVICE_SIGNAL, "sinr"): SensorMeta(
        name="SINR",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        # http://www.lte-anbieter.info/technik/sinr.php
        icon=lambda x: (
            "mdi:signal-cellular-outline",
            "mdi:signal-cellular-1",
            "mdi:signal-cellular-2",
            "mdi:signal-cellular-3",
        )[bisect((0, 5, 10), x if x is not None else -1000)],
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=True,
    ),
    (KEY_DEVICE_SIGNAL, "tac"): SensorMeta(
        name="TAC",
        icon="mdi:map-marker",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "tdd"): SensorMeta(
        name="TDD",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "transmode"): SensorMeta(
        name="Transmission mode",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "txpower"): SensorMeta(
        name="Transmit power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "ul_mcs"): SensorMeta(
        name="Uplink MCS",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_DEVICE_SIGNAL, "ulbandwidth"): SensorMeta(
        name="Uplink bandwidth",
        icon=lambda x: (
            "mdi:speedometer-slow",
            "mdi:speedometer-medium",
            "mdi:speedometer",
        )[bisect((8, 15), x if x is not None else -1000)],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    #
    # Monitoring
    #
    KEY_MONITORING_CHECK_NOTIFICATIONS: SensorMeta(
        exclude=re.compile(
            r"^(onlineupdatestatus|smsstoragefull)$",
            re.IGNORECASE,
        )
    ),
    (KEY_MONITORING_CHECK_NOTIFICATIONS, "UnreadMessage"): SensorMeta(
        name="SMS unread", icon="mdi:email-arrow-left"
    ),
    KEY_MONITORING_MONTH_STATISTICS: SensorMeta(
        exclude=re.compile(r"^month(duration|lastcleartime)$", re.IGNORECASE)
    ),
    (KEY_MONITORING_MONTH_STATISTICS, "CurrentMonthDownload"): SensorMeta(
        name="Current month download",
        native_unit_of_measurement=DATA_BYTES,
        icon="mdi:download",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    (KEY_MONITORING_MONTH_STATISTICS, "CurrentMonthUpload"): SensorMeta(
        name="Current month upload",
        native_unit_of_measurement=DATA_BYTES,
        icon="mdi:upload",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    KEY_MONITORING_STATUS: SensorMeta(
        include=re.compile(
            r"^(batterypercent|currentwifiuser|(primary|secondary).*dns)$",
            re.IGNORECASE,
        )
    ),
    (KEY_MONITORING_STATUS, "BatteryPercent"): SensorMeta(
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_MONITORING_STATUS, "CurrentWifiUser"): SensorMeta(
        name="WiFi clients connected",
        icon="mdi:wifi",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_MONITORING_STATUS, "PrimaryDns"): SensorMeta(
        name="Primary DNS server",
        icon="mdi:ip",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_MONITORING_STATUS, "PrimaryIPv6Dns"): SensorMeta(
        name="Primary IPv6 DNS server",
        icon="mdi:ip",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_MONITORING_STATUS, "SecondaryDns"): SensorMeta(
        name="Secondary DNS server",
        icon="mdi:ip",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_MONITORING_STATUS, "SecondaryIPv6Dns"): SensorMeta(
        name="Secondary IPv6 DNS server",
        icon="mdi:ip",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    KEY_MONITORING_TRAFFIC_STATISTICS: SensorMeta(
        exclude=re.compile(r"^showtraffic$", re.IGNORECASE)
    ),
    (KEY_MONITORING_TRAFFIC_STATISTICS, "CurrentConnectTime"): SensorMeta(
        name="Current connection duration",
        native_unit_of_measurement=TIME_SECONDS,
        icon="mdi:timer-outline",
    ),
    (KEY_MONITORING_TRAFFIC_STATISTICS, "CurrentDownload"): SensorMeta(
        name="Current connection download",
        native_unit_of_measurement=DATA_BYTES,
        icon="mdi:download",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    (KEY_MONITORING_TRAFFIC_STATISTICS, "CurrentDownloadRate"): SensorMeta(
        name="Current download rate",
        native_unit_of_measurement=DATA_RATE_BYTES_PER_SECOND,
        icon="mdi:download",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    (KEY_MONITORING_TRAFFIC_STATISTICS, "CurrentUpload"): SensorMeta(
        name="Current connection upload",
        native_unit_of_measurement=DATA_BYTES,
        icon="mdi:upload",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    (KEY_MONITORING_TRAFFIC_STATISTICS, "CurrentUploadRate"): SensorMeta(
        name="Current upload rate",
        native_unit_of_measurement=DATA_RATE_BYTES_PER_SECOND,
        icon="mdi:upload",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    (KEY_MONITORING_TRAFFIC_STATISTICS, "TotalConnectTime"): SensorMeta(
        name="Total connected duration",
        native_unit_of_measurement=TIME_SECONDS,
        icon="mdi:timer-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    (KEY_MONITORING_TRAFFIC_STATISTICS, "TotalDownload"): SensorMeta(
        name="Total download",
        native_unit_of_measurement=DATA_BYTES,
        icon="mdi:download",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    (KEY_MONITORING_TRAFFIC_STATISTICS, "TotalUpload"): SensorMeta(
        name="Total upload",
        native_unit_of_measurement=DATA_BYTES,
        icon="mdi:upload",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    #
    # Network
    #
    KEY_NET_CURRENT_PLMN: SensorMeta(
        exclude=re.compile(r"^(Rat|ShortName|Spn)$", re.IGNORECASE)
    ),
    (KEY_NET_CURRENT_PLMN, "FullName"): SensorMeta(
        name="Operator name",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_NET_CURRENT_PLMN, "Numeric"): SensorMeta(
        name="Operator code",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (KEY_NET_CURRENT_PLMN, "State"): SensorMeta(
        name="Operator search mode",
        formatter=lambda x: ({"0": "Auto", "1": "Manual"}.get(x, "Unknown"), None),
        entity_category=EntityCategory.CONFIG,
    ),
    KEY_NET_NET_MODE: SensorMeta(include=re.compile(r"^NetworkMode$", re.IGNORECASE)),
    (KEY_NET_NET_MODE, "NetworkMode"): SensorMeta(
        name="Preferred mode",
        formatter=lambda x: (
            {
                "00": "4G/3G/2G",
                "01": "2G",
                "02": "3G",
                "03": "4G",
                "0301": "4G/2G",
                "0302": "4G/3G",
                "0201": "3G/2G",
            }.get(x, "Unknown"),
            None,
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    #
    # SMS
    #
    (KEY_SMS_SMS_COUNT, "LocalDeleted"): SensorMeta(
        name="SMS deleted (device)",
        icon="mdi:email-minus",
    ),
    (KEY_SMS_SMS_COUNT, "LocalDraft"): SensorMeta(
        name="SMS drafts (device)",
        icon="mdi:email-arrow-right-outline",
    ),
    (KEY_SMS_SMS_COUNT, "LocalInbox"): SensorMeta(
        name="SMS inbox (device)",
        icon="mdi:email",
    ),
    (KEY_SMS_SMS_COUNT, "LocalMax"): SensorMeta(
        name="SMS capacity (device)",
        icon="mdi:email",
    ),
    (KEY_SMS_SMS_COUNT, "LocalOutbox"): SensorMeta(
        name="SMS outbox (device)",
        icon="mdi:email-arrow-right",
    ),
    (KEY_SMS_SMS_COUNT, "LocalUnread"): SensorMeta(
        name="SMS unread (device)",
        icon="mdi:email-arrow-left",
    ),
    (KEY_SMS_SMS_COUNT, "SimDraft"): SensorMeta(
        name="SMS drafts (SIM)",
        icon="mdi:email-arrow-right-outline",
    ),
    (KEY_SMS_SMS_COUNT, "SimInbox"): SensorMeta(
        name="SMS inbox (SIM)",
        icon="mdi:email",
    ),
    (KEY_SMS_SMS_COUNT, "SimMax"): SensorMeta(
        name="SMS capacity (SIM)",
        icon="mdi:email",
    ),
    (KEY_SMS_SMS_COUNT, "SimOutbox"): SensorMeta(
        name="SMS outbox (SIM)",
        icon="mdi:email-arrow-right",
    ),
    (KEY_SMS_SMS_COUNT, "SimUnread"): SensorMeta(
        name="SMS unread (SIM)",
        icon="mdi:email-arrow-left",
    ),
    (KEY_SMS_SMS_COUNT, "SimUsed"): SensorMeta(
        name="SMS messages (SIM)",
        icon="mdi:email-arrow-left",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up from config entry."""
    router = hass.data[DOMAIN].routers[config_entry.unique_id]
    sensors: list[Entity] = []
    for key in SENSOR_KEYS:
        if not (items := router.data.get(key)):
            continue
        if key_meta := SENSOR_META.get(key):
            if key_meta.include:
                items = filter(key_meta.include.search, items)
            if key_meta.exclude:
                items = [x for x in items if not key_meta.exclude.search(x)]
        for item in items:
            sensors.append(
                HuaweiLteSensor(
                    router, key, item, SENSOR_META.get((key, item), SensorMeta())
                )
            )

    async_add_entities(sensors, True)


def format_default(value: StateType) -> tuple[StateType, str | None]:
    """Format value."""
    unit = None
    if value is not None:
        # Clean up value and infer unit, e.g. -71dBm, 15 dB
        if match := re.match(
            r"([>=<]*)(?P<value>.+?)\s*(?P<unit>[a-zA-Z]+)\s*$", str(value)
        ):
            try:
                value = float(match.group("value"))
                unit = match.group("unit")
            except ValueError:
                pass
    return value, unit


@dataclass
class HuaweiLteSensor(HuaweiLteBaseEntityWithDevice, SensorEntity):
    """Huawei LTE sensor entity."""

    key: str
    item: str
    meta: SensorMeta

    _state: StateType = field(default=STATE_UNKNOWN, init=False)
    _unit: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize remaining attributes."""
        self._attr_name = self.meta.name or self.item

    async def async_added_to_hass(self) -> None:
        """Subscribe to needed data on add."""
        await super().async_added_to_hass()
        self.router.subscriptions[self.key].add(f"{SENSOR_DOMAIN}/{self.item}")

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from needed data on remove."""
        await super().async_will_remove_from_hass()
        self.router.subscriptions[self.key].remove(f"{SENSOR_DOMAIN}/{self.item}")

    @property
    def _device_unique_id(self) -> str:
        return f"{self.key}.{self.item}"

    @property
    def native_value(self) -> StateType:
        """Return sensor state."""
        return self._state

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return sensor device class."""
        return self.meta.device_class

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return sensor's unit of measurement."""
        return self.meta.native_unit_of_measurement or self._unit

    @property
    def icon(self) -> str | None:
        """Return icon for sensor."""
        icon = self.meta.icon
        if callable(icon):
            return icon(self.state)
        return icon

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return sensor state class."""
        return self.meta.state_class

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self.meta.entity_registry_enabled_default

    async def async_update(self) -> None:
        """Update state."""
        try:
            value = self.router.data[self.key][self.item]
        except KeyError:
            _LOGGER.debug("%s[%s] not in data", self.key, self.item)
            value = None

        formatter = self.meta.formatter
        if not callable(formatter):
            formatter = format_default

        self._state, self._unit = formatter(value)
        self._available = value is not None

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return category of entity, if any."""
        return self.meta.entity_category
