"""Support for Huawei LTE sensors."""
from __future__ import annotations

from bisect import bisect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import re

from huawei_lte_api.enums.net import NetworkModeEnum

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfFrequency,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
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


def format_freq_mhz(value: StateType) -> tuple[StateType, UnitOfFrequency]:
    """Format a frequency value for which source is in tenths of MHz."""
    return (
        float(value) / 10 if value is not None else None,
        UnitOfFrequency.MEGAHERTZ,
    )


def format_last_reset_elapsed_seconds(value: str | None) -> datetime | None:
    """Convert elapsed seconds to last reset datetime."""
    if value is None:
        return None
    try:
        last_reset = datetime.now() - timedelta(seconds=int(value))
        last_reset.replace(microsecond=0)
        return last_reset
    except ValueError:
        return None


def signal_icon(limits: Sequence[int], value: StateType) -> str:
    """Get signal icon."""
    return (
        "mdi:signal-cellular-outline",
        "mdi:signal-cellular-1",
        "mdi:signal-cellular-2",
        "mdi:signal-cellular-3",
    )[bisect(limits, value if value is not None else -1000)]


def bandwidth_icon(limits: Sequence[int], value: StateType) -> str:
    """Get bandwidth icon."""
    return (
        "mdi:speedometer-slow",
        "mdi:speedometer-medium",
        "mdi:speedometer",
    )[bisect(limits, value if value is not None else -1000)]


@dataclass
class HuaweiSensorGroup:
    """Class describing Huawei LTE sensor groups."""

    descriptions: dict[str, HuaweiSensorEntityDescription]
    include: re.Pattern[str] | None = None
    exclude: re.Pattern[str] | None = None


@dataclass
class HuaweiSensorEntityDescription(SensorEntityDescription):
    """Class describing Huawei LTE sensor entities."""

    format_fn: Callable[[str], tuple[StateType, str | None]] = format_default
    icon_fn: Callable[[StateType], str] | None = None
    device_class_fn: Callable[[StateType], SensorDeviceClass | None] | None = None
    last_reset_item: str | None = None
    last_reset_format_fn: Callable[[str | None], datetime | None] | None = None


SENSOR_META: dict[str, HuaweiSensorGroup] = {
    #
    # Device information
    #
    KEY_DEVICE_INFORMATION: HuaweiSensorGroup(
        include=re.compile(r"^(WanIP.*Address|uptime)$", re.IGNORECASE),
        descriptions={
            "uptime": HuaweiSensorEntityDescription(
                key="uptime",
                name="Uptime",
                icon="mdi:timer-outline",
                native_unit_of_measurement=UnitOfTime.SECONDS,
                device_class=SensorDeviceClass.DURATION,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "WanIPAddress": HuaweiSensorEntityDescription(
                key="WanIPAddress",
                name="WAN IP address",
                icon="mdi:ip",
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=True,
            ),
            "WanIPv6Address": HuaweiSensorEntityDescription(
                key="WanIPv6Address",
                name="WAN IPv6 address",
                icon="mdi:ip",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        },
    ),
    #
    # Signal
    #
    KEY_DEVICE_SIGNAL: HuaweiSensorGroup(
        descriptions={
            "arfcn": HuaweiSensorEntityDescription(
                key="arfcn",
                name="ARFCN",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "band": HuaweiSensorEntityDescription(
                key="band",
                name="Band",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "bsic": HuaweiSensorEntityDescription(
                key="bsic",
                name="Base station identity code",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "cell_id": HuaweiSensorEntityDescription(
                key="cell_id",
                name="Cell ID",
                icon="mdi:transmission-tower",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "cqi0": HuaweiSensorEntityDescription(
                key="cqi0",
                name="CQI 0",
                icon="mdi:speedometer",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "cqi1": HuaweiSensorEntityDescription(
                key="cqi1",
                name="CQI 1",
                icon="mdi:speedometer",
            ),
            "dl_mcs": HuaweiSensorEntityDescription(
                key="dl_mcs",
                name="Downlink MCS",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "dlbandwidth": HuaweiSensorEntityDescription(
                key="dlbandwidth",
                name="Downlink bandwidth",
                icon_fn=lambda x: bandwidth_icon((8, 15), x),
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "dlfrequency": HuaweiSensorEntityDescription(
                key="dlfrequency",
                name="Downlink frequency",
                device_class=SensorDeviceClass.FREQUENCY,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "earfcn": HuaweiSensorEntityDescription(
                key="earfcn",
                name="EARFCN",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "ecio": HuaweiSensorEntityDescription(
                key="ecio",
                name="EC/IO",
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                # https://wiki.teltonika.lt/view/EC/IO
                icon_fn=lambda x: signal_icon((-20, -10, -6), x),
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "enodeb_id": HuaweiSensorEntityDescription(
                key="enodeb_id",
                name="eNodeB ID",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "lac": HuaweiSensorEntityDescription(
                key="lac",
                name="LAC",
                icon="mdi:map-marker",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "ltedlfreq": HuaweiSensorEntityDescription(
                key="ltedlfreq",
                name="LTE downlink frequency",
                format_fn=format_freq_mhz,
                suggested_display_precision=0,
                device_class=SensorDeviceClass.FREQUENCY,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "lteulfreq": HuaweiSensorEntityDescription(
                key="lteulfreq",
                name="LTE uplink frequency",
                format_fn=format_freq_mhz,
                suggested_display_precision=0,
                device_class=SensorDeviceClass.FREQUENCY,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "mode": HuaweiSensorEntityDescription(
                key="mode",
                name="Mode",
                format_fn=lambda x: (
                    {"0": "2G", "2": "3G", "7": "4G"}.get(x),
                    None,
                ),
                icon_fn=lambda x: (
                    {
                        "2G": "mdi:signal-2g",
                        "3G": "mdi:signal-3g",
                        "4G": "mdi:signal-4g",
                    }.get(str(x), "mdi:signal")
                ),
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "pci": HuaweiSensorEntityDescription(
                key="pci",
                name="PCI",
                icon="mdi:transmission-tower",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "plmn": HuaweiSensorEntityDescription(
                key="plmn",
                name="PLMN",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "rac": HuaweiSensorEntityDescription(
                key="rac",
                name="RAC",
                icon="mdi:map-marker",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "rrc_status": HuaweiSensorEntityDescription(
                key="rrc_status",
                name="RRC status",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "rscp": HuaweiSensorEntityDescription(
                key="rscp",
                name="RSCP",
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                # https://wiki.teltonika.lt/view/RSCP
                icon_fn=lambda x: signal_icon((-95, -85, -75), x),
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "rsrp": HuaweiSensorEntityDescription(
                key="rsrp",
                name="RSRP",
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                # http://www.lte-anbieter.info/technik/rsrp.php
                icon_fn=lambda x: signal_icon((-110, -95, -80), x),
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=True,
            ),
            "rsrq": HuaweiSensorEntityDescription(
                key="rsrq",
                name="RSRQ",
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                # http://www.lte-anbieter.info/technik/rsrq.php
                icon_fn=lambda x: signal_icon((-11, -8, -5), x),
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=True,
            ),
            "rssi": HuaweiSensorEntityDescription(
                key="rssi",
                name="RSSI",
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                # https://eyesaas.com/wi-fi-signal-strength/
                icon_fn=lambda x: signal_icon((-80, -70, -60), x),
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=True,
            ),
            "sinr": HuaweiSensorEntityDescription(
                key="sinr",
                name="SINR",
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                # http://www.lte-anbieter.info/technik/sinr.php
                icon_fn=lambda x: signal_icon((0, 5, 10), x),
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=True,
            ),
            "tac": HuaweiSensorEntityDescription(
                key="tac",
                name="TAC",
                icon="mdi:map-marker",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "tdd": HuaweiSensorEntityDescription(
                key="tdd",
                name="TDD",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "transmode": HuaweiSensorEntityDescription(
                key="transmode",
                name="Transmission mode",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "txpower": HuaweiSensorEntityDescription(
                key="txpower",
                name="Transmit power",
                # The value we get from the API tends to consist of several, e.g.
                #     PPusch:15dBm PPucch:2dBm PSrs:42dBm PPrach:1dBm
                # Present as SIGNAL_STRENGTH only if it was parsed to a number.
                # We could try to parse this to separate component sensors sometime.
                device_class_fn=lambda x: (
                    SensorDeviceClass.SIGNAL_STRENGTH
                    if isinstance(x, (float, int))
                    else None
                ),
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "ul_mcs": HuaweiSensorEntityDescription(
                key="ul_mcs",
                name="Uplink MCS",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "ulbandwidth": HuaweiSensorEntityDescription(
                key="ulbandwidth",
                name="Uplink bandwidth",
                icon_fn=lambda x: bandwidth_icon((8, 15), x),
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "ulfrequency": HuaweiSensorEntityDescription(
                key="ulfrequency",
                name="Uplink frequency",
                device_class=SensorDeviceClass.FREQUENCY,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        }
    ),
    #
    # Monitoring
    #
    KEY_MONITORING_CHECK_NOTIFICATIONS: HuaweiSensorGroup(
        exclude=re.compile(
            r"^(onlineupdatestatus|smsstoragefull)$",
            re.IGNORECASE,
        ),
        descriptions={
            "UnreadMessage": HuaweiSensorEntityDescription(
                key="UnreadMessage", name="SMS unread", icon="mdi:email-arrow-left"
            ),
        },
    ),
    KEY_MONITORING_MONTH_STATISTICS: HuaweiSensorGroup(
        exclude=re.compile(
            r"^(currentday|month)(duration|lastcleartime)$", re.IGNORECASE
        ),
        descriptions={
            "CurrentDayUsed": HuaweiSensorEntityDescription(
                key="CurrentDayUsed",
                name="Current day transfer",
                native_unit_of_measurement=UnitOfInformation.BYTES,
                device_class=SensorDeviceClass.DATA_SIZE,
                icon="mdi:arrow-up-down-bold",
                state_class=SensorStateClass.TOTAL,
                last_reset_item="CurrentDayDuration",
                last_reset_format_fn=format_last_reset_elapsed_seconds,
            ),
            "CurrentMonthDownload": HuaweiSensorEntityDescription(
                key="CurrentMonthDownload",
                name="Current month download",
                native_unit_of_measurement=UnitOfInformation.BYTES,
                device_class=SensorDeviceClass.DATA_SIZE,
                icon="mdi:download",
                state_class=SensorStateClass.TOTAL,
                last_reset_item="MonthDuration",
                last_reset_format_fn=format_last_reset_elapsed_seconds,
            ),
            "CurrentMonthUpload": HuaweiSensorEntityDescription(
                key="CurrentMonthUpload",
                name="Current month upload",
                native_unit_of_measurement=UnitOfInformation.BYTES,
                device_class=SensorDeviceClass.DATA_SIZE,
                icon="mdi:upload",
                state_class=SensorStateClass.TOTAL,
                last_reset_item="MonthDuration",
                last_reset_format_fn=format_last_reset_elapsed_seconds,
            ),
        },
    ),
    KEY_MONITORING_STATUS: HuaweiSensorGroup(
        include=re.compile(
            r"^(batterypercent|currentwifiuser|(primary|secondary).*dns)$",
            re.IGNORECASE,
        ),
        descriptions={
            "BatteryPercent": HuaweiSensorEntityDescription(
                key="BatteryPercent",
                name="Battery",
                device_class=SensorDeviceClass.BATTERY,
                native_unit_of_measurement=PERCENTAGE,
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "CurrentWifiUser": HuaweiSensorEntityDescription(
                key="CurrentWifiUser",
                name="WiFi clients connected",
                icon="mdi:wifi",
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "PrimaryDns": HuaweiSensorEntityDescription(
                key="PrimaryDns",
                name="Primary DNS server",
                icon="mdi:ip",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "PrimaryIPv6Dns": HuaweiSensorEntityDescription(
                key="PrimaryIPv6Dns",
                name="Primary IPv6 DNS server",
                icon="mdi:ip",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "SecondaryDns": HuaweiSensorEntityDescription(
                key="SecondaryDns",
                name="Secondary DNS server",
                icon="mdi:ip",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "SecondaryIPv6Dns": HuaweiSensorEntityDescription(
                key="SecondaryIPv6Dns",
                name="Secondary IPv6 DNS server",
                icon="mdi:ip",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        },
    ),
    KEY_MONITORING_TRAFFIC_STATISTICS: HuaweiSensorGroup(
        exclude=re.compile(r"^showtraffic$", re.IGNORECASE),
        descriptions={
            "CurrentConnectTime": HuaweiSensorEntityDescription(
                key="CurrentConnectTime",
                name="Current connection duration",
                native_unit_of_measurement=UnitOfTime.SECONDS,
                device_class=SensorDeviceClass.DURATION,
                icon="mdi:timer-outline",
            ),
            "CurrentDownload": HuaweiSensorEntityDescription(
                key="CurrentDownload",
                name="Current connection download",
                native_unit_of_measurement=UnitOfInformation.BYTES,
                device_class=SensorDeviceClass.DATA_SIZE,
                icon="mdi:download",
                state_class=SensorStateClass.TOTAL_INCREASING,
            ),
            "CurrentDownloadRate": HuaweiSensorEntityDescription(
                key="CurrentDownloadRate",
                name="Current download rate",
                native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
                device_class=SensorDeviceClass.DATA_RATE,
                icon="mdi:download",
                state_class=SensorStateClass.MEASUREMENT,
            ),
            "CurrentUpload": HuaweiSensorEntityDescription(
                key="CurrentUpload",
                name="Current connection upload",
                native_unit_of_measurement=UnitOfInformation.BYTES,
                device_class=SensorDeviceClass.DATA_SIZE,
                icon="mdi:upload",
                state_class=SensorStateClass.TOTAL_INCREASING,
            ),
            "CurrentUploadRate": HuaweiSensorEntityDescription(
                key="CurrentUploadRate",
                name="Current upload rate",
                native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
                device_class=SensorDeviceClass.DATA_RATE,
                icon="mdi:upload",
                state_class=SensorStateClass.MEASUREMENT,
            ),
            "TotalConnectTime": HuaweiSensorEntityDescription(
                key="TotalConnectTime",
                name="Total connected duration",
                native_unit_of_measurement=UnitOfTime.SECONDS,
                device_class=SensorDeviceClass.DURATION,
                icon="mdi:timer-outline",
                state_class=SensorStateClass.TOTAL_INCREASING,
            ),
            "TotalDownload": HuaweiSensorEntityDescription(
                key="TotalDownload",
                name="Total download",
                native_unit_of_measurement=UnitOfInformation.BYTES,
                device_class=SensorDeviceClass.DATA_SIZE,
                icon="mdi:download",
                state_class=SensorStateClass.TOTAL_INCREASING,
            ),
            "TotalUpload": HuaweiSensorEntityDescription(
                key="TotalUpload",
                name="Total upload",
                native_unit_of_measurement=UnitOfInformation.BYTES,
                device_class=SensorDeviceClass.DATA_SIZE,
                icon="mdi:upload",
                state_class=SensorStateClass.TOTAL_INCREASING,
            ),
        },
    ),
    #
    # Network
    #
    KEY_NET_CURRENT_PLMN: HuaweiSensorGroup(
        exclude=re.compile(r"^(Rat|ShortName|Spn)$", re.IGNORECASE),
        descriptions={
            "FullName": HuaweiSensorEntityDescription(
                key="FullName",
                name="Operator name",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "Numeric": HuaweiSensorEntityDescription(
                key="Numeric",
                name="Operator code",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            "State": HuaweiSensorEntityDescription(
                key="State",
                name="Operator search mode",
                format_fn=lambda x: (
                    {"0": "Auto", "1": "Manual"}.get(x),
                    None,
                ),
                entity_category=EntityCategory.CONFIG,
            ),
        },
    ),
    KEY_NET_NET_MODE: HuaweiSensorGroup(
        include=re.compile(r"^NetworkMode$", re.IGNORECASE),
        descriptions={
            "NetworkMode": HuaweiSensorEntityDescription(
                key="NetworkMode",
                name="Preferred mode",
                format_fn=lambda x: (
                    {
                        NetworkModeEnum.MODE_AUTO.value: "4G/3G/2G",
                        NetworkModeEnum.MODE_4G_3G_AUTO.value: "4G/3G",
                        NetworkModeEnum.MODE_4G_2G_AUTO.value: "4G/2G",
                        NetworkModeEnum.MODE_4G_ONLY.value: "4G",
                        NetworkModeEnum.MODE_3G_2G_AUTO.value: "3G/2G",
                        NetworkModeEnum.MODE_3G_ONLY.value: "3G",
                        NetworkModeEnum.MODE_2G_ONLY.value: "2G",
                    }.get(x),
                    None,
                ),
                entity_category=EntityCategory.CONFIG,
            ),
        },
    ),
    #
    # SMS
    #
    KEY_SMS_SMS_COUNT: HuaweiSensorGroup(
        descriptions={
            "LocalDeleted": HuaweiSensorEntityDescription(
                key="LocalDeleted",
                name="SMS deleted (device)",
                icon="mdi:email-minus",
            ),
            "LocalDraft": HuaweiSensorEntityDescription(
                key="LocalDraft",
                name="SMS drafts (device)",
                icon="mdi:email-arrow-right-outline",
            ),
            "LocalInbox": HuaweiSensorEntityDescription(
                key="LocalInbox",
                name="SMS inbox (device)",
                icon="mdi:email",
            ),
            "LocalMax": HuaweiSensorEntityDescription(
                key="LocalMax",
                name="SMS capacity (device)",
                icon="mdi:email",
            ),
            "LocalOutbox": HuaweiSensorEntityDescription(
                key="LocalOutbox",
                name="SMS outbox (device)",
                icon="mdi:email-arrow-right",
            ),
            "LocalUnread": HuaweiSensorEntityDescription(
                key="LocalUnread",
                name="SMS unread (device)",
                icon="mdi:email-arrow-left",
            ),
            "SimDraft": HuaweiSensorEntityDescription(
                key="SimDraft",
                name="SMS drafts (SIM)",
                icon="mdi:email-arrow-right-outline",
            ),
            "SimInbox": HuaweiSensorEntityDescription(
                key="SimInbox",
                name="SMS inbox (SIM)",
                icon="mdi:email",
            ),
            "SimMax": HuaweiSensorEntityDescription(
                key="SimMax",
                name="SMS capacity (SIM)",
                icon="mdi:email",
            ),
            "SimOutbox": HuaweiSensorEntityDescription(
                key="SimOutbox",
                name="SMS outbox (SIM)",
                icon="mdi:email-arrow-right",
            ),
            "SimUnread": HuaweiSensorEntityDescription(
                key="SimUnread",
                name="SMS unread (SIM)",
                icon="mdi:email-arrow-left",
            ),
            "SimUsed": HuaweiSensorEntityDescription(
                key="SimUsed",
                name="SMS messages (SIM)",
                icon="mdi:email-arrow-left",
            ),
        },
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up from config entry."""
    router = hass.data[DOMAIN].routers[config_entry.entry_id]
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
                    router,
                    key,
                    item,
                    SENSOR_META[key].descriptions.get(
                        item, HuaweiSensorEntityDescription(key=item)
                    ),
                )
            )

    async_add_entities(sensors, True)


@dataclass
class HuaweiLteSensor(HuaweiLteBaseEntityWithDevice, SensorEntity):
    """Huawei LTE sensor entity."""

    key: str
    item: str
    entity_description: HuaweiSensorEntityDescription

    _state: StateType = field(default=None, init=False)
    _unit: str | None = field(default=None, init=False)
    _last_reset: datetime | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize remaining attributes."""
        self._attr_name = self.entity_description.name or self.item

    async def async_added_to_hass(self) -> None:
        """Subscribe to needed data on add."""
        await super().async_added_to_hass()
        self.router.subscriptions[self.key].add(f"{SENSOR_DOMAIN}/{self.item}")
        if self.entity_description.last_reset_item:
            self.router.subscriptions[self.key].add(
                f"{SENSOR_DOMAIN}/{self.entity_description.last_reset_item}"
            )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from needed data on remove."""
        await super().async_will_remove_from_hass()
        self.router.subscriptions[self.key].remove(f"{SENSOR_DOMAIN}/{self.item}")
        if self.entity_description.last_reset_item:
            self.router.subscriptions[self.key].remove(
                f"{SENSOR_DOMAIN}/{self.entity_description.last_reset_item}"
            )

    @property
    def _device_unique_id(self) -> str:
        return f"{self.key}.{self.item}"

    @property
    def native_value(self) -> StateType:
        """Return sensor state."""
        return self._state

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return sensor's unit of measurement."""
        return self.entity_description.native_unit_of_measurement or self._unit

    @property
    def icon(self) -> str | None:
        """Return icon for sensor."""
        if self.entity_description.icon_fn:
            return self.entity_description.icon_fn(self.state)
        return self.entity_description.icon

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return device class for sensor."""
        if self.entity_description.device_class_fn:
            # Note: using self.state could infloop here.
            return self.entity_description.device_class_fn(self.native_value)
        return super().device_class

    @property
    def last_reset(self) -> datetime | None:
        """Return the time when the sensor was last reset, if any."""
        return self._last_reset

    async def async_update(self) -> None:
        """Update state."""
        try:
            value = self.router.data[self.key][self.item]
        except KeyError:
            _LOGGER.debug("%s[%s] not in data", self.key, self.item)
            value = None

        last_reset = None
        if (
            self.entity_description.last_reset_item
            and self.entity_description.last_reset_format_fn
        ):
            try:
                last_reset_value = self.router.data[self.key][
                    self.entity_description.last_reset_item
                ]
            except KeyError:
                _LOGGER.debug(
                    "%s[%s] not in data",
                    self.key,
                    self.entity_description.last_reset_item,
                )
            else:
                last_reset = self.entity_description.last_reset_format_fn(
                    last_reset_value
                )

        self._state, self._unit = self.entity_description.format_fn(value)
        self._last_reset = last_reset
        self._available = value is not None
