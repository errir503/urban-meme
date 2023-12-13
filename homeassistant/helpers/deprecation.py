"""Deprecation helpers for Home Assistant."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
import functools
import inspect
import logging
from typing import Any, ParamSpec, TypeVar

from homeassistant.core import HomeAssistant, async_get_hass
from homeassistant.exceptions import HomeAssistantError
from homeassistant.loader import async_suggest_report_issue

from .frame import MissingIntegrationFrame, get_integration_frame

_ObjectT = TypeVar("_ObjectT", bound=object)
_R = TypeVar("_R")
_P = ParamSpec("_P")


def deprecated_substitute(
    substitute_name: str,
) -> Callable[[Callable[[_ObjectT], Any]], Callable[[_ObjectT], Any]]:
    """Help migrate properties to new names.

    When a property is added to replace an older property, this decorator can
    be added to the new property, listing the old property as the substitute.
    If the old property is defined, its value will be used instead, and a log
    warning will be issued alerting the user of the impending change.
    """

    def decorator(func: Callable[[_ObjectT], Any]) -> Callable[[_ObjectT], Any]:
        """Decorate function as deprecated."""

        def func_wrapper(self: _ObjectT) -> Any:
            """Wrap for the original function."""
            if hasattr(self, substitute_name):
                # If this platform is still using the old property, issue
                # a logger warning once with instructions on how to fix it.
                warnings = getattr(func, "_deprecated_substitute_warnings", {})
                module_name = self.__module__
                if not warnings.get(module_name):
                    logger = logging.getLogger(module_name)
                    logger.warning(
                        (
                            "'%s' is deprecated. Please rename '%s' to "
                            "'%s' in '%s' to ensure future support."
                        ),
                        substitute_name,
                        substitute_name,
                        func.__name__,
                        inspect.getfile(self.__class__),
                    )
                    warnings[module_name] = True
                    setattr(func, "_deprecated_substitute_warnings", warnings)

                # Return the old property
                return getattr(self, substitute_name)
            return func(self)

        return func_wrapper

    return decorator


def get_deprecated(
    config: dict[str, Any], new_name: str, old_name: str, default: Any | None = None
) -> Any | None:
    """Allow an old config name to be deprecated with a replacement.

    If the new config isn't found, but the old one is, the old value is used
    and a warning is issued to the user.
    """
    if old_name in config:
        module = inspect.getmodule(inspect.stack(context=0)[1].frame)
        if module is not None:
            module_name = module.__name__
        else:
            # If Python is unable to access the sources files, the call stack frame
            # will be missing information, so let's guard.
            # https://github.com/home-assistant/core/issues/24982
            module_name = __name__

        logger = logging.getLogger(module_name)
        logger.warning(
            (
                "'%s' is deprecated. Please rename '%s' to '%s' in your "
                "configuration file."
            ),
            old_name,
            old_name,
            new_name,
        )
        return config.get(old_name)
    return config.get(new_name, default)


def deprecated_class(
    replacement: str, *, breaks_in_ha_version: str | None = None
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Mark class as deprecated and provide a replacement class to be used instead.

    If the deprecated function was called from a custom integration, ask the user to
    report an issue.
    """

    def deprecated_decorator(cls: Callable[_P, _R]) -> Callable[_P, _R]:
        """Decorate class as deprecated."""

        @functools.wraps(cls)
        def deprecated_cls(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            """Wrap for the original class."""
            _print_deprecation_warning(
                cls, replacement, "class", "instantiated", breaks_in_ha_version
            )
            return cls(*args, **kwargs)

        return deprecated_cls

    return deprecated_decorator


def deprecated_function(
    replacement: str, *, breaks_in_ha_version: str | None = None
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Mark function as deprecated and provide a replacement to be used instead.

    If the deprecated function was called from a custom integration, ask the user to
    report an issue.
    """

    def deprecated_decorator(func: Callable[_P, _R]) -> Callable[_P, _R]:
        """Decorate function as deprecated."""

        @functools.wraps(func)
        def deprecated_func(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            """Wrap for the original function."""
            _print_deprecation_warning(
                func, replacement, "function", "called", breaks_in_ha_version
            )
            return func(*args, **kwargs)

        return deprecated_func

    return deprecated_decorator


def _print_deprecation_warning(
    obj: Any,
    replacement: str,
    description: str,
    verb: str,
    breaks_in_ha_version: str | None,
) -> None:
    logger = logging.getLogger(obj.__module__)
    if breaks_in_ha_version:
        breaks_in = f" which will be removed in HA Core {breaks_in_ha_version}"
    else:
        breaks_in = ""
    try:
        integration_frame = get_integration_frame()
    except MissingIntegrationFrame:
        logger.warning(
            "%s is a deprecated %s%s. Use %s instead",
            obj.__name__,
            description,
            breaks_in,
            replacement,
        )
    else:
        if integration_frame.custom_integration:
            hass: HomeAssistant | None = None
            with suppress(HomeAssistantError):
                hass = async_get_hass()
            report_issue = async_suggest_report_issue(
                hass,
                integration_domain=integration_frame.integration,
                module=integration_frame.module,
            )
            logger.warning(
                (
                    "%s was %s from %s, this is a deprecated %s%s. Use %s instead,"
                    " please %s"
                ),
                obj.__name__,
                verb,
                integration_frame.integration,
                description,
                breaks_in,
                replacement,
                report_issue,
            )
        else:
            logger.warning(
                "%s was %s from %s, this is a deprecated %s%s. Use %s instead",
                obj.__name__,
                verb,
                integration_frame.integration,
                description,
                breaks_in,
                replacement,
            )
