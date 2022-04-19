"""The profiler integration."""
import asyncio
from datetime import timedelta
import logging
import reprlib
import sys
import threading
import time
import traceback
from typing import Any

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, CONF_TYPE
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN

SERVICE_START = "start"
SERVICE_MEMORY = "memory"
SERVICE_START_LOG_OBJECTS = "start_log_objects"
SERVICE_STOP_LOG_OBJECTS = "stop_log_objects"
SERVICE_DUMP_LOG_OBJECTS = "dump_log_objects"
SERVICE_LOG_THREAD_FRAMES = "log_thread_frames"
SERVICE_LOG_EVENT_LOOP_SCHEDULED = "log_event_loop_scheduled"


SERVICES = (
    SERVICE_START,
    SERVICE_MEMORY,
    SERVICE_START_LOG_OBJECTS,
    SERVICE_STOP_LOG_OBJECTS,
    SERVICE_DUMP_LOG_OBJECTS,
    SERVICE_LOG_THREAD_FRAMES,
    SERVICE_LOG_EVENT_LOOP_SCHEDULED,
)

DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

CONF_SECONDS = "seconds"

LOG_INTERVAL_SUB = "log_interval_subscription"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Profiler from a config entry."""
    lock = asyncio.Lock()
    domain_data = hass.data[DOMAIN] = {}

    async def _async_run_profile(call: ServiceCall) -> None:
        async with lock:
            await _async_generate_profile(hass, call)

    async def _async_run_memory_profile(call: ServiceCall) -> None:
        async with lock:
            await _async_generate_memory_profile(hass, call)

    async def _async_start_log_objects(call: ServiceCall) -> None:
        if LOG_INTERVAL_SUB in domain_data:
            domain_data[LOG_INTERVAL_SUB]()

        persistent_notification.async_create(
            hass,
            "Object growth logging has started. See [the logs](/config/logs) to track the growth of new objects.",
            title="Object growth logging started",
            notification_id="profile_object_logging",
        )
        await hass.async_add_executor_job(_log_objects)
        domain_data[LOG_INTERVAL_SUB] = async_track_time_interval(
            hass, _log_objects, call.data[CONF_SCAN_INTERVAL]
        )

    async def _async_stop_log_objects(call: ServiceCall) -> None:
        if LOG_INTERVAL_SUB not in domain_data:
            return

        persistent_notification.async_dismiss(hass, "profile_object_logging")
        domain_data.pop(LOG_INTERVAL_SUB)()

    def _safe_repr(obj: Any) -> str:
        """Get the repr of an object but keep going if there is an exception.

        We wrap repr to ensure if one object cannot be serialized, we can
        still get the rest.
        """
        try:
            return repr(obj)
        except Exception:  # pylint: disable=broad-except
            return f"Failed to serialize {type(obj)}"

    def _dump_log_objects(call: ServiceCall) -> None:
        # Imports deferred to avoid loading modules
        # in memory since usually only one part of this
        # integration is used at a time
        import objgraph  # pylint: disable=import-outside-toplevel

        obj_type = call.data[CONF_TYPE]

        _LOGGER.critical(
            "%s objects in memory: %s",
            obj_type,
            [_safe_repr(obj) for obj in objgraph.by_type(obj_type)],
        )

        persistent_notification.create(
            hass,
            f"Objects with type {obj_type} have been dumped to the log. See [the logs](/config/logs) to review the repr of the objects.",
            title="Object dump completed",
            notification_id="profile_object_dump",
        )

    async def _async_dump_thread_frames(call: ServiceCall) -> None:
        """Log all thread frames."""
        frames = sys._current_frames()  # pylint: disable=protected-access
        main_thread = threading.main_thread()
        for thread in threading.enumerate():
            if thread == main_thread:
                continue
            _LOGGER.critical(
                "Thread [%s]: %s",
                thread.name,
                "".join(traceback.format_stack(frames.get(thread.ident))).strip(),
            )

    async def _async_dump_scheduled(call: ServiceCall) -> None:
        """Log all scheduled in the event loop."""
        arepr = reprlib.aRepr
        original_maxstring = arepr.maxstring
        original_maxother = arepr.maxother
        arepr.maxstring = 300
        arepr.maxother = 300
        try:
            for handle in hass.loop._scheduled:  # pylint: disable=protected-access
                if not handle.cancelled():
                    _LOGGER.critical("Scheduled: %s", handle)
        finally:
            arepr.max_string = original_maxstring
            arepr.max_other = original_maxother

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_START,
        _async_run_profile,
        schema=vol.Schema(
            {vol.Optional(CONF_SECONDS, default=60.0): vol.Coerce(float)}
        ),
    )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_MEMORY,
        _async_run_memory_profile,
        schema=vol.Schema(
            {vol.Optional(CONF_SECONDS, default=60.0): vol.Coerce(float)}
        ),
    )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_START_LOG_OBJECTS,
        _async_start_log_objects,
        schema=vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): cv.time_period
            }
        ),
    )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_STOP_LOG_OBJECTS,
        _async_stop_log_objects,
    )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_DUMP_LOG_OBJECTS,
        _dump_log_objects,
        schema=vol.Schema({vol.Required(CONF_TYPE): str}),
    )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_LOG_THREAD_FRAMES,
        _async_dump_thread_frames,
    )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_LOG_EVENT_LOOP_SCHEDULED,
        _async_dump_scheduled,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    for service in SERVICES:
        hass.services.async_remove(domain=DOMAIN, service=service)
    if LOG_INTERVAL_SUB in hass.data[DOMAIN]:
        hass.data[DOMAIN][LOG_INTERVAL_SUB]()
    hass.data.pop(DOMAIN)
    return True


async def _async_generate_profile(hass: HomeAssistant, call: ServiceCall):
    # Imports deferred to avoid loading modules
    # in memory since usually only one part of this
    # integration is used at a time
    import cProfile  # pylint: disable=import-outside-toplevel

    start_time = int(time.time() * 1000000)
    persistent_notification.async_create(
        hass,
        "The profile has started. This notification will be updated when it is complete.",
        title="Profile Started",
        notification_id=f"profiler_{start_time}",
    )
    profiler = cProfile.Profile()
    profiler.enable()
    await asyncio.sleep(float(call.data[CONF_SECONDS]))
    profiler.disable()

    cprofile_path = hass.config.path(f"profile.{start_time}.cprof")
    callgrind_path = hass.config.path(f"callgrind.out.{start_time}")
    await hass.async_add_executor_job(
        _write_profile, profiler, cprofile_path, callgrind_path
    )
    persistent_notification.async_create(
        hass,
        f"Wrote cProfile data to {cprofile_path} and callgrind data to {callgrind_path}",
        title="Profile Complete",
        notification_id=f"profiler_{start_time}",
    )


async def _async_generate_memory_profile(hass: HomeAssistant, call: ServiceCall):
    # Imports deferred to avoid loading modules
    # in memory since usually only one part of this
    # integration is used at a time
    from guppy import hpy  # pylint: disable=import-outside-toplevel

    start_time = int(time.time() * 1000000)
    persistent_notification.async_create(
        hass,
        "The memory profile has started. This notification will be updated when it is complete.",
        title="Profile Started",
        notification_id=f"memory_profiler_{start_time}",
    )
    heap_profiler = hpy()
    heap_profiler.setref()
    await asyncio.sleep(float(call.data[CONF_SECONDS]))
    heap = heap_profiler.heap()

    heap_path = hass.config.path(f"heap_profile.{start_time}.hpy")
    await hass.async_add_executor_job(_write_memory_profile, heap, heap_path)
    persistent_notification.async_create(
        hass,
        f"Wrote heapy memory profile to {heap_path}",
        title="Profile Complete",
        notification_id=f"memory_profiler_{start_time}",
    )


def _write_profile(profiler, cprofile_path, callgrind_path):
    # Imports deferred to avoid loading modules
    # in memory since usually only one part of this
    # integration is used at a time
    from pyprof2calltree import convert  # pylint: disable=import-outside-toplevel

    profiler.create_stats()
    profiler.dump_stats(cprofile_path)
    convert(profiler.getstats(), callgrind_path)


def _write_memory_profile(heap, heap_path):
    heap.byrcs.dump(heap_path)


def _log_objects(*_):
    # Imports deferred to avoid loading modules
    # in memory since usually only one part of this
    # integration is used at a time
    import objgraph  # pylint: disable=import-outside-toplevel

    _LOGGER.critical("Memory Growth: %s", objgraph.growth(limit=100))
