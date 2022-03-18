"""samsungctl and samsungtvws bridge classes."""
from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from asyncio.exceptions import TimeoutError as AsyncioTimeoutError
from collections.abc import Callable, Mapping
import contextlib
from typing import Any, cast

from samsungctl import Remote
from samsungctl.exceptions import AccessDenied, ConnectionClosed, UnhandledResponse
from samsungtvws.async_remote import SamsungTVWSAsyncRemote
from samsungtvws.async_rest import SamsungTVAsyncRest
from samsungtvws.command import SamsungTVCommand
from samsungtvws.event import MS_ERROR_EVENT
from samsungtvws.exceptions import ConnectionFailure, HttpApiError
from samsungtvws.remote import ChannelEmitCommand, SendRemoteKey
from websockets.exceptions import ConnectionClosedError, WebSocketException

from homeassistant.const import (
    CONF_HOST,
    CONF_ID,
    CONF_METHOD,
    CONF_NAME,
    CONF_PORT,
    CONF_TIMEOUT,
    CONF_TOKEN,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_DESCRIPTION,
    LEGACY_PORT,
    LOGGER,
    METHOD_LEGACY,
    METHOD_WEBSOCKET,
    RESULT_AUTH_MISSING,
    RESULT_CANNOT_CONNECT,
    RESULT_NOT_SUPPORTED,
    RESULT_SUCCESS,
    TIMEOUT_REQUEST,
    TIMEOUT_WEBSOCKET,
    VALUE_CONF_ID,
    VALUE_CONF_NAME,
    WEBSOCKET_PORTS,
)

KEY_PRESS_TIMEOUT = 1.2


def mac_from_device_info(info: dict[str, Any]) -> str | None:
    """Extract the mac address from the device info."""
    if wifi_mac := info.get("device", {}).get("wifiMac"):
        return format_mac(wifi_mac)
    return None


async def async_get_device_info(
    hass: HomeAssistant,
    bridge: SamsungTVBridge | None,
    host: str,
) -> tuple[int | None, str | None, dict[str, Any] | None]:
    """Fetch the port, method, and device info."""
    if bridge and bridge.port:
        return bridge.port, bridge.method, await bridge.async_device_info()

    for port in WEBSOCKET_PORTS:
        bridge = SamsungTVBridge.get_bridge(hass, METHOD_WEBSOCKET, host, port)
        if info := await bridge.async_device_info():
            return port, METHOD_WEBSOCKET, info

    bridge = SamsungTVBridge.get_bridge(hass, METHOD_LEGACY, host, LEGACY_PORT)
    result = await bridge.async_try_connect()
    if result in (RESULT_SUCCESS, RESULT_AUTH_MISSING):
        return LEGACY_PORT, METHOD_LEGACY, await bridge.async_device_info()

    return None, None, None


class SamsungTVBridge(ABC):
    """The Base Bridge abstract class."""

    @staticmethod
    def get_bridge(
        hass: HomeAssistant,
        method: str,
        host: str,
        port: int | None = None,
        entry_data: Mapping[str, Any] | None = None,
    ) -> SamsungTVBridge:
        """Get Bridge instance."""
        if method == METHOD_LEGACY or port == LEGACY_PORT:
            return SamsungTVLegacyBridge(hass, method, host, port)
        return SamsungTVWSBridge(hass, method, host, port, entry_data)

    def __init__(
        self, hass: HomeAssistant, method: str, host: str, port: int | None = None
    ) -> None:
        """Initialize Bridge."""
        self.hass = hass
        self.port = port
        self.method = method
        self.host = host
        self.token: str | None = None
        self._reauth_callback: CALLBACK_TYPE | None = None
        self._update_config_entry: Callable[[Mapping[str, Any]], None] | None = None

    def register_reauth_callback(self, func: CALLBACK_TYPE) -> None:
        """Register a callback function."""
        self._reauth_callback = func

    def register_update_config_entry_callback(
        self, func: Callable[[Mapping[str, Any]], None]
    ) -> None:
        """Register a callback function."""
        self._update_config_entry = func

    @abstractmethod
    async def async_try_connect(self) -> str:
        """Try to connect to the TV."""

    @abstractmethod
    async def async_device_info(self) -> dict[str, Any] | None:
        """Try to gather infos of this TV."""

    @abstractmethod
    async def async_get_app_list(self) -> dict[str, str] | None:
        """Get installed app list."""

    @abstractmethod
    async def async_is_on(self) -> bool:
        """Tells if the TV is on."""

    @abstractmethod
    async def async_send_keys(self, keys: list[str]) -> None:
        """Send a list of keys to the tv."""

    @abstractmethod
    async def async_power_off(self) -> None:
        """Send power off command to remote."""

    @abstractmethod
    async def async_close_remote(self) -> None:
        """Close remote object."""

    def _notify_reauth_callback(self) -> None:
        """Notify access denied callback."""
        if self._reauth_callback is not None:
            self._reauth_callback()

    def _notify_update_config_entry(self, updates: Mapping[str, Any]) -> None:
        """Notify update config callback."""
        if self._update_config_entry is not None:
            self._update_config_entry(updates)


class SamsungTVLegacyBridge(SamsungTVBridge):
    """The Bridge for Legacy TVs."""

    def __init__(
        self, hass: HomeAssistant, method: str, host: str, port: int | None
    ) -> None:
        """Initialize Bridge."""
        super().__init__(hass, method, host, LEGACY_PORT)
        self.config = {
            CONF_NAME: VALUE_CONF_NAME,
            CONF_DESCRIPTION: VALUE_CONF_NAME,
            CONF_ID: VALUE_CONF_ID,
            CONF_HOST: host,
            CONF_METHOD: method,
            CONF_PORT: None,
            CONF_TIMEOUT: 1,
        }
        self._remote: Remote | None = None

    async def async_get_app_list(self) -> dict[str, str]:
        """Get installed app list."""
        return {}

    async def async_is_on(self) -> bool:
        """Tells if the TV is on."""
        return await self.hass.async_add_executor_job(self._is_on)

    def _is_on(self) -> bool:
        """Tells if the TV is on."""
        if self._remote is not None:
            self._close_remote()

        try:
            return self._get_remote() is not None
        except (UnhandledResponse, AccessDenied):
            # We got a response so it's working.
            return True

    async def async_try_connect(self) -> str:
        """Try to connect to the Legacy TV."""
        return await self.hass.async_add_executor_job(self._try_connect)

    def _try_connect(self) -> str:
        """Try to connect to the Legacy TV."""
        config = {
            CONF_NAME: VALUE_CONF_NAME,
            CONF_DESCRIPTION: VALUE_CONF_NAME,
            CONF_ID: VALUE_CONF_ID,
            CONF_HOST: self.host,
            CONF_METHOD: self.method,
            CONF_PORT: None,
            # We need this high timeout because waiting for auth popup is just an open socket
            CONF_TIMEOUT: TIMEOUT_REQUEST,
        }
        try:
            LOGGER.debug("Try config: %s", config)
            with Remote(config.copy()):
                LOGGER.debug("Working config: %s", config)
                return RESULT_SUCCESS
        except AccessDenied:
            LOGGER.debug("Working but denied config: %s", config)
            return RESULT_AUTH_MISSING
        except UnhandledResponse as err:
            LOGGER.debug("Working but unsupported config: %s, error: %s", config, err)
            return RESULT_NOT_SUPPORTED
        except (ConnectionClosed, OSError) as err:
            LOGGER.debug("Failing config: %s, error: %s", config, err)
            return RESULT_CANNOT_CONNECT

    async def async_device_info(self) -> None:
        """Try to gather infos of this device."""
        return None

    def _get_remote(self) -> Remote:
        """Create or return a remote control instance."""
        if self._remote is None:
            # We need to create a new instance to reconnect.
            try:
                LOGGER.debug(
                    "Create SamsungTVLegacyBridge for %s (%s)", CONF_NAME, self.host
                )
                self._remote = Remote(self.config.copy())
            # This is only happening when the auth was switched to DENY
            # A removed auth will lead to socket timeout because waiting for auth popup is just an open socket
            except AccessDenied:
                self._notify_reauth_callback()
                raise
            except (ConnectionClosed, OSError):
                pass
        return self._remote

    async def async_send_keys(self, keys: list[str]) -> None:
        """Send a list of keys using legacy protocol."""
        first_key = True
        for key in keys:
            if first_key:
                first_key = False
            else:
                await asyncio.sleep(KEY_PRESS_TIMEOUT)
            await self.hass.async_add_executor_job(self._send_key, key)

    def _send_key(self, key: str) -> None:
        """Send a key using legacy protocol."""
        try:
            # recreate connection if connection was dead
            retry_count = 1
            for _ in range(retry_count + 1):
                try:
                    if remote := self._get_remote():
                        remote.control(key)
                    break
                except (ConnectionClosed, BrokenPipeError):
                    # BrokenPipe can occur when the commands is sent to fast
                    self._remote = None
        except (UnhandledResponse, AccessDenied):
            # We got a response so it's on.
            LOGGER.debug("Failed sending command %s", key, exc_info=True)
        except OSError:
            # Different reasons, e.g. hostname not resolveable
            pass

    async def async_power_off(self) -> None:
        """Send power off command to remote."""
        await self.async_send_keys(["KEY_POWEROFF"])
        # Force closing of remote session to provide instant UI feedback
        await self.async_close_remote()

    async def async_close_remote(self) -> None:
        """Close remote object."""
        await self.hass.async_add_executor_job(self._close_remote)

    def _close_remote(self) -> None:
        """Close remote object."""
        try:
            if self._remote is not None:
                # Close the current remote connection
                self._remote.close()
            self._remote = None
        except OSError:
            LOGGER.debug("Could not establish connection")


class SamsungTVWSBridge(SamsungTVBridge):
    """The Bridge for WebSocket TVs."""

    def __init__(
        self,
        hass: HomeAssistant,
        method: str,
        host: str,
        port: int | None = None,
        entry_data: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize Bridge."""
        super().__init__(hass, method, host, port)
        if entry_data:
            self.token = entry_data.get(CONF_TOKEN)
        self._rest_api: SamsungTVAsyncRest | None = None
        self._app_list: dict[str, str] | None = None
        self._device_info: dict[str, Any] | None = None
        self._remote: SamsungTVWSAsyncRemote | None = None
        self._remote_lock = asyncio.Lock()

    async def async_get_app_list(self) -> dict[str, str] | None:
        """Get installed app list."""
        if self._app_list is None:
            if remote := await self._async_get_remote():
                raw_app_list = await remote.app_list()
                self._app_list = {
                    app["name"]: app["appId"]
                    for app in sorted(
                        raw_app_list or [],
                        key=lambda app: cast(str, app["name"]),
                    )
                }
                LOGGER.debug("Generated app list: %s", self._app_list)
        return self._app_list

    def _get_device_spec(self, key: str) -> Any | None:
        """Check if a flag exists in latest device info."""
        if not ((info := self._device_info) and (device := info.get("device"))):
            return None
        return device.get(key)

    async def async_is_on(self) -> bool:
        """Tells if the TV is on."""
        if self._get_device_spec("PowerState") is not None:
            LOGGER.debug("Checking if TV %s is on using device info", self.host)
            # Ensure we get an updated value
            info = await self.async_device_info()
            return info is not None and info["device"]["PowerState"] == "on"
        LOGGER.debug("Checking if TV %s is on using websocket", self.host)
        if remote := await self._async_get_remote():
            return remote.is_alive()
        return False

    async def async_try_connect(self) -> str:
        """Try to connect to the Websocket TV."""
        for self.port in WEBSOCKET_PORTS:
            config = {
                CONF_NAME: VALUE_CONF_NAME,
                CONF_HOST: self.host,
                CONF_METHOD: self.method,
                CONF_PORT: self.port,
                # We need this high timeout because waiting for auth popup is just an open socket
                CONF_TIMEOUT: TIMEOUT_REQUEST,
            }

            result = None
            try:
                LOGGER.debug("Try config: %s", config)
                async with SamsungTVWSAsyncRemote(
                    host=self.host,
                    port=self.port,
                    token=self.token,
                    timeout=TIMEOUT_REQUEST,
                    name=VALUE_CONF_NAME,
                ) as remote:
                    await remote.open()
                    self.token = remote.token
                    LOGGER.debug("Working config: %s", config)
                    return RESULT_SUCCESS
            except ConnectionClosedError as err:
                LOGGER.info(
                    "Working but unsupported config: %s, error: '%s'; this may "
                    "be an indication that access to the TV has been denied. Please "
                    "check the Device Connection Manager on your TV",
                    config,
                    err,
                )
                result = RESULT_NOT_SUPPORTED
            except WebSocketException as err:
                LOGGER.debug(
                    "Working but unsupported config: %s, error: %s", config, err
                )
                result = RESULT_NOT_SUPPORTED
            except (OSError, AsyncioTimeoutError, ConnectionFailure) as err:
                LOGGER.debug("Failing config: %s, error: %s", config, err)
        # pylint: disable=useless-else-on-loop
        else:
            if result:
                return result

        return RESULT_CANNOT_CONNECT

    async def async_device_info(self) -> dict[str, Any] | None:
        """Try to gather infos of this TV."""
        if self._rest_api is None:
            assert self.port
            self._rest_api = SamsungTVAsyncRest(
                host=self.host,
                session=async_get_clientsession(self.hass),
                port=self.port,
                timeout=TIMEOUT_WEBSOCKET,
            )

        with contextlib.suppress(HttpApiError, AsyncioTimeoutError):
            device_info: dict[str, Any] = await self._rest_api.rest_device_info()
            LOGGER.debug("Device info on %s is: %s", self.host, device_info)
            self._device_info = device_info
            return device_info

        return None

    async def async_launch_app(self, app_id: str) -> None:
        """Send the launch_app command using websocket protocol."""
        await self._async_send_commands([ChannelEmitCommand.launch_app(app_id)])

    async def async_send_keys(self, keys: list[str]) -> None:
        """Send a list of keys using websocket protocol."""
        await self._async_send_commands([SendRemoteKey.click(key) for key in keys])

    async def _async_send_commands(self, commands: list[SamsungTVCommand]) -> None:
        """Send the commands using websocket protocol."""
        try:
            # recreate connection if connection was dead
            retry_count = 1
            for _ in range(retry_count + 1):
                try:
                    if remote := await self._async_get_remote():
                        await remote.send_command(commands)
                    break
                except (
                    BrokenPipeError,
                    WebSocketException,
                ):
                    # BrokenPipe can occur when the commands is sent to fast
                    # WebSocketException can occur when timed out
                    self._remote = None
        except OSError:
            # Different reasons, e.g. hostname not resolveable
            pass

    async def _async_get_remote(self) -> SamsungTVWSAsyncRemote | None:
        """Create or return a remote control instance."""
        if (remote := self._remote) and remote.is_alive():
            # If we have one then try to use it
            return remote

        async with self._remote_lock:
            # If we don't have one make sure we do it under the lock
            # so we don't make two do due a race to get the remote
            return await self._async_get_remote_under_lock()

    async def _async_get_remote_under_lock(self) -> SamsungTVWSAsyncRemote | None:
        """Create or return a remote control instance."""
        if self._remote is None or not self._remote.is_alive():
            # We need to create a new instance to reconnect.
            LOGGER.debug("Create SamsungTVWSBridge for %s", self.host)
            assert self.port
            self._remote = SamsungTVWSAsyncRemote(
                host=self.host,
                port=self.port,
                token=self.token,
                timeout=TIMEOUT_WEBSOCKET,
                name=VALUE_CONF_NAME,
            )
            try:
                await self._remote.start_listening(self._remote_event)
            except ConnectionClosedError as err:
                # This is only happening when the auth was switched to DENY
                # A removed auth will lead to socket timeout because waiting
                # for auth popup is just an open socket
                LOGGER.info(
                    "Failed to get remote for %s, re-authentication required: %s",
                    self.host,
                    err.__repr__(),
                )
                self._notify_reauth_callback()
            except ConnectionFailure as err:
                LOGGER.warning(
                    "Unexpected ConnectionFailure trying to get remote for %s, "
                    "please report this issue: %s",
                    self.host,
                    err.__repr__(),
                )
                self._remote = None
            except (WebSocketException, AsyncioTimeoutError, OSError) as err:
                LOGGER.debug(
                    "Failed to get remote for %s: %s", self.host, err.__repr__()
                )
                self._remote = None
            else:
                LOGGER.debug("Created SamsungTVWSBridge for %s", self.host)
                if self._device_info is None:
                    # Initialise device info on first connect
                    await self.async_device_info()
                if self.token != self._remote.token:
                    LOGGER.info(
                        "SamsungTVWSBridge has provided a new token %s",
                        self._remote.token,
                    )
                    self.token = self._remote.token
                    self._notify_update_config_entry({CONF_TOKEN: self.token})
        return self._remote

    @staticmethod
    def _remote_event(event: str, response: Any) -> None:
        """Received event from remote websocket."""
        if event == MS_ERROR_EVENT:
            # { 'event': 'ms.error',
            #   'data': {'message': 'unrecognized method value : ms.remote.control'}}
            if (data := response.get("data")) and (
                message := data.get("message")
            ) == "unrecognized method value : ms.remote.control":
                LOGGER.error(
                    "Your TV seems to be unsupported by "
                    "SamsungTVWSBridge and may need a PIN: '%s'",
                    message,
                )

    async def async_power_off(self) -> None:
        """Send power off command to remote."""
        if self._get_device_spec("FrameTVSupport") == "true":
            await self._async_send_commands(SendRemoteKey.hold("KEY_POWER", 3))
        else:
            await self._async_send_commands([SendRemoteKey.click("KEY_POWER")])
        # Force closing of remote session to provide instant UI feedback
        await self.async_close_remote()

    async def async_close_remote(self) -> None:
        """Close remote object."""
        try:
            if self._remote is not None:
                # Close the current remote connection
                await self._remote.close()
            self._remote = None
        except OSError as err:
            LOGGER.debug(
                "Error closing connection to %s: %s", self.host, err.__repr__()
            )
