"""Constants for the FRITZ!Box Tools integration."""

from typing import Literal

from fritzconnection.core.exceptions import (
    FritzActionError,
    FritzActionFailedError,
    FritzInternalError,
    FritzLookUpError,
    FritzServiceError,
)

from homeassistant.backports.enum import StrEnum
from homeassistant.const import Platform


class MeshRoles(StrEnum):
    """Available Mesh roles."""

    NONE = "none"
    MASTER = "master"
    SLAVE = "slave"


DOMAIN = "fritz"

PLATFORMS = [
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

CONF_OLD_DISCOVERY = "old_discovery"
DEFAULT_CONF_OLD_DISCOVERY = False

DATA_FRITZ = "fritz_data"

DSL_CONNECTION: Literal["dsl"] = "dsl"

DEFAULT_DEVICE_NAME = "Unknown device"
DEFAULT_HOST = "192.168.178.1"
DEFAULT_PORT = 49000
DEFAULT_USERNAME = ""

ERROR_AUTH_INVALID = "invalid_auth"
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_UPNP_NOT_CONFIGURED = "upnp_not_configured"
ERROR_UNKNOWN = "unknown_error"

FRITZ_SERVICES = "fritz_services"
SERVICE_REBOOT = "reboot"
SERVICE_RECONNECT = "reconnect"
SERVICE_CLEANUP = "cleanup"
SERVICE_SET_GUEST_WIFI_PW = "set_guest_wifi_password"

SWITCH_TYPE_DEFLECTION = "CallDeflection"
SWITCH_TYPE_PORTFORWARD = "PortForward"
SWITCH_TYPE_PROFILE = "Profile"
SWITCH_TYPE_WIFINETWORK = "WiFiNetwork"

UPTIME_DEVIATION = 5

FRITZ_EXCEPTIONS = (
    FritzActionError,
    FritzActionFailedError,
    FritzInternalError,
    FritzServiceError,
    FritzLookUpError,
)

WIFI_STANDARD = {1: "2.4Ghz", 2: "5Ghz", 3: "5Ghz", 4: "Guest"}
