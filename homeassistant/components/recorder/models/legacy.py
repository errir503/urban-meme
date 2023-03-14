"""Models for Recorder."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.engine.row import Row

from homeassistant.const import (
    COMPRESSED_STATE_ATTRIBUTES,
    COMPRESSED_STATE_LAST_CHANGED,
    COMPRESSED_STATE_LAST_UPDATED,
    COMPRESSED_STATE_STATE,
)
from homeassistant.core import Context, State

from .state_attributes import decode_attributes_from_row
from .time import (
    process_datetime_to_timestamp,
    process_timestamp,
    process_timestamp_to_utc_isoformat,
)

# pylint: disable=invalid-name


class LazyStatePreSchema31(State):
    """A lazy version of core State before schema 31."""

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
        start_time: datetime | None,
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
    def attributes(self) -> dict[str, Any]:
        """State attributes."""
        if self._attributes is None:
            self._attributes = decode_attributes_from_row(self._row, self.attr_cache)
        return self._attributes

    @attributes.setter
    def attributes(self, value: dict[str, Any]) -> None:
        """Set attributes."""
        self._attributes = value

    @property
    def context(self) -> Context:
        """State context."""
        if self._context is None:
            self._context = Context(id=None)
        return self._context

    @context.setter
    def context(self, value: Context) -> None:
        """Set context."""
        self._context = value

    @property
    def last_changed(self) -> datetime:
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

    @property
    def last_updated(self) -> datetime:
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


def row_to_compressed_state_pre_schema_31(
    row: Row,
    attr_cache: dict[str, dict[str, Any]],
    start_time: datetime | None,
) -> dict[str, Any]:
    """Convert a database row to a compressed state before schema 31."""
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
