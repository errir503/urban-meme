"""The Recorder websocket API."""
from __future__ import annotations

from datetime import datetime as dt
import logging
from typing import Any, Literal

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import messages
from homeassistant.core import HomeAssistant, callback, valid_entity_id
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.json import JSON_DUMP
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import (
    DistanceConverter,
    EnergyConverter,
    MassConverter,
    PowerConverter,
    PressureConverter,
    SpeedConverter,
    TemperatureConverter,
    VolumeConverter,
)

from .const import MAX_QUEUE_BACKLOG
from .statistics import (
    STATISTIC_UNIT_TO_UNIT_CONVERTER,
    async_add_external_statistics,
    async_change_statistics_unit,
    async_import_statistics,
    list_statistic_ids,
    statistics_during_period,
    validate_statistics,
)
from .util import async_migration_in_progress, async_migration_is_live, get_instance

_LOGGER: logging.Logger = logging.getLogger(__package__)


@callback
def async_setup(hass: HomeAssistant) -> None:
    """Set up the recorder websocket API."""
    websocket_api.async_register_command(hass, ws_adjust_sum_statistics)
    websocket_api.async_register_command(hass, ws_backup_end)
    websocket_api.async_register_command(hass, ws_backup_start)
    websocket_api.async_register_command(hass, ws_change_statistics_unit)
    websocket_api.async_register_command(hass, ws_clear_statistics)
    websocket_api.async_register_command(hass, ws_get_statistics_during_period)
    websocket_api.async_register_command(hass, ws_get_statistics_metadata)
    websocket_api.async_register_command(hass, ws_list_statistic_ids)
    websocket_api.async_register_command(hass, ws_import_statistics)
    websocket_api.async_register_command(hass, ws_info)
    websocket_api.async_register_command(hass, ws_update_statistics_metadata)
    websocket_api.async_register_command(hass, ws_validate_statistics)


def _ws_get_statistics_during_period(
    hass: HomeAssistant,
    msg_id: int,
    start_time: dt,
    end_time: dt | None,
    statistic_ids: list[str] | None,
    period: Literal["5minute", "day", "hour", "week", "month"],
    units: dict[str, str],
) -> str:
    """Fetch statistics and convert them to json in the executor."""
    return JSON_DUMP(
        messages.result_message(
            msg_id,
            statistics_during_period(
                hass, start_time, end_time, statistic_ids, period, units=units
            ),
        )
    )


async def ws_handle_get_statistics_during_period(
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

    connection.send_message(
        await get_instance(hass).async_add_executor_job(
            _ws_get_statistics_during_period,
            hass,
            msg["id"],
            start_time,
            end_time,
            msg.get("statistic_ids"),
            msg.get("period"),
            msg.get("units"),
        )
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "recorder/statistics_during_period",
        vol.Required("start_time"): str,
        vol.Optional("end_time"): str,
        vol.Optional("statistic_ids"): [str],
        vol.Required("period"): vol.Any("5minute", "hour", "day", "week", "month"),
        vol.Optional("units"): vol.Schema(
            {
                vol.Optional("distance"): vol.In(DistanceConverter.VALID_UNITS),
                vol.Optional("energy"): vol.In(EnergyConverter.VALID_UNITS),
                vol.Optional("mass"): vol.In(MassConverter.VALID_UNITS),
                vol.Optional("power"): vol.In(PowerConverter.VALID_UNITS),
                vol.Optional("pressure"): vol.In(PressureConverter.VALID_UNITS),
                vol.Optional("speed"): vol.In(SpeedConverter.VALID_UNITS),
                vol.Optional("temperature"): vol.In(TemperatureConverter.VALID_UNITS),
                vol.Optional("volume"): vol.In(VolumeConverter.VALID_UNITS),
            }
        ),
    }
)
@websocket_api.async_response
async def ws_get_statistics_during_period(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Handle statistics websocket command."""
    await ws_handle_get_statistics_during_period(hass, connection, msg)


def _ws_get_list_statistic_ids(
    hass: HomeAssistant,
    msg_id: int,
    statistic_type: Literal["mean"] | Literal["sum"] | None = None,
) -> str:
    """Fetch a list of available statistic_id and convert them to json in the executor."""
    return JSON_DUMP(
        messages.result_message(msg_id, list_statistic_ids(hass, None, statistic_type))
    )


async def ws_handle_list_statistic_ids(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Fetch a list of available statistic_id."""
    connection.send_message(
        await get_instance(hass).async_add_executor_job(
            _ws_get_list_statistic_ids,
            hass,
            msg["id"],
            msg.get("statistic_type"),
        )
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "recorder/list_statistic_ids",
        vol.Optional("statistic_type"): vol.Any("sum", "mean"),
    }
)
@websocket_api.async_response
async def ws_list_statistic_ids(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Fetch a list of available statistic_id."""
    await ws_handle_list_statistic_ids(hass, connection, msg)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "recorder/validate_statistics",
    }
)
@websocket_api.async_response
async def ws_validate_statistics(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Fetch a list of available statistic_id."""
    instance = get_instance(hass)
    statistic_ids = await instance.async_add_executor_job(
        validate_statistics,
        hass,
    )
    connection.send_result(msg["id"], statistic_ids)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "recorder/clear_statistics",
        vol.Required("statistic_ids"): [str],
    }
)
@callback
def ws_clear_statistics(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Clear statistics for a list of statistic_ids.

    Note: The WS call posts a job to the recorder's queue and then returns, it doesn't
    wait until the job is completed.
    """
    get_instance(hass).async_clear_statistics(msg["statistic_ids"])
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "recorder/get_statistics_metadata",
        vol.Optional("statistic_ids"): [str],
    }
)
@websocket_api.async_response
async def ws_get_statistics_metadata(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Get metadata for a list of statistic_ids."""
    instance = get_instance(hass)
    statistic_ids = await instance.async_add_executor_job(
        list_statistic_ids, hass, msg.get("statistic_ids")
    )
    connection.send_result(msg["id"], statistic_ids)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "recorder/update_statistics_metadata",
        vol.Required("statistic_id"): str,
        vol.Required("unit_of_measurement"): vol.Any(str, None),
    }
)
@callback
def ws_update_statistics_metadata(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Update statistics metadata for a statistic_id.

    Only the normalized unit of measurement can be updated.
    """
    get_instance(hass).async_update_statistics_metadata(
        msg["statistic_id"], new_unit_of_measurement=msg["unit_of_measurement"]
    )
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "recorder/change_statistics_unit",
        vol.Required("statistic_id"): str,
        vol.Required("new_unit_of_measurement"): vol.Any(str, None),
        vol.Required("old_unit_of_measurement"): vol.Any(str, None),
    }
)
@callback
def ws_change_statistics_unit(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Change the unit_of_measurement for a statistic_id.

    All existing statistics will be converted to the new unit.
    """
    async_change_statistics_unit(
        hass,
        msg["statistic_id"],
        new_unit_of_measurement=msg["new_unit_of_measurement"],
        old_unit_of_measurement=msg["old_unit_of_measurement"],
    )
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "recorder/adjust_sum_statistics",
        vol.Required("statistic_id"): str,
        vol.Required("start_time"): str,
        vol.Required("adjustment"): vol.Any(float, int),
        vol.Required("adjustment_unit_of_measurement"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_adjust_sum_statistics(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Adjust sum statistics.

    If the statistics is stored as NORMALIZED_UNIT,
    it's allowed to make an adjustment in VALID_UNIT
    """
    start_time_str = msg["start_time"]

    if start_time := dt_util.parse_datetime(start_time_str):
        start_time = dt_util.as_utc(start_time)
    else:
        connection.send_error(msg["id"], "invalid_start_time", "Invalid start time")
        return

    instance = get_instance(hass)
    metadatas = await instance.async_add_executor_job(
        list_statistic_ids, hass, (msg["statistic_id"],)
    )
    if not metadatas:
        connection.send_error(msg["id"], "unknown_statistic_id", "Unknown statistic ID")
        return
    metadata = metadatas[0]

    def valid_units(statistics_unit: str | None, adjustment_unit: str | None) -> bool:
        if statistics_unit == adjustment_unit:
            return True
        converter = STATISTIC_UNIT_TO_UNIT_CONVERTER.get(statistics_unit)
        if converter is not None and adjustment_unit in converter.VALID_UNITS:
            return True
        return False

    stat_unit = metadata["statistics_unit_of_measurement"]
    adjustment_unit = msg["adjustment_unit_of_measurement"]
    if not valid_units(stat_unit, adjustment_unit):
        connection.send_error(
            msg["id"],
            "invalid_units",
            f"Can't convert {stat_unit} to {adjustment_unit}",
        )
        return

    get_instance(hass).async_adjust_statistics(
        msg["statistic_id"], start_time, msg["adjustment"], adjustment_unit
    )
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "recorder/import_statistics",
        vol.Required("metadata"): {
            vol.Required("has_mean"): bool,
            vol.Required("has_sum"): bool,
            vol.Required("name"): vol.Any(str, None),
            vol.Required("source"): str,
            vol.Required("statistic_id"): str,
            vol.Required("unit_of_measurement"): vol.Any(str, None),
        },
        vol.Required("stats"): [
            {
                vol.Required("start"): cv.datetime,
                vol.Optional("mean"): vol.Any(float, int),
                vol.Optional("min"): vol.Any(float, int),
                vol.Optional("max"): vol.Any(float, int),
                vol.Optional("last_reset"): vol.Any(cv.datetime, None),
                vol.Optional("state"): vol.Any(float, int),
                vol.Optional("sum"): vol.Any(float, int),
            }
        ],
    }
)
@callback
def ws_import_statistics(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Import statistics."""
    metadata = msg["metadata"]
    stats = msg["stats"]

    if valid_entity_id(metadata["statistic_id"]):
        async_import_statistics(hass, metadata, stats)
    else:
        async_add_external_statistics(hass, metadata, stats)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "recorder/info",
    }
)
@callback
def ws_info(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return status of the recorder."""
    instance = get_instance(hass)

    backlog = instance.backlog if instance else None
    migration_in_progress = async_migration_in_progress(hass)
    migration_is_live = async_migration_is_live(hass)
    recording = instance.recording if instance else False
    thread_alive = instance.is_alive() if instance else False

    recorder_info = {
        "backlog": backlog,
        "max_backlog": MAX_QUEUE_BACKLOG,
        "migration_in_progress": migration_in_progress,
        "migration_is_live": migration_is_live,
        "recording": recording,
        "thread_running": thread_alive,
    }
    connection.send_result(msg["id"], recorder_info)


@websocket_api.ws_require_user(only_supervisor=True)
@websocket_api.websocket_command({vol.Required("type"): "backup/start"})
@websocket_api.async_response
async def ws_backup_start(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Backup start notification."""

    _LOGGER.info("Backup start notification, locking database for writes")
    instance = get_instance(hass)
    try:
        await instance.lock_database()
    except TimeoutError as err:
        connection.send_error(msg["id"], "timeout_error", str(err))
        return
    connection.send_result(msg["id"])


@websocket_api.ws_require_user(only_supervisor=True)
@websocket_api.websocket_command({vol.Required("type"): "backup/end"})
@websocket_api.async_response
async def ws_backup_end(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Backup end notification."""

    instance = get_instance(hass)
    _LOGGER.info("Backup end notification, releasing write lock")
    if not instance.unlock_database():
        connection.send_error(
            msg["id"], "database_unlock_failed", "Failed to unlock database."
        )
    connection.send_result(msg["id"])
