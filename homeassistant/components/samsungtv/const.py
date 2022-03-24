"""Constants for the Samsung TV integration."""
import logging

LOGGER = logging.getLogger(__package__)
DOMAIN = "samsungtv"

ATTR_PROPERTIES = "properties"

DEFAULT_NAME = "Samsung TV"
DEFAULT_MANUFACTURER = "Samsung"

VALUE_CONF_NAME = "HomeAssistant"
VALUE_CONF_ID = "ha.component.samsung"

CONF_DESCRIPTION = "description"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_ON_ACTION = "turn_on_action"
CONF_SESSION_ID = "session_id"

RESULT_AUTH_MISSING = "auth_missing"
RESULT_INVALID_PIN = "invalid_pin"
RESULT_SUCCESS = "success"
RESULT_CANNOT_CONNECT = "cannot_connect"
RESULT_NOT_SUPPORTED = "not_supported"
RESULT_UNKNOWN_HOST = "unknown"

METHOD_LEGACY = "legacy"
METHOD_ENCRYPTED_WEBSOCKET = "encrypted"
METHOD_WEBSOCKET = "websocket"

TIMEOUT_REQUEST = 31
TIMEOUT_WEBSOCKET = 5

LEGACY_PORT = 55000
ENCRYPTED_WEBSOCKET_PORT = 8000
WEBSOCKET_PORTS = (8002, 8001)
