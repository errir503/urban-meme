"""Recorder constants."""

from homeassistant.backports.enum import StrEnum
from homeassistant.const import ATTR_ATTRIBUTION, ATTR_RESTORED, ATTR_SUPPORTED_FEATURES
from homeassistant.helpers.json import (  # noqa: F401 pylint: disable=unused-import
    JSON_DUMP,
)

DATA_INSTANCE = "recorder_instance"
SQLITE_URL_PREFIX = "sqlite://"
MARIADB_URL_PREFIX = "mariadb://"
MARIADB_PYMYSQL_URL_PREFIX = "mariadb+pymysql://"
MYSQLDB_URL_PREFIX = "mysql://"
MYSQLDB_PYMYSQL_URL_PREFIX = "mysql+pymysql://"
DOMAIN = "recorder"

EVENT_RECORDER_5MIN_STATISTICS_GENERATED = "recorder_5min_statistics_generated"
EVENT_RECORDER_HOURLY_STATISTICS_GENERATED = "recorder_hourly_statistics_generated"

CONF_DB_INTEGRITY_CHECK = "db_integrity_check"

MAX_QUEUE_BACKLOG = 65000

# The maximum number of rows (events) we purge in one delete statement

# sqlite3 has a limit of 999 until version 3.32.0
# in https://github.com/sqlite/sqlite/commit/efdba1a8b3c6c967e7fae9c1989c40d420ce64cc
# We can increase this back to 1000 once most
# have upgraded their sqlite version
SQLITE_MAX_BIND_VARS = 998

DB_WORKER_PREFIX = "DbWorker"

ALL_DOMAIN_EXCLUDE_ATTRS = {ATTR_ATTRIBUTION, ATTR_RESTORED, ATTR_SUPPORTED_FEATURES}

ATTR_KEEP_DAYS = "keep_days"
ATTR_REPACK = "repack"
ATTR_APPLY_FILTER = "apply_filter"

KEEPALIVE_TIME = 30


EXCLUDE_ATTRIBUTES = f"{DOMAIN}_exclude_attributes_by_domain"


STATISTICS_ROWS_SCHEMA_VERSION = 23
CONTEXT_ID_AS_BINARY_SCHEMA_VERSION = 36
EVENT_TYPE_IDS_SCHEMA_VERSION = 37
STATES_META_SCHEMA_VERSION = 38

LEGACY_STATES_EVENT_ID_INDEX_SCHEMA_VERSION = 28


INTEGRATION_PLATFORM_EXCLUDE_ATTRIBUTES = "exclude_attributes"

INTEGRATION_PLATFORM_COMPILE_STATISTICS = "compile_statistics"
INTEGRATION_PLATFORM_VALIDATE_STATISTICS = "validate_statistics"
INTEGRATION_PLATFORM_LIST_STATISTIC_IDS = "list_statistic_ids"

INTEGRATION_PLATFORMS_LOAD_IN_RECORDER_THREAD = {
    INTEGRATION_PLATFORM_COMPILE_STATISTICS,
    INTEGRATION_PLATFORM_VALIDATE_STATISTICS,
    INTEGRATION_PLATFORM_LIST_STATISTIC_IDS,
}


class SupportedDialect(StrEnum):
    """Supported dialects."""

    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
