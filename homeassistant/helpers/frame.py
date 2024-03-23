"""Provide frame helper for finding the current frame context."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
import functools
import linecache
import logging
import sys
from types import FrameType
from typing import TYPE_CHECKING, Any, TypeVar, cast

from homeassistant.core import HomeAssistant, async_get_hass
from homeassistant.exceptions import HomeAssistantError
from homeassistant.loader import async_suggest_report_issue

if TYPE_CHECKING:
    from functools import cached_property
else:
    from homeassistant.backports.functools import cached_property

_LOGGER = logging.getLogger(__name__)

# Keep track of integrations already reported to prevent flooding
_REPORTED_INTEGRATIONS: set[str] = set()

_CallableT = TypeVar("_CallableT", bound=Callable)


@dataclass(kw_only=True)
class IntegrationFrame:
    """Integration frame container."""

    custom_integration: bool
    integration: str
    module: str | None
    relative_filename: str
    _frame: FrameType

    @cached_property
    def line_number(self) -> int:
        """Return the line number of the frame."""
        return self._frame.f_lineno

    @cached_property
    def filename(self) -> str:
        """Return the filename of the frame."""
        return self._frame.f_code.co_filename

    @cached_property
    def line(self) -> str:
        """Return the line of the frame."""
        return (linecache.getline(self.filename, self.line_number) or "?").strip()


def get_integration_logger(fallback_name: str) -> logging.Logger:
    """Return a logger by checking the current integration frame.

    If Python is unable to access the sources files, the call stack frame
    will be missing information, so let's guard by requiring a fallback name.
    https://github.com/home-assistant/core/issues/24982
    """
    try:
        integration_frame = get_integration_frame()
    except MissingIntegrationFrame:
        return logging.getLogger(fallback_name)

    if integration_frame.custom_integration:
        logger_name = f"custom_components.{integration_frame.integration}"
    else:
        logger_name = f"homeassistant.components.{integration_frame.integration}"

    return logging.getLogger(logger_name)


def get_current_frame(depth: int = 0) -> FrameType:
    """Return the current frame."""
    # Add one to depth since get_current_frame is included
    return sys._getframe(depth + 1)  # pylint: disable=protected-access


def get_integration_frame(exclude_integrations: set | None = None) -> IntegrationFrame:
    """Return the frame, integration and integration path of the current stack frame."""
    found_frame = None
    if not exclude_integrations:
        exclude_integrations = set()

    frame: FrameType | None = get_current_frame()
    while frame is not None:
        filename = frame.f_code.co_filename

        for path in ("custom_components/", "homeassistant/components/"):
            try:
                index = filename.index(path)
                start = index + len(path)
                end = filename.index("/", start)
                integration = filename[start:end]
                if integration not in exclude_integrations:
                    found_frame = frame

                break
            except ValueError:
                continue

        if found_frame is not None:
            break

        frame = frame.f_back

    if found_frame is None:
        raise MissingIntegrationFrame

    found_module: str | None = None
    for module, module_obj in dict(sys.modules).items():
        if not hasattr(module_obj, "__file__"):
            continue
        if module_obj.__file__ == found_frame.f_code.co_filename:
            found_module = module
            break

    return IntegrationFrame(
        custom_integration=path == "custom_components/",
        integration=integration,
        module=found_module,
        relative_filename=found_frame.f_code.co_filename[index:],
        _frame=found_frame,
    )


class MissingIntegrationFrame(HomeAssistantError):
    """Raised when no integration is found in the frame."""


def report(
    what: str,
    exclude_integrations: set | None = None,
    error_if_core: bool = True,
    level: int = logging.WARNING,
    log_custom_component_only: bool = False,
) -> None:
    """Report incorrect usage.

    Async friendly.
    """
    try:
        integration_frame = get_integration_frame(
            exclude_integrations=exclude_integrations
        )
    except MissingIntegrationFrame as err:
        msg = f"Detected code that {what}. Please report this issue."
        if error_if_core:
            raise RuntimeError(msg) from err
        if not log_custom_component_only:
            _LOGGER.warning(msg, stack_info=True)
        return

    if not log_custom_component_only or integration_frame.custom_integration:
        _report_integration(what, integration_frame, level)


def _report_integration(
    what: str,
    integration_frame: IntegrationFrame,
    level: int = logging.WARNING,
) -> None:
    """Report incorrect usage in an integration.

    Async friendly.
    """
    # Keep track of integrations already reported to prevent flooding
    key = f"{integration_frame.filename}:{integration_frame.line_number}"
    if key in _REPORTED_INTEGRATIONS:
        return
    _REPORTED_INTEGRATIONS.add(key)

    hass: HomeAssistant | None = None
    with suppress(HomeAssistantError):
        hass = async_get_hass()
    report_issue = async_suggest_report_issue(
        hass,
        integration_domain=integration_frame.integration,
        module=integration_frame.module,
    )

    _LOGGER.log(
        level,
        "Detected that %sintegration '%s' %s at %s, line %s: %s, please %s",
        "custom " if integration_frame.custom_integration else "",
        integration_frame.integration,
        what,
        integration_frame.relative_filename,
        integration_frame.line_number,
        integration_frame.line,
        report_issue,
    )


def warn_use(func: _CallableT, what: str) -> _CallableT:
    """Mock a function to warn when it was about to be used."""
    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def report_use(*args: Any, **kwargs: Any) -> None:
            report(what)

    else:

        @functools.wraps(func)
        def report_use(*args: Any, **kwargs: Any) -> None:
            report(what)

    return cast(_CallableT, report_use)
