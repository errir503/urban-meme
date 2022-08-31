"""HTTP Support for Hass.io."""
from __future__ import annotations

import asyncio
from http import HTTPStatus
import logging
import os
import re

import aiohttp
from aiohttp import web
from aiohttp.client import ClientTimeout
from aiohttp.hdrs import (
    AUTHORIZATION,
    CACHE_CONTROL,
    CONTENT_ENCODING,
    CONTENT_LENGTH,
    CONTENT_TYPE,
    TRANSFER_ENCODING,
)
from aiohttp.web_exceptions import HTTPBadGateway
from multidict import istr

from homeassistant.components.http import KEY_AUTHENTICATED, HomeAssistantView
from homeassistant.components.onboarding import async_is_onboarded

from .const import X_HASS_IS_ADMIN, X_HASS_USER_ID

_LOGGER = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 1024 * 1024 * 1024

# pylint: disable=implicit-str-concat
NO_TIMEOUT = re.compile(
    r"^(?:"
    r"|homeassistant/update"
    r"|hassos/update"
    r"|hassos/update/cli"
    r"|supervisor/update"
    r"|addons/[^/]+/(?:update|install|rebuild)"
    r"|backups/.+/full"
    r"|backups/.+/partial"
    r"|backups/[^/]+/(?:upload|download)"
    r")$"
)

NO_AUTH_ONBOARDING = re.compile(r"^(?:" r"|supervisor/logs" r"|backups/[^/]+/.+" r")$")

NO_AUTH = re.compile(r"^(?:" r"|app/.*" r"|[store\/]*addons/[^/]+/(logo|icon)" r")$")

NO_STORE = re.compile(r"^(?:" r"|app/entrypoint.js" r")$")
# pylint: enable=implicit-str-concat


class HassIOView(HomeAssistantView):
    """Hass.io view to handle base part."""

    name = "api:hassio"
    url = "/api/hassio/{path:.+}"
    requires_auth = False

    def __init__(self, host: str, websession: aiohttp.ClientSession) -> None:
        """Initialize a Hass.io base view."""
        self._host = host
        self._websession = websession

    async def _handle(
        self, request: web.Request, path: str
    ) -> web.Response | web.StreamResponse:
        """Route data to Hass.io."""
        hass = request.app["hass"]
        if _need_auth(hass, path) and not request[KEY_AUTHENTICATED]:
            return web.Response(status=HTTPStatus.UNAUTHORIZED)

        return await self._command_proxy(path, request)

    delete = _handle
    get = _handle
    post = _handle

    async def _command_proxy(
        self, path: str, request: web.Request
    ) -> web.StreamResponse:
        """Return a client request with proxy origin for Hass.io supervisor.

        This method is a coroutine.
        """
        headers = _init_header(request)
        if path == "backups/new/upload":
            # We need to reuse the full content type that includes the boundary
            headers[
                CONTENT_TYPE
            ] = request._stored_content_type  # pylint: disable=protected-access

        try:
            client = await self._websession.request(
                method=request.method,
                url=f"http://{self._host}/{path}",
                params=request.query,
                data=request.content,
                headers=headers,
                timeout=_get_timeout(path),
            )

            # Stream response
            response = web.StreamResponse(
                status=client.status, headers=_response_header(client, path)
            )
            response.content_type = client.content_type

            await response.prepare(request)
            async for data in client.content.iter_chunked(4096):
                await response.write(data)

            return response

        except aiohttp.ClientError as err:
            _LOGGER.error("Client error on api %s request %s", path, err)

        except asyncio.TimeoutError:
            _LOGGER.error("Client timeout error on API request %s", path)

        raise HTTPBadGateway()


def _init_header(request: web.Request) -> dict[istr, str]:
    """Create initial header."""
    headers = {
        AUTHORIZATION: f"Bearer {os.environ.get('SUPERVISOR_TOKEN', '')}",
        CONTENT_TYPE: request.content_type,
    }

    # Add user data
    if request.get("hass_user") is not None:
        headers[istr(X_HASS_USER_ID)] = request["hass_user"].id
        headers[istr(X_HASS_IS_ADMIN)] = str(int(request["hass_user"].is_admin))

    return headers


def _response_header(response: aiohttp.ClientResponse, path: str) -> dict[str, str]:
    """Create response header."""
    headers = {}

    for name, value in response.headers.items():
        if name in (
            TRANSFER_ENCODING,
            CONTENT_LENGTH,
            CONTENT_TYPE,
            CONTENT_ENCODING,
        ):
            continue
        headers[name] = value

    if NO_STORE.match(path):
        headers[CACHE_CONTROL] = "no-store, max-age=0"

    return headers


def _get_timeout(path: str) -> ClientTimeout:
    """Return timeout for a URL path."""
    if NO_TIMEOUT.match(path):
        return ClientTimeout(connect=10, total=None)
    return ClientTimeout(connect=10, total=300)


def _need_auth(hass, path: str) -> bool:
    """Return if a path need authentication."""
    if not async_is_onboarded(hass) and NO_AUTH_ONBOARDING.match(path):
        return False
    if NO_AUTH.match(path):
        return False
    return True
