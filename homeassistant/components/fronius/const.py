"""Constants for the Fronius integration."""
from typing import Final, NamedTuple, TypedDict

from homeassistant.helpers.device_registry import DeviceInfo

DOMAIN: Final = "fronius"

SolarNetId = str
SOLAR_NET_DISCOVERY_NEW: Final = "fronius_discovery_new"
SOLAR_NET_ID_POWER_FLOW: SolarNetId = "power_flow"
SOLAR_NET_ID_SYSTEM: SolarNetId = "system"
SOLAR_NET_RESCAN_TIMER: Final = 60


class FroniusConfigEntryData(TypedDict):
    """ConfigEntry for the Fronius integration."""

    host: str
    is_logger: bool


class FroniusDeviceInfo(NamedTuple):
    """Information about a Fronius inverter device."""

    device_info: DeviceInfo
    solar_net_id: SolarNetId
    unique_id: str
