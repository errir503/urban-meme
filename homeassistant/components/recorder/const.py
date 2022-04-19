"""Recorder constants."""

from functools import partial
import json
from typing import Final

from homeassistant.const import ATTR_ATTRIBUTION, ATTR_RESTORED, ATTR_SUPPORTED_FEATURES
from homeassistant.helpers.json import JSONEncoder

DATA_INSTANCE = "recorder_instance"
SQLITE_URL_PREFIX = "sqlite://"
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

JSON_DUMP: Final = partial(json.dumps, cls=JSONEncoder, separators=(",", ":"))

ALL_DOMAIN_EXCLUDE_ATTRS = {ATTR_ATTRIBUTION, ATTR_RESTORED, ATTR_SUPPORTED_FEATURES}
