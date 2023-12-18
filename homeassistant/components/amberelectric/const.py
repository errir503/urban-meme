"""Amber Electric Constants."""
import logging

from homeassistant.const import Platform

DOMAIN = "amberelectric"
CONF_SITE_NAME = "site_name"
CONF_SITE_ID = "site_id"
CONF_SITE_NMI = "site_nmi"

ATTRIBUTION = "Data provided by Amber Electric"

LOGGER = logging.getLogger(__package__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
