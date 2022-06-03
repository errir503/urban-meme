"""Models for SQLAlchemy."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import json
import logging
from typing import Any, TypedDict, cast, overload

import ciso8601
from fnvhash import fnv1a_32
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    distinct,
    type_coerce,
)
from sqlalchemy.dialects import mysql, oracle, postgresql, sqlite
from sqlalchemy.engine.row import Row
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import aliased, declarative_base, relationship
from sqlalchemy.orm.session import Session

from homeassistant.components.websocket_api.const import (
    COMPRESSED_STATE_ATTRIBUTES,
    COMPRESSED_STATE_LAST_CHANGED,
    COMPRESSED_STATE_LAST_UPDATED,
    COMPRESSED_STATE_STATE,
)
from homeassistant.const import (
    MAX_LENGTH_EVENT_CONTEXT_ID,
    MAX_LENGTH_EVENT_EVENT_TYPE,
    MAX_LENGTH_EVENT_ORIGIN,
    MAX_LENGTH_STATE_ENTITY_ID,
    MAX_LENGTH_STATE_STATE,
)
from homeassistant.core import Context, Event, EventOrigin, State, split_entity_id
import homeassistant.util.dt as dt_util

from .const import ALL_DOMAIN_EXCLUDE_ATTRS, JSON_DUMP

# SQLAlchemy Schema
# pylint: disable=invalid-name
Base = declarative_base()

SCHEMA_VERSION = 29

_LOGGER = logging.getLogger(__name__)

DB_TIMEZONE = "+00:00"

TABLE_EVENTS = "events"
TABLE_EVENT_DATA = "event_data"
TABLE_STATES = "states"
TABLE_STATE_ATTRIBUTES = "state_attributes"
TABLE_RECORDER_RUNS = "recorder_runs"
TABLE_SCHEMA_CHANGES = "schema_changes"
TABLE_STATISTICS = "statistics"
TABLE_STATISTICS_META = "statistics_meta"
TABLE_STATISTICS_RUNS = "statistics_runs"
TABLE_STATISTICS_SHORT_TERM = "statistics_short_term"

ALL_TABLES = [
    TABLE_STATES,
    TABLE_STATE_ATTRIBUTES,
    TABLE_EVENTS,
    TABLE_EVENT_DATA,
    TABLE_RECORDER_RUNS,
    TABLE_SCHEMA_CHANGES,
    TABLE_STATISTICS,
    TABLE_STATISTICS_META,
    TABLE_STATISTICS_RUNS,
    TABLE_STATISTICS_SHORT_TERM,
]

TABLES_TO_CHECK = [
    TABLE_STATES,
    TABLE_EVENTS,
    TABLE_RECORDER_RUNS,
    TABLE_SCHEMA_CHANGES,
]

LAST_UPDATED_INDEX = "ix_states_last_updated"
ENTITY_ID_LAST_UPDATED_INDEX = "ix_states_entity_id_last_updated"
EVENTS_CONTEXT_ID_INDEX = "ix_events_context_id"
STATES_CONTEXT_ID_INDEX = "ix_states_context_id"

EMPTY_JSON_OBJECT = "{}"


class FAST_PYSQLITE_DATETIME(sqlite.DATETIME):  # type: ignore[misc]
    """Use ciso8601 to parse datetimes instead of sqlalchemy built-in regex."""

    def result_processor(self, dialect, coltype):  # type: ignore[no-untyped-def]
        """Offload the datetime parsing to ciso8601."""
        return lambda value: None if value is None else ciso8601.parse_datetime(value)


JSON_VARIENT_CAST = Text().with_variant(
    postgresql.JSON(none_as_null=True), "postgresql"
)
JSONB_VARIENT_CAST = Text().with_variant(
    postgresql.JSONB(none_as_null=True), "postgresql"
)
DATETIME_TYPE = (
    DateTime(timezone=True)
    .with_variant(mysql.DATETIME(timezone=True, fsp=6), "mysql")
    .with_variant(FAST_PYSQLITE_DATETIME(), "sqlite")
)
DOUBLE_TYPE = (
    Float()
    .with_variant(mysql.DOUBLE(asdecimal=False), "mysql")
    .with_variant(oracle.DOUBLE_PRECISION(), "oracle")
    .with_variant(postgresql.DOUBLE_PRECISION(), "postgresql")
)


class JSONLiteral(JSON):  # type: ignore[misc]
    """Teach SA how to literalize json."""

    def literal_processor(self, dialect: str) -> Callable[[Any], str]:
        """Processor to convert a value to JSON."""

        def process(value: Any) -> str:
            """Dump json."""
            return json.dumps(value)

        return process


EVENT_ORIGIN_ORDER = [EventOrigin.local, EventOrigin.remote]
EVENT_ORIGIN_TO_IDX = {origin: idx for idx, origin in enumerate(EVENT_ORIGIN_ORDER)}


class UnsupportedDialect(Exception):
    """The dialect or its version is not supported."""


class Events(Base):  # type: ignore[misc,valid-type]
    """Event history data."""

    __table_args__ = (
        # Used for fetching events at a specific time
        # see logbook
        Index("ix_events_event_type_time_fired", "event_type", "time_fired"),
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_EVENTS
    event_id = Column(Integer, Identity(), primary_key=True)
    event_type = Column(String(MAX_LENGTH_EVENT_EVENT_TYPE))
    event_data = Column(Text().with_variant(mysql.LONGTEXT, "mysql"))
    origin = Column(String(MAX_LENGTH_EVENT_ORIGIN))  # no longer used for new rows
    origin_idx = Column(SmallInteger)
    time_fired = Column(DATETIME_TYPE, index=True)
    context_id = Column(String(MAX_LENGTH_EVENT_CONTEXT_ID), index=True)
    context_user_id = Column(String(MAX_LENGTH_EVENT_CONTEXT_ID))
    context_parent_id = Column(String(MAX_LENGTH_EVENT_CONTEXT_ID))
    data_id = Column(Integer, ForeignKey("event_data.data_id"), index=True)
    event_data_rel = relationship("EventData")

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            f"<recorder.Events("
            f"id={self.event_id}, type='{self.event_type}', "
            f"origin_idx='{self.origin_idx}', time_fired='{self.time_fired}'"
            f", data_id={self.data_id})>"
        )

    @staticmethod
    def from_event(event: Event) -> Events:
        """Create an event database object from a native event."""
        return Events(
            event_type=event.event_type,
            event_data=None,
            origin_idx=EVENT_ORIGIN_TO_IDX.get(event.origin),
            time_fired=event.time_fired,
            context_id=event.context.id,
            context_user_id=event.context.user_id,
            context_parent_id=event.context.parent_id,
        )

    def to_native(self, validate_entity_id: bool = True) -> Event | None:
        """Convert to a native HA Event."""
        context = Context(
            id=self.context_id,
            user_id=self.context_user_id,
            parent_id=self.context_parent_id,
        )
        try:
            return Event(
                self.event_type,
                json.loads(self.event_data) if self.event_data else {},
                EventOrigin(self.origin)
                if self.origin
                else EVENT_ORIGIN_ORDER[self.origin_idx],
                process_timestamp(self.time_fired),
                context=context,
            )
        except ValueError:
            # When json.loads fails
            _LOGGER.exception("Error converting to event: %s", self)
            return None


class EventData(Base):  # type: ignore[misc,valid-type]
    """Event data history."""

    __table_args__ = (
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_EVENT_DATA
    data_id = Column(Integer, Identity(), primary_key=True)
    hash = Column(BigInteger, index=True)
    # Note that this is not named attributes to avoid confusion with the states table
    shared_data = Column(Text().with_variant(mysql.LONGTEXT, "mysql"))

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            f"<recorder.EventData("
            f"id={self.data_id}, hash='{self.hash}', data='{self.shared_data}'"
            f")>"
        )

    @staticmethod
    def from_event(event: Event) -> EventData:
        """Create object from an event."""
        shared_data = JSON_DUMP(event.data)
        return EventData(
            shared_data=shared_data, hash=EventData.hash_shared_data(shared_data)
        )

    @staticmethod
    def shared_data_from_event(event: Event) -> str:
        """Create shared_attrs from an event."""
        return JSON_DUMP(event.data)

    @staticmethod
    def hash_shared_data(shared_data: str) -> int:
        """Return the hash of json encoded shared data."""
        return cast(int, fnv1a_32(shared_data.encode("utf-8")))

    def to_native(self) -> dict[str, Any]:
        """Convert to an HA state object."""
        try:
            return cast(dict[str, Any], json.loads(self.shared_data))
        except ValueError:
            _LOGGER.exception("Error converting row to event data: %s", self)
            return {}


class States(Base):  # type: ignore[misc,valid-type]
    """State change history."""

    __table_args__ = (
        # Used for fetching the state of entities at a specific time
        # (get_states in history.py)
        Index(ENTITY_ID_LAST_UPDATED_INDEX, "entity_id", "last_updated"),
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_STATES
    state_id = Column(Integer, Identity(), primary_key=True)
    entity_id = Column(String(MAX_LENGTH_STATE_ENTITY_ID))
    state = Column(String(MAX_LENGTH_STATE_STATE))
    attributes = Column(
        Text().with_variant(mysql.LONGTEXT, "mysql")
    )  # no longer used for new rows
    event_id = Column(  # no longer used for new rows
        Integer, ForeignKey("events.event_id", ondelete="CASCADE"), index=True
    )
    last_changed = Column(DATETIME_TYPE)
    last_updated = Column(DATETIME_TYPE, default=dt_util.utcnow, index=True)
    old_state_id = Column(Integer, ForeignKey("states.state_id"), index=True)
    attributes_id = Column(
        Integer, ForeignKey("state_attributes.attributes_id"), index=True
    )
    context_id = Column(String(MAX_LENGTH_EVENT_CONTEXT_ID), index=True)
    context_user_id = Column(String(MAX_LENGTH_EVENT_CONTEXT_ID))
    context_parent_id = Column(String(MAX_LENGTH_EVENT_CONTEXT_ID))
    origin_idx = Column(SmallInteger)  # 0 is local, 1 is remote
    old_state = relationship("States", remote_side=[state_id])
    state_attributes = relationship("StateAttributes")

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            f"<recorder.States("
            f"id={self.state_id}, entity_id='{self.entity_id}', "
            f"state='{self.state}', event_id='{self.event_id}', "
            f"last_updated='{self.last_updated.isoformat(sep=' ', timespec='seconds')}', "
            f"old_state_id={self.old_state_id}, attributes_id={self.attributes_id}"
            f")>"
        )

    @staticmethod
    def from_event(event: Event) -> States:
        """Create object from a state_changed event."""
        entity_id = event.data["entity_id"]
        state: State | None = event.data.get("new_state")
        dbstate = States(
            entity_id=entity_id,
            attributes=None,
            context_id=event.context.id,
            context_user_id=event.context.user_id,
            context_parent_id=event.context.parent_id,
            origin_idx=EVENT_ORIGIN_TO_IDX.get(event.origin),
        )

        # None state means the state was removed from the state machine
        if state is None:
            dbstate.state = ""
            dbstate.last_updated = event.time_fired
            dbstate.last_changed = None
            return dbstate

        dbstate.state = state.state
        dbstate.last_updated = state.last_updated
        if state.last_updated == state.last_changed:
            dbstate.last_changed = None
        else:
            dbstate.last_changed = state.last_changed

        return dbstate

    def to_native(self, validate_entity_id: bool = True) -> State | None:
        """Convert to an HA state object."""
        context = Context(
            id=self.context_id,
            user_id=self.context_user_id,
            parent_id=self.context_parent_id,
        )
        try:
            attrs = json.loads(self.attributes) if self.attributes else {}
        except ValueError:
            # When json.loads fails
            _LOGGER.exception("Error converting row to state: %s", self)
            return None
        if self.last_changed is None or self.last_changed == self.last_updated:
            last_changed = last_updated = process_timestamp(self.last_updated)
        else:
            last_updated = process_timestamp(self.last_updated)
            last_changed = process_timestamp(self.last_changed)
        return State(
            self.entity_id,
            self.state,
            # Join the state_attributes table on attributes_id to get the attributes
            # for newer states
            attrs,
            last_changed,
            last_updated,
            context=context,
            validate_entity_id=validate_entity_id,
        )


class StateAttributes(Base):  # type: ignore[misc,valid-type]
    """State attribute change history."""

    __table_args__ = (
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_STATE_ATTRIBUTES
    attributes_id = Column(Integer, Identity(), primary_key=True)
    hash = Column(BigInteger, index=True)
    # Note that this is not named attributes to avoid confusion with the states table
    shared_attrs = Column(Text().with_variant(mysql.LONGTEXT, "mysql"))

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            f"<recorder.StateAttributes("
            f"id={self.attributes_id}, hash='{self.hash}', attributes='{self.shared_attrs}'"
            f")>"
        )

    @staticmethod
    def from_event(event: Event) -> StateAttributes:
        """Create object from a state_changed event."""
        state: State | None = event.data.get("new_state")
        # None state means the state was removed from the state machine
        dbstate = StateAttributes(
            shared_attrs="{}" if state is None else JSON_DUMP(state.attributes)
        )
        dbstate.hash = StateAttributes.hash_shared_attrs(dbstate.shared_attrs)
        return dbstate

    @staticmethod
    def shared_attrs_from_event(
        event: Event, exclude_attrs_by_domain: dict[str, set[str]]
    ) -> str:
        """Create shared_attrs from a state_changed event."""
        state: State | None = event.data.get("new_state")
        # None state means the state was removed from the state machine
        if state is None:
            return "{}"
        domain = split_entity_id(state.entity_id)[0]
        exclude_attrs = (
            exclude_attrs_by_domain.get(domain, set()) | ALL_DOMAIN_EXCLUDE_ATTRS
        )
        return JSON_DUMP(
            {k: v for k, v in state.attributes.items() if k not in exclude_attrs}
        )

    @staticmethod
    def hash_shared_attrs(shared_attrs: str) -> int:
        """Return the hash of json encoded shared attributes."""
        return cast(int, fnv1a_32(shared_attrs.encode("utf-8")))

    def to_native(self) -> dict[str, Any]:
        """Convert to an HA state object."""
        try:
            return cast(dict[str, Any], json.loads(self.shared_attrs))
        except ValueError:
            # When json.loads fails
            _LOGGER.exception("Error converting row to state attributes: %s", self)
            return {}


class StatisticResult(TypedDict):
    """Statistic result data class.

    Allows multiple datapoints for the same statistic_id.
    """

    meta: StatisticMetaData
    stat: StatisticData


class StatisticDataBase(TypedDict):
    """Mandatory fields for statistic data class."""

    start: datetime


class StatisticData(StatisticDataBase, total=False):
    """Statistic data class."""

    mean: float
    min: float
    max: float
    last_reset: datetime | None
    state: float
    sum: float


class StatisticsBase:
    """Statistics base class."""

    id = Column(Integer, Identity(), primary_key=True)
    created = Column(DATETIME_TYPE, default=dt_util.utcnow)

    @declared_attr  # type: ignore[misc]
    def metadata_id(self) -> Column:
        """Define the metadata_id column for sub classes."""
        return Column(
            Integer,
            ForeignKey(f"{TABLE_STATISTICS_META}.id", ondelete="CASCADE"),
            index=True,
        )

    start = Column(DATETIME_TYPE, index=True)
    mean = Column(DOUBLE_TYPE)
    min = Column(DOUBLE_TYPE)
    max = Column(DOUBLE_TYPE)
    last_reset = Column(DATETIME_TYPE)
    state = Column(DOUBLE_TYPE)
    sum = Column(DOUBLE_TYPE)

    @classmethod
    def from_stats(cls, metadata_id: int, stats: StatisticData) -> StatisticsBase:
        """Create object from a statistics."""
        return cls(  # type: ignore[call-arg,misc]
            metadata_id=metadata_id,
            **stats,
        )


class Statistics(Base, StatisticsBase):  # type: ignore[misc,valid-type]
    """Long term statistics."""

    duration = timedelta(hours=1)

    __table_args__ = (
        # Used for fetching statistics for a certain entity at a specific time
        Index("ix_statistics_statistic_id_start", "metadata_id", "start", unique=True),
    )
    __tablename__ = TABLE_STATISTICS


class StatisticsShortTerm(Base, StatisticsBase):  # type: ignore[misc,valid-type]
    """Short term statistics."""

    duration = timedelta(minutes=5)

    __table_args__ = (
        # Used for fetching statistics for a certain entity at a specific time
        Index(
            "ix_statistics_short_term_statistic_id_start",
            "metadata_id",
            "start",
            unique=True,
        ),
    )
    __tablename__ = TABLE_STATISTICS_SHORT_TERM


class StatisticMetaData(TypedDict):
    """Statistic meta data class."""

    has_mean: bool
    has_sum: bool
    name: str | None
    source: str
    statistic_id: str
    unit_of_measurement: str | None


class StatisticsMeta(Base):  # type: ignore[misc,valid-type]
    """Statistics meta data."""

    __table_args__ = (
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_STATISTICS_META
    id = Column(Integer, Identity(), primary_key=True)
    statistic_id = Column(String(255), index=True, unique=True)
    source = Column(String(32))
    unit_of_measurement = Column(String(255))
    has_mean = Column(Boolean)
    has_sum = Column(Boolean)
    name = Column(String(255))

    @staticmethod
    def from_meta(meta: StatisticMetaData) -> StatisticsMeta:
        """Create object from meta data."""
        return StatisticsMeta(**meta)


class RecorderRuns(Base):  # type: ignore[misc,valid-type]
    """Representation of recorder run."""

    __table_args__ = (Index("ix_recorder_runs_start_end", "start", "end"),)
    __tablename__ = TABLE_RECORDER_RUNS
    run_id = Column(Integer, Identity(), primary_key=True)
    start = Column(DateTime(timezone=True), default=dt_util.utcnow)
    end = Column(DateTime(timezone=True))
    closed_incorrect = Column(Boolean, default=False)
    created = Column(DateTime(timezone=True), default=dt_util.utcnow)

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        end = (
            f"'{self.end.isoformat(sep=' ', timespec='seconds')}'" if self.end else None
        )
        return (
            f"<recorder.RecorderRuns("
            f"id={self.run_id}, start='{self.start.isoformat(sep=' ', timespec='seconds')}', "
            f"end={end}, closed_incorrect={self.closed_incorrect}, "
            f"created='{self.created.isoformat(sep=' ', timespec='seconds')}'"
            f")>"
        )

    def entity_ids(self, point_in_time: datetime | None = None) -> list[str]:
        """Return the entity ids that existed in this run.

        Specify point_in_time if you want to know which existed at that point
        in time inside the run.
        """
        session = Session.object_session(self)

        assert session is not None, "RecorderRuns need to be persisted"

        query = session.query(distinct(States.entity_id)).filter(
            States.last_updated >= self.start
        )

        if point_in_time is not None:
            query = query.filter(States.last_updated < point_in_time)
        elif self.end is not None:
            query = query.filter(States.last_updated < self.end)

        return [row[0] for row in query]

    def to_native(self, validate_entity_id: bool = True) -> RecorderRuns:
        """Return self, native format is this model."""
        return self


class SchemaChanges(Base):  # type: ignore[misc,valid-type]
    """Representation of schema version changes."""

    __tablename__ = TABLE_SCHEMA_CHANGES
    change_id = Column(Integer, Identity(), primary_key=True)
    schema_version = Column(Integer)
    changed = Column(DateTime(timezone=True), default=dt_util.utcnow)

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            f"<recorder.SchemaChanges("
            f"id={self.change_id}, schema_version={self.schema_version}, "
            f"changed='{self.changed.isoformat(sep=' ', timespec='seconds')}'"
            f")>"
        )


class StatisticsRuns(Base):  # type: ignore[misc,valid-type]
    """Representation of statistics run."""

    __tablename__ = TABLE_STATISTICS_RUNS
    run_id = Column(Integer, Identity(), primary_key=True)
    start = Column(DateTime(timezone=True), index=True)

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            f"<recorder.StatisticsRuns("
            f"id={self.run_id}, start='{self.start.isoformat(sep=' ', timespec='seconds')}', "
            f")>"
        )


EVENT_DATA_JSON = type_coerce(
    EventData.shared_data.cast(JSONB_VARIENT_CAST), JSONLiteral(none_as_null=True)
)
OLD_FORMAT_EVENT_DATA_JSON = type_coerce(
    Events.event_data.cast(JSONB_VARIENT_CAST), JSONLiteral(none_as_null=True)
)

SHARED_ATTRS_JSON = type_coerce(
    StateAttributes.shared_attrs.cast(JSON_VARIENT_CAST), JSON(none_as_null=True)
)
OLD_FORMAT_ATTRS_JSON = type_coerce(
    States.attributes.cast(JSON_VARIENT_CAST), JSON(none_as_null=True)
)

ENTITY_ID_IN_EVENT: Column = EVENT_DATA_JSON["entity_id"]
OLD_ENTITY_ID_IN_EVENT: Column = OLD_FORMAT_EVENT_DATA_JSON["entity_id"]
DEVICE_ID_IN_EVENT: Column = EVENT_DATA_JSON["device_id"]
OLD_STATE = aliased(States, name="old_state")


@overload
def process_timestamp(ts: None) -> None:
    ...


@overload
def process_timestamp(ts: datetime) -> datetime:
    ...


def process_timestamp(ts: datetime | None) -> datetime | None:
    """Process a timestamp into datetime object."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=dt_util.UTC)

    return dt_util.as_utc(ts)


@overload
def process_timestamp_to_utc_isoformat(ts: None) -> None:
    ...


@overload
def process_timestamp_to_utc_isoformat(ts: datetime) -> str:
    ...


def process_timestamp_to_utc_isoformat(ts: datetime | None) -> str | None:
    """Process a timestamp into UTC isotime."""
    if ts is None:
        return None
    if ts.tzinfo == dt_util.UTC:
        return ts.isoformat()
    if ts.tzinfo is None:
        return f"{ts.isoformat()}{DB_TIMEZONE}"
    return ts.astimezone(dt_util.UTC).isoformat()


def process_datetime_to_timestamp(ts: datetime) -> float:
    """Process a datebase datetime to epoch.

    Mirrors the behavior of process_timestamp_to_utc_isoformat
    except it returns the epoch time.
    """
    if ts.tzinfo is None or ts.tzinfo == dt_util.UTC:
        return dt_util.utc_to_timestamp(ts)
    return ts.timestamp()


class LazyState(State):
    """A lazy version of core State."""

    __slots__ = [
        "_row",
        "_attributes",
        "_last_changed",
        "_last_updated",
        "_context",
        "attr_cache",
    ]

    def __init__(  # pylint: disable=super-init-not-called
        self,
        row: Row,
        attr_cache: dict[str, dict[str, Any]],
        start_time: datetime | None = None,
    ) -> None:
        """Init the lazy state."""
        self._row = row
        self.entity_id: str = self._row.entity_id
        self.state = self._row.state or ""
        self._attributes: dict[str, Any] | None = None
        self._last_changed: datetime | None = start_time
        self._last_updated: datetime | None = start_time
        self._context: Context | None = None
        self.attr_cache = attr_cache

    @property  # type: ignore[override]
    def attributes(self) -> dict[str, Any]:  # type: ignore[override]
        """State attributes."""
        if self._attributes is None:
            self._attributes = decode_attributes_from_row(self._row, self.attr_cache)
        return self._attributes

    @attributes.setter
    def attributes(self, value: dict[str, Any]) -> None:
        """Set attributes."""
        self._attributes = value

    @property  # type: ignore[override]
    def context(self) -> Context:  # type: ignore[override]
        """State context."""
        if self._context is None:
            self._context = Context(id=None)
        return self._context

    @context.setter
    def context(self, value: Context) -> None:
        """Set context."""
        self._context = value

    @property  # type: ignore[override]
    def last_changed(self) -> datetime:  # type: ignore[override]
        """Last changed datetime."""
        if self._last_changed is None:
            if (last_changed := self._row.last_changed) is not None:
                self._last_changed = process_timestamp(last_changed)
            else:
                self._last_changed = self.last_updated
        return self._last_changed

    @last_changed.setter
    def last_changed(self, value: datetime) -> None:
        """Set last changed datetime."""
        self._last_changed = value

    @property  # type: ignore[override]
    def last_updated(self) -> datetime:  # type: ignore[override]
        """Last updated datetime."""
        if self._last_updated is None:
            self._last_updated = process_timestamp(self._row.last_updated)
        return self._last_updated

    @last_updated.setter
    def last_updated(self, value: datetime) -> None:
        """Set last updated datetime."""
        self._last_updated = value

    def as_dict(self) -> dict[str, Any]:  # type: ignore[override]
        """Return a dict representation of the LazyState.

        Async friendly.

        To be used for JSON serialization.
        """
        if self._last_changed is None and self._last_updated is None:
            last_updated_isoformat = process_timestamp_to_utc_isoformat(
                self._row.last_updated
            )
            if (
                self._row.last_changed is None
                or self._row.last_changed == self._row.last_updated
            ):
                last_changed_isoformat = last_updated_isoformat
            else:
                last_changed_isoformat = process_timestamp_to_utc_isoformat(
                    self._row.last_changed
                )
        else:
            last_updated_isoformat = self.last_updated.isoformat()
            if self.last_changed == self.last_updated:
                last_changed_isoformat = last_updated_isoformat
            else:
                last_changed_isoformat = self.last_changed.isoformat()
        return {
            "entity_id": self.entity_id,
            "state": self.state,
            "attributes": self._attributes or self.attributes,
            "last_changed": last_changed_isoformat,
            "last_updated": last_updated_isoformat,
        }

    def __eq__(self, other: Any) -> bool:
        """Return the comparison."""
        return (
            other.__class__ in [self.__class__, State]
            and self.entity_id == other.entity_id
            and self.state == other.state
            and self.attributes == other.attributes
        )


def decode_attributes_from_row(
    row: Row, attr_cache: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Decode attributes from a database row."""
    source: str = row.shared_attrs or row.attributes
    if (attributes := attr_cache.get(source)) is not None:
        return attributes
    if not source or source == EMPTY_JSON_OBJECT:
        return {}
    try:
        attr_cache[source] = attributes = json.loads(source)
    except ValueError:
        _LOGGER.exception("Error converting row to state attributes: %s", source)
        attr_cache[source] = attributes = {}
    return attributes


def row_to_compressed_state(
    row: Row,
    attr_cache: dict[str, dict[str, Any]],
    start_time: datetime | None = None,
) -> dict[str, Any]:
    """Convert a database row to a compressed state."""
    comp_state = {
        COMPRESSED_STATE_STATE: row.state,
        COMPRESSED_STATE_ATTRIBUTES: decode_attributes_from_row(row, attr_cache),
    }
    if start_time:
        comp_state[COMPRESSED_STATE_LAST_UPDATED] = start_time.timestamp()
    else:
        row_last_updated: datetime = row.last_updated
        comp_state[COMPRESSED_STATE_LAST_UPDATED] = process_datetime_to_timestamp(
            row_last_updated
        )
        if (
            row_changed_changed := row.last_changed
        ) and row_last_updated != row_changed_changed:
            comp_state[COMPRESSED_STATE_LAST_CHANGED] = process_datetime_to_timestamp(
                row_changed_changed
            )
    return comp_state
