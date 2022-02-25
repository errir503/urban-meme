"""Manifest validation."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from awesomeversion import (
    AwesomeVersion,
    AwesomeVersionException,
    AwesomeVersionStrategy,
)
import voluptuous as vol
from voluptuous.humanize import humanize_error

from homeassistant.helpers import config_validation as cv

from .model import Config, Integration

DOCUMENTATION_URL_SCHEMA = "https"
DOCUMENTATION_URL_HOST = "www.home-assistant.io"
DOCUMENTATION_URL_PATH_PREFIX = "/integrations/"
DOCUMENTATION_URL_EXCEPTIONS = {"https://www.home-assistant.io/hassio"}

SUPPORTED_QUALITY_SCALES = ["gold", "internal", "platinum", "silver"]
SUPPORTED_IOT_CLASSES = [
    "assumed_state",
    "calculated",
    "cloud_polling",
    "cloud_push",
    "local_polling",
    "local_push",
]

# List of integrations that are supposed to have no IoT class
NO_IOT_CLASS = [
    "air_quality",
    "alarm_control_panel",
    "api",
    "auth",
    "automation",
    "binary_sensor",
    "blueprint",
    "button",
    "calendar",
    "camera",
    "climate",
    "color_extractor",
    "config",
    "configurator",
    "counter",
    "cover",
    "default_config",
    "device_automation",
    "device_tracker",
    "diagnostics",
    "discovery",
    "downloader",
    "fan",
    "ffmpeg",
    "frontend",
    "geo_location",
    "history",
    "homeassistant",
    "humidifier",
    "image_processing",
    "image",
    "input_boolean",
    "input_button",
    "input_datetime",
    "input_number",
    "input_select",
    "input_text",
    "intent_script",
    "intent",
    "light",
    "lock",
    "logbook",
    "logger",
    "lovelace",
    "mailbox",
    "map",
    "media_player",
    "media_source",
    "my",
    "notify",
    "number",
    "onboarding",
    "panel_custom",
    "panel_iframe",
    "plant",
    "profiler",
    "proxy",
    "python_script",
    "remote",
    "safe_mode",
    "scene",
    "script",
    "search",
    "select",
    "sensor",
    "siren",
    "stt",
    "switch",
    "system_health",
    "system_log",
    "tag",
    "timer",
    "trace",
    "tts",
    "vacuum",
    "water_heater",
    "weather",
    "webhook",
    "websocket_api",
    "zone",
]


def documentation_url(value: str) -> str:
    """Validate that a documentation url has the correct path and domain."""
    if value in DOCUMENTATION_URL_EXCEPTIONS:
        return value

    parsed_url = urlparse(value)
    if parsed_url.scheme != DOCUMENTATION_URL_SCHEMA:
        raise vol.Invalid("Documentation url is not prefixed with https")
    if parsed_url.netloc == DOCUMENTATION_URL_HOST and not parsed_url.path.startswith(
        DOCUMENTATION_URL_PATH_PREFIX
    ):
        raise vol.Invalid(
            "Documentation url does not begin with www.home-assistant.io/integrations"
        )

    return value


def verify_lowercase(value: str):
    """Verify a value is lowercase."""
    if value.lower() != value:
        raise vol.Invalid("Value needs to be lowercase")

    return value


def verify_uppercase(value: str):
    """Verify a value is uppercase."""
    if value.upper() != value:
        raise vol.Invalid("Value needs to be uppercase")

    return value


def verify_version(value: str):
    """Verify the version."""
    try:
        AwesomeVersion(
            value,
            [
                AwesomeVersionStrategy.CALVER,
                AwesomeVersionStrategy.SEMVER,
                AwesomeVersionStrategy.SIMPLEVER,
                AwesomeVersionStrategy.BUILDVER,
                AwesomeVersionStrategy.PEP440,
            ],
        )
    except AwesomeVersionException:
        raise vol.Invalid(f"'{value}' is not a valid version.")
    return value


def verify_wildcard(value: str):
    """Verify the matcher contains a wildcard."""
    if "*" not in value:
        raise vol.Invalid(f"'{value}' needs to contain a wildcard matcher")
    return value


MANIFEST_SCHEMA = vol.Schema(
    {
        vol.Required("domain"): str,
        vol.Required("name"): str,
        vol.Optional("config_flow"): bool,
        vol.Optional("mqtt"): [str],
        vol.Optional("zeroconf"): [
            vol.Any(
                str,
                vol.All(
                    cv.deprecated("macaddress"),
                    cv.deprecated("model"),
                    cv.deprecated("manufacturer"),
                    vol.Schema(
                        {
                            vol.Required("type"): str,
                            vol.Optional("macaddress"): vol.All(
                                str, verify_uppercase, verify_wildcard
                            ),
                            vol.Optional("manufacturer"): vol.All(
                                str, verify_lowercase
                            ),
                            vol.Optional("model"): vol.All(str, verify_lowercase),
                            vol.Optional("name"): vol.All(str, verify_lowercase),
                            vol.Optional("properties"): vol.Schema(
                                {str: verify_lowercase}
                            ),
                        }
                    ),
                ),
            )
        ],
        vol.Optional("ssdp"): vol.Schema(
            vol.All([vol.All(vol.Schema({}, extra=vol.ALLOW_EXTRA), vol.Length(min=1))])
        ),
        vol.Optional("homekit"): vol.Schema({vol.Optional("models"): [str]}),
        vol.Optional("dhcp"): [
            vol.Schema(
                {
                    vol.Optional("macaddress"): vol.All(
                        str, verify_uppercase, verify_wildcard
                    ),
                    vol.Optional("hostname"): vol.All(str, verify_lowercase),
                    vol.Optional("registered_devices"): cv.boolean,
                }
            )
        ],
        vol.Optional("usb"): [
            vol.Schema(
                {
                    vol.Optional("vid"): vol.All(str, verify_uppercase),
                    vol.Optional("pid"): vol.All(str, verify_uppercase),
                    vol.Optional("serial_number"): vol.All(str, verify_lowercase),
                    vol.Optional("manufacturer"): vol.All(str, verify_lowercase),
                    vol.Optional("description"): vol.All(str, verify_lowercase),
                    vol.Optional("known_devices"): [str],
                }
            )
        ],
        vol.Required("documentation"): vol.All(
            vol.Url(), documentation_url  # pylint: disable=no-value-for-parameter
        ),
        vol.Optional(
            "issue_tracker"
        ): vol.Url(),  # pylint: disable=no-value-for-parameter
        vol.Optional("quality_scale"): vol.In(SUPPORTED_QUALITY_SCALES),
        vol.Optional("requirements"): [str],
        vol.Optional("dependencies"): [str],
        vol.Optional("after_dependencies"): [str],
        vol.Required("codeowners"): [str],
        vol.Optional("loggers"): [str],
        vol.Optional("disabled"): str,
        vol.Optional("iot_class"): vol.In(SUPPORTED_IOT_CLASSES),
        vol.Optional("supported_brands"): vol.Schema({str: str}),
    }
)

CUSTOM_INTEGRATION_MANIFEST_SCHEMA = MANIFEST_SCHEMA.extend(
    {
        vol.Optional("version"): vol.All(str, verify_version),
        vol.Remove("supported_brands"): dict,
    }
)


def validate_version(integration: Integration):
    """
    Validate the version of the integration.

    Will be removed when the version key is no longer optional for custom integrations.
    """
    if not integration.manifest.get("version"):
        integration.add_error("manifest", "No 'version' key in the manifest file.")
        return


def validate_manifest(integration: Integration, core_components_dir: Path) -> None:
    """Validate manifest."""
    if not integration.manifest:
        return

    try:
        if integration.core:
            MANIFEST_SCHEMA(integration.manifest)
        else:
            CUSTOM_INTEGRATION_MANIFEST_SCHEMA(integration.manifest)
    except vol.Invalid as err:
        integration.add_error(
            "manifest", f"Invalid manifest: {humanize_error(integration.manifest, err)}"
        )

    if integration.manifest["domain"] != integration.path.name:
        integration.add_error("manifest", "Domain does not match dir name")

    if (
        not integration.core
        and (core_components_dir / integration.manifest["domain"]).exists()
    ):
        integration.add_warning(
            "manifest", "Domain collides with built-in core integration"
        )

    if (
        integration.manifest["domain"] in NO_IOT_CLASS
        and "iot_class" in integration.manifest
    ):
        integration.add_error("manifest", "Domain should not have an IoT Class")

    if (
        integration.manifest["domain"] not in NO_IOT_CLASS
        and "iot_class" not in integration.manifest
    ):
        integration.add_error("manifest", "Domain is missing an IoT Class")

    for domain, _name in integration.manifest.get("supported_brands", {}).items():
        if (core_components_dir / domain).exists():
            integration.add_warning(
                "manifest",
                f"Supported brand domain {domain} collides with built-in core integration",
            )

    if not integration.core:
        validate_version(integration)


def validate(integrations: dict[str, Integration], config: Config) -> None:
    """Handle all integrations manifests."""
    core_components_dir = config.root / "homeassistant/components"
    for integration in integrations.values():
        validate_manifest(integration, core_components_dir)
