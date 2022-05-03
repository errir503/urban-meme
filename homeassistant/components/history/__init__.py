"""Provide pre-made queries on top of the recorder component."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime as dt, timedelta
from http import HTTPStatus
import logging
import time
from typing import cast

from aiohttp import web
from sqlalchemy import not_, or_
import voluptuous as vol

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.recorder import (
    get_instance,
    history,
    models as history_models,
)
from homeassistant.components.recorder.statistics import (
    list_statistic_ids,
    statistics_during_period,
)
from homeassistant.components.recorder.util import session_scope
from homeassistant.const import CONF_DOMAINS, CONF_ENTITIES, CONF_EXCLUDE, CONF_INCLUDE
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.deprecation import deprecated_class, deprecated_function
from homeassistant.helpers.entityfilter import (
    CONF_ENTITY_GLOBS,
    INCLUDE_EXCLUDE_BASE_FILTER_SCHEMA,
)
from homeassistant.helpers.typing import ConfigType
import homeassistant.util.dt as dt_util

# mypy: allow-untyped-defs, no-check-untyped-defs

_LOGGER = logging.getLogger(__name__)

DOMAIN = "history"
CONF_ORDER = "use_include_order"

GLOB_TO_SQL_CHARS = {
    42: "%",  # *
    46: "_",  # .
}

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: INCLUDE_EXCLUDE_BASE_FILTER_SCHEMA.extend(
            {vol.Optional(CONF_ORDER, default=False): cv.boolean}
        )
    },
    extra=vol.ALLOW_EXTRA,
)


@deprecated_function("homeassistant.components.recorder.history.get_significant_states")
def get_significant_states(hass, *args, **kwargs):
    """Wrap get_significant_states_with_session with an sql session."""
    return history.get_significant_states(hass, *args, **kwargs)


@deprecated_function(
    "homeassistant.components.recorder.history.state_changes_during_period"
)
def state_changes_during_period(hass, start_time, end_time=None, entity_id=None):
    """Return states changes during UTC period start_time - end_time."""
    return history.state_changes_during_period(
        hass, start_time, end_time=None, entity_id=None
    )


@deprecated_function("homeassistant.components.recorder.history.get_last_state_changes")
def get_last_state_changes(hass, number_of_states, entity_id):
    """Return the last number_of_states."""
    return history.get_last_state_changes(hass, number_of_states, entity_id)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the history hooks."""
    conf = config.get(DOMAIN, {})

    filters = sqlalchemy_filter_from_include_exclude_conf(conf)

    use_include_order = conf.get(CONF_ORDER)

    hass.http.register_view(HistoryPeriodView(filters, use_include_order))
    frontend.async_register_built_in_panel(hass, "history", "history", "hass:chart-box")
    websocket_api.async_register_command(hass, ws_get_statistics_during_period)
    websocket_api.async_register_command(hass, ws_get_list_statistic_ids)

    return True


@deprecated_class("homeassistant.components.recorder.models.LazyState")
class LazyState(history_models.LazyState):
    """A lazy version of core State."""


@websocket_api.websocket_command(
    {
        vol.Required("type"): "history/statistics_during_period",
        vol.Required("start_time"): str,
        vol.Optional("end_time"): str,
        vol.Optional("statistic_ids"): [str],
        vol.Required("period"): vol.Any("5minute", "hour", "day", "month"),
    }
)
@websocket_api.async_response
async def ws_get_statistics_during_period(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle statistics websocket command."""
    start_time_str = msg["start_time"]
    end_time_str = msg.get("end_time")

    if start_time := dt_util.parse_datetime(start_time_str):
        start_time = dt_util.as_utc(start_time)
    else:
        connection.send_error(msg["id"], "invalid_start_time", "Invalid start_time")
        return

    if end_time_str:
        if end_time := dt_util.parse_datetime(end_time_str):
            end_time = dt_util.as_utc(end_time)
        else:
            connection.send_error(msg["id"], "invalid_end_time", "Invalid end_time")
            return
    else:
        end_time = None

    statistics = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start_time,
        end_time,
        msg.get("statistic_ids"),
        msg.get("period"),
    )
    connection.send_result(msg["id"], statistics)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "history/list_statistic_ids",
        vol.Optional("statistic_type"): vol.Any("sum", "mean"),
    }
)
@websocket_api.async_response
async def ws_get_list_statistic_ids(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Fetch a list of available statistic_id."""
    statistic_ids = await get_instance(hass).async_add_executor_job(
        list_statistic_ids,
        hass,
        None,
        msg.get("statistic_type"),
    )
    connection.send_result(msg["id"], statistic_ids)


class HistoryPeriodView(HomeAssistantView):
    """Handle history period requests."""

    url = "/api/history/period"
    name = "api:history:view-period"
    extra_urls = ["/api/history/period/{datetime}"]

    def __init__(self, filters: Filters | None, use_include_order: bool) -> None:
        """Initialize the history period view."""
        self.filters = filters
        self.use_include_order = use_include_order

    async def get(
        self, request: web.Request, datetime: str | None = None
    ) -> web.Response:
        """Return history over a period of time."""
        datetime_ = None
        if datetime and (datetime_ := dt_util.parse_datetime(datetime)) is None:
            return self.json_message("Invalid datetime", HTTPStatus.BAD_REQUEST)

        now = dt_util.utcnow()

        one_day = timedelta(days=1)
        if datetime_:
            start_time = dt_util.as_utc(datetime_)
        else:
            start_time = now - one_day

        if start_time > now:
            return self.json([])

        if end_time_str := request.query.get("end_time"):
            if end_time := dt_util.parse_datetime(end_time_str):
                end_time = dt_util.as_utc(end_time)
            else:
                return self.json_message("Invalid end_time", HTTPStatus.BAD_REQUEST)
        else:
            end_time = start_time + one_day
        entity_ids_str = request.query.get("filter_entity_id")
        entity_ids = None
        if entity_ids_str:
            entity_ids = entity_ids_str.lower().split(",")
        include_start_time_state = "skip_initial_state" not in request.query
        significant_changes_only = (
            request.query.get("significant_changes_only", "1") != "0"
        )

        minimal_response = "minimal_response" in request.query
        no_attributes = "no_attributes" in request.query

        hass = request.app["hass"]

        if (
            not include_start_time_state
            and entity_ids
            and not _entities_may_have_state_changes_after(hass, entity_ids, start_time)
        ):
            return self.json([])

        return cast(
            web.Response,
            await get_instance(hass).async_add_executor_job(
                self._sorted_significant_states_json,
                hass,
                start_time,
                end_time,
                entity_ids,
                include_start_time_state,
                significant_changes_only,
                minimal_response,
                no_attributes,
            ),
        )

    def _sorted_significant_states_json(
        self,
        hass,
        start_time,
        end_time,
        entity_ids,
        include_start_time_state,
        significant_changes_only,
        minimal_response,
        no_attributes,
    ):
        """Fetch significant stats from the database as json."""
        timer_start = time.perf_counter()

        with session_scope(hass=hass) as session:
            result = history.get_significant_states_with_session(
                hass,
                session,
                start_time,
                end_time,
                entity_ids,
                self.filters,
                include_start_time_state,
                significant_changes_only,
                minimal_response,
                no_attributes,
            )

        result = list(result.values())
        if _LOGGER.isEnabledFor(logging.DEBUG):
            elapsed = time.perf_counter() - timer_start
            _LOGGER.debug("Extracted %d states in %fs", sum(map(len, result)), elapsed)

        # Optionally reorder the result to respect the ordering given
        # by any entities explicitly included in the configuration.
        if self.filters and self.use_include_order:
            sorted_result = []
            for order_entity in self.filters.included_entities:
                for state_list in result:
                    if state_list[0].entity_id == order_entity:
                        sorted_result.append(state_list)
                        result.remove(state_list)
                        break
            sorted_result.extend(result)
            result = sorted_result

        return self.json(result)


def sqlalchemy_filter_from_include_exclude_conf(conf: ConfigType) -> Filters | None:
    """Build a sql filter from config."""
    filters = Filters()
    if exclude := conf.get(CONF_EXCLUDE):
        filters.excluded_entities = exclude.get(CONF_ENTITIES, [])
        filters.excluded_domains = exclude.get(CONF_DOMAINS, [])
        filters.excluded_entity_globs = exclude.get(CONF_ENTITY_GLOBS, [])
    if include := conf.get(CONF_INCLUDE):
        filters.included_entities = include.get(CONF_ENTITIES, [])
        filters.included_domains = include.get(CONF_DOMAINS, [])
        filters.included_entity_globs = include.get(CONF_ENTITY_GLOBS, [])

    return filters if filters.has_config else None


class Filters:
    """Container for the configured include and exclude filters."""

    def __init__(self) -> None:
        """Initialise the include and exclude filters."""
        self.excluded_entities: list[str] = []
        self.excluded_domains: list[str] = []
        self.excluded_entity_globs: list[str] = []

        self.included_entities: list[str] = []
        self.included_domains: list[str] = []
        self.included_entity_globs: list[str] = []

    def apply(self, query):
        """Apply the entity filter."""
        if not self.has_config:
            return query

        return query.filter(self.entity_filter())

    @property
    def has_config(self):
        """Determine if there is any filter configuration."""
        if (
            self.excluded_entities
            or self.excluded_domains
            or self.excluded_entity_globs
            or self.included_entities
            or self.included_domains
            or self.included_entity_globs
        ):
            return True

        return False

    def bake(self, baked_query):
        """Update a baked query.

        Works the same as apply on a baked_query.
        """
        if not self.has_config:
            return

        baked_query += lambda q: q.filter(self.entity_filter())

    def entity_filter(self):
        """Generate the entity filter query."""
        includes = []
        if self.included_domains:
            includes.append(
                or_(
                    *[
                        history_models.States.entity_id.like(f"{domain}.%")
                        for domain in self.included_domains
                    ]
                ).self_group()
            )
        if self.included_entities:
            includes.append(history_models.States.entity_id.in_(self.included_entities))
        for glob in self.included_entity_globs:
            includes.append(_glob_to_like(glob))

        excludes = []
        if self.excluded_domains:
            excludes.append(
                or_(
                    *[
                        history_models.States.entity_id.like(f"{domain}.%")
                        for domain in self.excluded_domains
                    ]
                ).self_group()
            )
        if self.excluded_entities:
            excludes.append(history_models.States.entity_id.in_(self.excluded_entities))
        for glob in self.excluded_entity_globs:
            excludes.append(_glob_to_like(glob))

        if not includes and not excludes:
            return None

        if includes and not excludes:
            return or_(*includes)

        if not includes and excludes:
            return not_(or_(*excludes))

        return or_(*includes) & not_(or_(*excludes))


def _glob_to_like(glob_str):
    """Translate glob to sql."""
    return history_models.States.entity_id.like(glob_str.translate(GLOB_TO_SQL_CHARS))


def _entities_may_have_state_changes_after(
    hass: HomeAssistant, entity_ids: Iterable, start_time: dt
) -> bool:
    """Check the state machine to see if entities have changed since start time."""
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)

        if state is None or state.last_changed > start_time:
            return True

    return False
