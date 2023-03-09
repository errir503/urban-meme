"""Test Home Assistant logging util methods."""
import asyncio
from functools import partial
import logging
import queue
from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant, callback, is_callback
import homeassistant.util.logging as logging_util


def test_sensitive_data_filter() -> None:
    """Test the logging sensitive data filter."""
    log_filter = logging_util.HideSensitiveDataFilter("mock_sensitive")

    clean_record = logging.makeLogRecord({"msg": "clean log data"})
    log_filter.filter(clean_record)
    assert clean_record.msg == "clean log data"

    sensitive_record = logging.makeLogRecord({"msg": "mock_sensitive log"})
    log_filter.filter(sensitive_record)
    assert sensitive_record.msg == "******* log"


async def test_logging_with_queue_handler() -> None:
    """Test logging with HomeAssistantQueueHandler."""

    simple_queue = queue.SimpleQueue()  # type: ignore
    handler = logging_util.HomeAssistantQueueHandler(simple_queue)

    log_record = logging.makeLogRecord({"msg": "Test Log Record"})

    handler.emit(log_record)

    with pytest.raises(asyncio.CancelledError), patch.object(
        handler, "enqueue", side_effect=asyncio.CancelledError
    ):
        handler.emit(log_record)

    with patch.object(handler, "emit") as emit_mock:
        handler.handle(log_record)
        emit_mock.assert_called_once()

    with patch.object(handler, "filter") as filter_mock, patch.object(
        handler, "emit"
    ) as emit_mock:
        filter_mock.return_value = False
        handler.handle(log_record)
        emit_mock.assert_not_called()

    with patch.object(handler, "enqueue", side_effect=OSError), patch.object(
        handler, "handleError"
    ) as mock_handle_error:
        handler.emit(log_record)
        mock_handle_error.assert_called_once()

    handler.close()

    assert simple_queue.get_nowait().msg == "Test Log Record"
    assert simple_queue.empty()


async def test_migrate_log_handler(hass: HomeAssistant) -> None:
    """Test migrating log handlers."""

    logging_util.async_activate_log_queue_handler(hass)

    assert len(logging.root.handlers) == 1
    assert isinstance(logging.root.handlers[0], logging_util.HomeAssistantQueueHandler)

    # Test that the close hook shuts down the queue handler's thread
    listener_thread = logging.root.handlers[0].listener._thread
    assert listener_thread.is_alive()
    logging.root.handlers[0].close()
    assert not listener_thread.is_alive()


@pytest.mark.no_fail_on_log_exception
async def test_async_create_catching_coro(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test exception logging of wrapped coroutine."""

    async def job():
        raise Exception("This is a bad coroutine")

    hass.async_create_task(logging_util.async_create_catching_coro(job()))
    await hass.async_block_till_done()
    assert "This is a bad coroutine" in caplog.text
    assert "in test_async_create_catching_coro" in caplog.text


def test_catch_log_exception() -> None:
    """Test it is still a callback after wrapping including partial."""

    async def async_meth():
        pass

    assert asyncio.iscoroutinefunction(
        logging_util.catch_log_exception(partial(async_meth), lambda: None)
    )

    @callback
    def callback_meth():
        pass

    assert is_callback(
        logging_util.catch_log_exception(partial(callback_meth), lambda: None)
    )

    def sync_meth():
        pass

    wrapped = logging_util.catch_log_exception(partial(sync_meth), lambda: None)

    assert not is_callback(wrapped)
    assert not asyncio.iscoroutinefunction(wrapped)
