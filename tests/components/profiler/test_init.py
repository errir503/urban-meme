"""Test the Profiler config flow."""
from datetime import timedelta
import os
from unittest.mock import patch

from homeassistant.components.profiler import (
    CONF_SECONDS,
    SERVICE_DUMP_LOG_OBJECTS,
    SERVICE_LOG_EVENT_LOOP_SCHEDULED,
    SERVICE_LOG_THREAD_FRAMES,
    SERVICE_MEMORY,
    SERVICE_START,
    SERVICE_START_LOG_OBJECTS,
    SERVICE_STOP_LOG_OBJECTS,
)
from homeassistant.components.profiler.const import DOMAIN
from homeassistant.const import CONF_SCAN_INTERVAL, CONF_TYPE
import homeassistant.util.dt as dt_util

from tests.common import MockConfigEntry, async_fire_time_changed


async def test_basic_usage(hass, tmpdir):
    """Test we can setup and the service is registered."""
    test_dir = tmpdir.mkdir("profiles")

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_START)

    last_filename = None

    def _mock_path(filename):
        nonlocal last_filename
        last_filename = f"{test_dir}/{filename}"
        return last_filename

    with patch("homeassistant.components.profiler.cProfile.Profile"), patch.object(
        hass.config, "path", _mock_path
    ):
        await hass.services.async_call(DOMAIN, SERVICE_START, {CONF_SECONDS: 0.000001})
        await hass.async_block_till_done()

    assert os.path.exists(last_filename)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_memory_usage(hass, tmpdir):
    """Test we can setup and the service is registered."""
    test_dir = tmpdir.mkdir("profiles")

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_MEMORY)

    last_filename = None

    def _mock_path(filename):
        nonlocal last_filename
        last_filename = f"{test_dir}/{filename}"
        return last_filename

    with patch("homeassistant.components.profiler.hpy") as mock_hpy, patch.object(
        hass.config, "path", _mock_path
    ):
        await hass.services.async_call(DOMAIN, SERVICE_MEMORY, {CONF_SECONDS: 0.000001})
        await hass.async_block_till_done()

        mock_hpy.assert_called_once()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_object_growth_logging(hass, caplog):
    """Test we can setup and the service and we can dump objects to the log."""

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_START_LOG_OBJECTS)
    assert hass.services.has_service(DOMAIN, SERVICE_STOP_LOG_OBJECTS)

    with patch("homeassistant.components.profiler.objgraph.growth"):
        await hass.services.async_call(
            DOMAIN, SERVICE_START_LOG_OBJECTS, {CONF_SCAN_INTERVAL: 10}
        )
        await hass.async_block_till_done()

    assert "Growth" in caplog.text
    caplog.clear()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert "Growth" in caplog.text

    await hass.services.async_call(DOMAIN, SERVICE_STOP_LOG_OBJECTS, {})
    await hass.async_block_till_done()
    caplog.clear()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=21))
    await hass.async_block_till_done()
    assert "Growth" not in caplog.text

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert "Growth" not in caplog.text


async def test_dump_log_object(hass, caplog):
    """Test we can setup and the service is registered and logging works."""

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    class DumpLogDummy:
        def __init__(self, fail):
            self.fail = fail

        def __repr__(self):
            if self.fail:
                raise Exception("failed")
            return "<DumpLogDummy success>"

    obj1 = DumpLogDummy(False)
    obj2 = DumpLogDummy(True)

    assert hass.services.has_service(DOMAIN, SERVICE_DUMP_LOG_OBJECTS)

    await hass.services.async_call(
        DOMAIN, SERVICE_DUMP_LOG_OBJECTS, {CONF_TYPE: "DumpLogDummy"}
    )
    await hass.async_block_till_done()

    assert "<DumpLogDummy success>" in caplog.text
    assert "Failed to serialize" in caplog.text
    del obj1
    del obj2
    caplog.clear()


async def test_log_thread_frames(hass, caplog):
    """Test we can log thread frames."""

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_LOG_THREAD_FRAMES)

    await hass.services.async_call(DOMAIN, SERVICE_LOG_THREAD_FRAMES, {})
    await hass.async_block_till_done()

    assert "SyncWorker_0" in caplog.text
    caplog.clear()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_log_scheduled(hass, caplog):
    """Test we can log scheduled items in the event loop."""

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_LOG_EVENT_LOOP_SCHEDULED)

    await hass.services.async_call(DOMAIN, SERVICE_LOG_EVENT_LOOP_SCHEDULED, {})
    await hass.async_block_till_done()

    assert "Scheduled" in caplog.text
    caplog.clear()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
