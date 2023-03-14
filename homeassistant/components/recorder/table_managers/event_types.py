"""Support managing EventTypes."""
from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from lru import LRU  # pylint: disable=no-name-in-module
from sqlalchemy.orm.session import Session

from homeassistant.core import Event

from ..db_schema import EventTypes
from ..queries import find_event_type_ids

CACHE_SIZE = 2048


class EventTypeManager:
    """Manage the EventTypes table."""

    def __init__(self) -> None:
        """Initialize the event type manager."""
        self._id_map: dict[str, int] = LRU(CACHE_SIZE)
        self._pending: dict[str, EventTypes] = {}
        self.active = False

    def load(self, events: list[Event], session: Session) -> None:
        """Load the event_type to event_type_ids mapping into memory."""
        self.get_many(
            (event.event_type for event in events if event.event_type is not None),
            session,
        )

    def get(self, event_type: str, session: Session) -> int | None:
        """Resolve event_type to the event_type_id."""
        return self.get_many((event_type,), session)[event_type]

    def get_many(
        self, event_types: Iterable[str], session: Session
    ) -> dict[str, int | None]:
        """Resolve event_types to event_type_ids."""
        results: dict[str, int | None] = {}
        missing: list[str] = []
        for event_type in event_types:
            if (event_type_id := self._id_map.get(event_type)) is None:
                missing.append(event_type)

            results[event_type] = event_type_id

        if not missing:
            return results

        with session.no_autoflush:
            for event_type_id, event_type in session.execute(
                find_event_type_ids(missing)
            ):
                results[event_type] = self._id_map[event_type] = cast(
                    int, event_type_id
                )

        return results

    def get_pending(self, event_type: str) -> EventTypes | None:
        """Get pending EventTypes that have not be assigned ids yet."""
        return self._pending.get(event_type)

    def add_pending(self, db_event_type: EventTypes) -> None:
        """Add a pending EventTypes that will be committed at the next interval."""
        assert db_event_type.event_type is not None
        event_type: str = db_event_type.event_type
        self._pending[event_type] = db_event_type

    def post_commit_pending(self) -> None:
        """Call after commit to load the event_type_ids of the new EventTypes into the LRU."""
        for event_type, db_event_types in self._pending.items():
            self._id_map[event_type] = db_event_types.event_type_id
        self._pending.clear()

    def reset(self) -> None:
        """Reset the event manager after the database has been reset or changed."""
        self._id_map.clear()
        self._pending.clear()

    def evict_purged(self, event_types: Iterable[str]) -> None:
        """Evict purged event_types from the cache when they are no longer used."""
        for event_type in event_types:
            self._id_map.pop(event_type, None)
