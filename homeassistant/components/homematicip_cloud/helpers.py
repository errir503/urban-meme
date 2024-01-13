"""Helper functions for Homematicip Cloud Integration."""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from functools import wraps
import json
import logging
from typing import Any, Concatenate, ParamSpec, TypeGuard, TypeVar

from homeassistant.exceptions import HomeAssistantError

from . import HomematicipGenericEntity

_HomematicipGenericEntityT = TypeVar(
    "_HomematicipGenericEntityT", bound=HomematicipGenericEntity
)
_P = ParamSpec("_P")

_LOGGER = logging.getLogger(__name__)


def is_error_response(response: Any) -> TypeGuard[dict[str, Any]]:
    """Response from async call contains errors or not."""
    if isinstance(response, dict):
        return response.get("errorCode") not in ("", None)

    return False


def handle_errors(
    func: Callable[
        Concatenate[_HomematicipGenericEntityT, _P], Coroutine[Any, Any, Any]
    ],
) -> Callable[Concatenate[_HomematicipGenericEntityT, _P], Coroutine[Any, Any, Any]]:
    """Handle async errors."""

    @wraps(func)
    async def inner(
        self: _HomematicipGenericEntityT, *args: _P.args, **kwargs: _P.kwargs
    ) -> None:
        """Handle errors from async call."""
        result = await func(self, *args, **kwargs)
        if is_error_response(result):
            _LOGGER.error(
                "Error while execute function %s: %s",
                __name__,
                json.dumps(result),
            )
            raise HomeAssistantError(
                f"Error while execute function {func.__name__}: {result.get('errorCode')}. See log for more information."
            )

    return inner
