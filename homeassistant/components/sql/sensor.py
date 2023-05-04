"""Sensor from an SQL Query."""
from __future__ import annotations

from datetime import date
import decimal
import logging

import sqlalchemy
from sqlalchemy import lambda_stmt
from sqlalchemy.engine import Result
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.sql.lambdas import StatementLambdaElement
from sqlalchemy.util import LRUCache

from homeassistant.components.recorder import (
    CONF_DB_URL,
    SupportedDialect,
    get_instance,
)
from homeassistant.components.sensor import (
    CONF_STATE_CLASS,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_VALUE_TEMPLATE,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import CONF_COLUMN_NAME, CONF_QUERY, DOMAIN
from .models import SQLData
from .util import redact_credentials, resolve_db_url

_LOGGER = logging.getLogger(__name__)

_SQL_LAMBDA_CACHE: LRUCache = LRUCache(1000)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the SQL sensor from yaml."""
    if (conf := discovery_info) is None:
        return

    name: str = conf[CONF_NAME]
    query_str: str = conf[CONF_QUERY]
    unit: str | None = conf.get(CONF_UNIT_OF_MEASUREMENT)
    value_template: Template | None = conf.get(CONF_VALUE_TEMPLATE)
    column_name: str = conf[CONF_COLUMN_NAME]
    unique_id: str | None = conf.get(CONF_UNIQUE_ID)
    db_url: str = resolve_db_url(hass, conf.get(CONF_DB_URL))
    device_class: SensorDeviceClass | None = conf.get(CONF_DEVICE_CLASS)
    state_class: SensorStateClass | None = conf.get(CONF_STATE_CLASS)

    if value_template is not None:
        value_template.hass = hass

    await async_setup_sensor(
        hass,
        name,
        query_str,
        column_name,
        unit,
        value_template,
        unique_id,
        db_url,
        True,
        device_class,
        state_class,
        async_add_entities,
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the SQL sensor from config entry."""

    db_url: str = resolve_db_url(hass, entry.options.get(CONF_DB_URL))
    name: str = entry.options[CONF_NAME]
    query_str: str = entry.options[CONF_QUERY]
    unit: str | None = entry.options.get(CONF_UNIT_OF_MEASUREMENT)
    template: str | None = entry.options.get(CONF_VALUE_TEMPLATE)
    column_name: str = entry.options[CONF_COLUMN_NAME]

    value_template: Template | None = None
    if template is not None:
        try:
            value_template = Template(template)
            value_template.ensure_valid()
        except TemplateError:
            value_template = None
        if value_template is not None:
            value_template.hass = hass

    await async_setup_sensor(
        hass,
        name,
        query_str,
        column_name,
        unit,
        value_template,
        entry.entry_id,
        db_url,
        False,
        None,
        None,
        async_add_entities,
    )


@callback
def _async_get_or_init_domain_data(hass: HomeAssistant) -> SQLData:
    """Get or initialize domain data."""
    if DOMAIN in hass.data:
        sql_data: SQLData = hass.data[DOMAIN]
        return sql_data

    session_makers_by_db_url: dict[str, scoped_session] = {}

    #
    # Ensure we dispose of all engines at shutdown
    # to avoid unclean disconnects
    #
    # Shutdown all sessions in the executor since they will
    # do blocking I/O
    #
    def _shutdown_db_engines(event: Event) -> None:
        """Shutdown all database engines."""
        for sessmaker in session_makers_by_db_url.values():
            sessmaker.connection().engine.dispose()

    cancel_shutdown = hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP, _shutdown_db_engines
    )

    sql_data = SQLData(cancel_shutdown, session_makers_by_db_url)
    hass.data[DOMAIN] = sql_data
    return sql_data


async def async_setup_sensor(
    hass: HomeAssistant,
    name: str,
    query_str: str,
    column_name: str,
    unit: str | None,
    value_template: Template | None,
    unique_id: str | None,
    db_url: str,
    yaml: bool,
    device_class: SensorDeviceClass | None,
    state_class: SensorStateClass | None,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SQL sensor."""
    instance = get_instance(hass)
    sessmaker: scoped_session | None
    sql_data = _async_get_or_init_domain_data(hass)
    uses_recorder_db = db_url == instance.db_url
    use_database_executor = False
    if uses_recorder_db and instance.dialect_name == SupportedDialect.SQLITE:
        use_database_executor = True
        assert instance.engine is not None
        sessmaker = scoped_session(sessionmaker(bind=instance.engine, future=True))
    # For other databases we need to create a new engine since
    # we want the connection to use the default timezone and these
    # database engines will use QueuePool as its only sqlite that
    # needs our custom pool. If there is already a session maker
    # for this db_url we can use that so we do not create a new engine
    # for every sensor.
    elif db_url in sql_data.session_makers_by_db_url:
        sessmaker = sql_data.session_makers_by_db_url[db_url]
    elif sessmaker := await hass.async_add_executor_job(
        _validate_and_get_session_maker_for_db_url, db_url
    ):
        sql_data.session_makers_by_db_url[db_url] = sessmaker
    else:
        return

    upper_query = query_str.upper()
    if uses_recorder_db:
        redacted_query = redact_credentials(query_str)

        issue_key = unique_id if unique_id else redacted_query
        # If the query has a unique id and they fix it we can dismiss the issue
        # but if it doesn't have a unique id they have to ignore it instead

        if (
            "ENTITY_ID," in upper_query or "ENTITY_ID " in upper_query
        ) and "STATES_META" not in upper_query:
            _LOGGER.error(
                "The query `%s` contains the keyword `entity_id` but does not "
                "reference the `states_meta` table. This will cause a full table "
                "scan and database instability. Please check the documentation and use "
                "`states_meta.entity_id` instead",
                redacted_query,
            )

            ir.async_create_issue(
                hass,
                DOMAIN,
                f"entity_id_query_does_full_table_scan_{issue_key}",
                translation_key="entity_id_query_does_full_table_scan",
                translation_placeholders={"query": redacted_query},
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
            )
            raise ValueError(
                "Query contains entity_id but does not reference states_meta"
            )

        ir.async_delete_issue(
            hass, DOMAIN, f"entity_id_query_does_full_table_scan_{issue_key}"
        )

    # MSSQL uses TOP and not LIMIT
    if not ("LIMIT" in upper_query or "SELECT TOP" in upper_query):
        if "mssql" in db_url:
            query_str = upper_query.replace("SELECT", "SELECT TOP 1")
        else:
            query_str = query_str.replace(";", "") + " LIMIT 1;"

    async_add_entities(
        [
            SQLSensor(
                name,
                sessmaker,
                query_str,
                column_name,
                unit,
                value_template,
                unique_id,
                yaml,
                device_class,
                state_class,
                use_database_executor,
            )
        ],
        True,
    )


def _validate_and_get_session_maker_for_db_url(db_url: str) -> scoped_session | None:
    """Validate the db_url and return a session maker.

    This does I/O and should be run in the executor.
    """
    sess: Session | None = None
    try:
        engine = sqlalchemy.create_engine(db_url, future=True)
        sessmaker = scoped_session(sessionmaker(bind=engine, future=True))
        # Run a dummy query just to test the db_url
        sess = sessmaker()
        sess.execute(sqlalchemy.text("SELECT 1;"))

    except SQLAlchemyError as err:
        _LOGGER.error(
            "Couldn't connect using %s DB_URL: %s",
            redact_credentials(db_url),
            redact_credentials(str(err)),
        )
        return None
    else:
        return sessmaker
    finally:
        if sess:
            sess.close()


def _generate_lambda_stmt(query: str) -> StatementLambdaElement:
    """Generate the lambda statement."""
    text = sqlalchemy.text(query)
    return lambda_stmt(lambda: text, lambda_cache=_SQL_LAMBDA_CACHE)


class SQLSensor(SensorEntity):
    """Representation of an SQL sensor."""

    _attr_icon = "mdi:database-search"
    _attr_has_entity_name = True

    def __init__(
        self,
        name: str,
        sessmaker: scoped_session,
        query: str,
        column: str,
        unit: str | None,
        value_template: Template | None,
        unique_id: str | None,
        yaml: bool,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass | None,
        use_database_executor: bool,
    ) -> None:
        """Initialize the SQL sensor."""
        self._query = query
        self._attr_name = name if yaml else None
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._template = value_template
        self._column_name = column
        self.sessionmaker = sessmaker
        self._attr_extra_state_attributes = {}
        self._attr_unique_id = unique_id
        self._use_database_executor = use_database_executor
        self._lambda_stmt = _generate_lambda_stmt(query)
        if not yaml and unique_id:
            self._attr_device_info = DeviceInfo(
                entry_type=DeviceEntryType.SERVICE,
                identifiers={(DOMAIN, unique_id)},
                manufacturer="SQL",
                name=name,
            )

    async def async_update(self) -> None:
        """Retrieve sensor data from the query using the right executor."""
        if self._use_database_executor:
            await get_instance(self.hass).async_add_executor_job(self._update)
        else:
            await self.hass.async_add_executor_job(self._update)

    def _update(self) -> None:
        """Retrieve sensor data from the query."""
        data = None
        self._attr_extra_state_attributes = {}
        sess: scoped_session = self.sessionmaker()
        try:
            result: Result = sess.execute(self._lambda_stmt)
        except SQLAlchemyError as err:
            _LOGGER.error(
                "Error executing query %s: %s",
                self._query,
                redact_credentials(str(err)),
            )
            return

        for res in result.mappings():
            _LOGGER.debug("Query %s result in %s", self._query, res.items())
            data = res[self._column_name]
            for key, value in res.items():
                if isinstance(value, decimal.Decimal):
                    value = float(value)
                elif isinstance(value, date):
                    value = value.isoformat()
                elif isinstance(value, (bytes, bytearray)):
                    value = f"0x{value.hex()}"
                self._attr_extra_state_attributes[key] = value

        if data is not None and isinstance(data, (bytes, bytearray)):
            data = f"0x{data.hex()}"

        if data is not None and self._template is not None:
            self._attr_native_value = (
                self._template.async_render_with_possible_json_value(data, None)
            )
        else:
            self._attr_native_value = data

        if data is None:
            _LOGGER.warning("%s returned no results", self._query)

        sess.close()
