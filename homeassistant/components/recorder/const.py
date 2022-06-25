"""Recorder constants."""

from homeassistant.backports.enum import StrEnum
from homeassistant.const import ATTR_ATTRIBUTION, ATTR_RESTORED, ATTR_SUPPORTED_FEATURES
from homeassistant.helpers.json import (  # noqa: F401 pylint: disable=unused-import
    JSON_DUMP,
)

DATA_INSTANCE = "recorder_instance"
SQLITE_URL_PREFIX = "sqlite://"
MYSQLDB_URL_PREFIX = "mysql://"
DOMAIN = "recorder"

CONF_DB_INTEGRITY_CHECK = "db_integrity_check"

MAX_QUEUE_BACKLOG = 40000

# The maximum number of rows (events) we purge in one delete statement

# sqlite3 has a limit of 999 until version 3.32.0
# in https://github.com/sqlite/sqlite/commit/efdba1a8b3c6c967e7fae9c1989c40d420ce64cc
# We can increase this back to 1000 once most
# have upgraded their sqlite version
MAX_ROWS_TO_PURGE = 998

DB_WORKER_PREFIX = "DbWorker"

ALL_DOMAIN_EXCLUDE_ATTRS = {ATTR_ATTRIBUTION, ATTR_RESTORED, ATTR_SUPPORTED_FEATURES}

ATTR_KEEP_DAYS = "keep_days"
ATTR_REPACK = "repack"
ATTR_APPLY_FILTER = "apply_filter"

KEEPALIVE_TIME = 30


EXCLUDE_ATTRIBUTES = f"{DOMAIN}_exclude_attributes_by_domain"


class SupportedDialect(StrEnum):
    """Supported dialects."""

    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
