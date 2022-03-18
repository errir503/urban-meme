"""Support for August devices."""
from __future__ import annotations

import asyncio
from collections.abc import ValuesView
from itertools import chain
import logging

from aiohttp import ClientError, ClientResponseError
from yalexs.doorbell import Doorbell, DoorbellDetail
from yalexs.exceptions import AugustApiAIOHTTPError
from yalexs.lock import Lock, LockDetail
from yalexs.pubnub_activity import activities_from_pubnub_message
from yalexs.pubnub_async import AugustPubNub, async_create_pubnub

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)

from .activity import ActivityStream
from .const import DOMAIN, MIN_TIME_BETWEEN_DETAIL_UPDATES, PLATFORMS
from .exceptions import CannotConnect, InvalidAuth, RequireValidation
from .gateway import AugustGateway
from .subscriber import AugustSubscriberMixin

_LOGGER = logging.getLogger(__name__)

API_CACHED_ATTRS = {
    "door_state",
    "door_state_datetime",
    "lock_status",
    "lock_status_datetime",
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up August from a config entry."""

    august_gateway = AugustGateway(hass)

    try:
        await august_gateway.async_setup(entry.data)
        return await async_setup_august(hass, entry, august_gateway)
    except (RequireValidation, InvalidAuth) as err:
        raise ConfigEntryAuthFailed from err
    except asyncio.TimeoutError as err:
        raise ConfigEntryNotReady("Timed out connecting to august api") from err
    except (AugustApiAIOHTTPError, ClientResponseError, CannotConnect) as err:
        raise ConfigEntryNotReady from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    data: AugustData = hass.data[DOMAIN][entry.entry_id]
    data.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_setup_august(
    hass: HomeAssistant, config_entry: ConfigEntry, august_gateway: AugustGateway
) -> bool:
    """Set up the August component."""

    if CONF_PASSWORD in config_entry.data:
        # We no longer need to store passwords since we do not
        # support YAML anymore
        config_data = config_entry.data.copy()
        del config_data[CONF_PASSWORD]
        hass.config_entries.async_update_entry(config_entry, data=config_data)

    await august_gateway.async_authenticate()
    await august_gateway.async_refresh_access_token_if_needed()

    hass.data.setdefault(DOMAIN, {})
    data = hass.data[DOMAIN][config_entry.entry_id] = AugustData(hass, august_gateway)
    await data.async_setup()

    hass.config_entries.async_setup_platforms(config_entry, PLATFORMS)

    return True


class AugustData(AugustSubscriberMixin):
    """August data object."""

    def __init__(self, hass, august_gateway):
        """Init August data object."""
        super().__init__(hass, MIN_TIME_BETWEEN_DETAIL_UPDATES)
        self._hass = hass
        self._august_gateway = august_gateway
        self.activity_stream = None
        self._api = august_gateway.api
        self._device_detail_by_id = {}
        self._doorbells_by_id = {}
        self._locks_by_id = {}
        self._house_ids = set()
        self._pubnub_unsub = None

    async def async_setup(self):
        """Async setup of august device data and activities."""
        token = self._august_gateway.access_token
        # This used to be a gather but it was less reliable with august's recent api changes.
        user_data = await self._api.async_get_user(token)
        locks = await self._api.async_get_operable_locks(token)
        doorbells = await self._api.async_get_doorbells(token)
        if not doorbells:
            doorbells = []
        if not locks:
            locks = []

        self._doorbells_by_id = {device.device_id: device for device in doorbells}
        self._locks_by_id = {device.device_id: device for device in locks}
        self._house_ids = {device.house_id for device in chain(locks, doorbells)}

        await self._async_refresh_device_detail_by_ids(
            [device.device_id for device in chain(locks, doorbells)]
        )

        # We remove all devices that we are missing
        # detail as we cannot determine if they are usable.
        # This also allows us to avoid checking for
        # detail being None all over the place
        self._remove_inoperative_locks()
        self._remove_inoperative_doorbells()

        pubnub = AugustPubNub()
        for device in self._device_detail_by_id.values():
            pubnub.register_device(device)

        self.activity_stream = ActivityStream(
            self._hass, self._api, self._august_gateway, self._house_ids, pubnub
        )
        await self.activity_stream.async_setup()
        pubnub.subscribe(self.async_pubnub_message)
        self._pubnub_unsub = async_create_pubnub(user_data["UserID"], pubnub)

        if self._locks_by_id:
            # Do not prevent setup as the sync can timeout
            # but it is not a fatal error as the lock
            # will recover automatically when it comes back online.
            asyncio.create_task(self._async_initial_sync())

    async def _async_initial_sync(self):
        """Attempt to request an initial sync."""
        # We don't care if this fails because we only want to wake
        # locks that are actually online anyways and they will be
        # awake when they come back online
        for result in await asyncio.gather(
            *[
                self.async_status_async(
                    device_id, bool(detail.bridge and detail.bridge.hyper_bridge)
                )
                for device_id, detail in self._device_detail_by_id.items()
                if device_id in self._locks_by_id
            ],
            return_exceptions=True,
        ):
            if isinstance(result, Exception) and not isinstance(
                result, (asyncio.TimeoutError, ClientResponseError, CannotConnect)
            ):
                _LOGGER.warning(
                    "Unexpected exception during initial sync: %s",
                    result,
                    exc_info=result,
                )

    @callback
    def async_pubnub_message(self, device_id, date_time, message):
        """Process a pubnub message."""
        device = self.get_device_detail(device_id)
        activities = activities_from_pubnub_message(device, date_time, message)
        if activities:
            self.activity_stream.async_process_newer_device_activities(activities)
            self.async_signal_device_id_update(device.device_id)
        self.activity_stream.async_schedule_house_id_refresh(device.house_id)

    @callback
    def async_stop(self):
        """Stop the subscriptions."""
        self._pubnub_unsub()
        self.activity_stream.async_stop()

    @property
    def doorbells(self) -> ValuesView[Doorbell]:
        """Return a list of py-august Doorbell objects."""
        return self._doorbells_by_id.values()

    @property
    def locks(self) -> ValuesView[Lock]:
        """Return a list of py-august Lock objects."""
        return self._locks_by_id.values()

    def get_device_detail(self, device_id: str) -> DoorbellDetail | LockDetail:
        """Return the py-august LockDetail or DoorbellDetail object for a device."""
        return self._device_detail_by_id[device_id]

    async def _async_refresh(self, time):
        await self._async_refresh_device_detail_by_ids(self._subscriptions.keys())

    async def _async_refresh_device_detail_by_ids(self, device_ids_list):
        """Refresh each device in sequence.

        This used to be a gather but it was less reliable with august's
        recent api changes.

        The august api has been timing out for some devices so
        we want the ones that it isn't timing out for to keep working.
        """
        for device_id in device_ids_list:
            try:
                await self._async_refresh_device_detail_by_id(device_id)
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Timed out calling august api during refresh of device: %s",
                    device_id,
                )
            except (ClientResponseError, CannotConnect) as err:
                _LOGGER.warning(
                    "Error from august api during refresh of device: %s",
                    device_id,
                    exc_info=err,
                )

    async def _async_refresh_device_detail_by_id(self, device_id):
        if device_id in self._locks_by_id:
            if self.activity_stream and self.activity_stream.pubnub.connected:
                saved_attrs = _save_live_attrs(self._device_detail_by_id[device_id])
            await self._async_update_device_detail(
                self._locks_by_id[device_id], self._api.async_get_lock_detail
            )
            if self.activity_stream and self.activity_stream.pubnub.connected:
                _restore_live_attrs(self._device_detail_by_id[device_id], saved_attrs)
            # keypads are always attached to locks
            if (
                device_id in self._device_detail_by_id
                and self._device_detail_by_id[device_id].keypad is not None
            ):
                keypad = self._device_detail_by_id[device_id].keypad
                self._device_detail_by_id[keypad.device_id] = keypad
        elif device_id in self._doorbells_by_id:
            await self._async_update_device_detail(
                self._doorbells_by_id[device_id],
                self._api.async_get_doorbell_detail,
            )
        _LOGGER.debug(
            "async_signal_device_id_update (from detail updates): %s", device_id
        )
        self.async_signal_device_id_update(device_id)

    async def _async_update_device_detail(self, device, api_call):
        _LOGGER.debug(
            "Started retrieving detail for %s (%s)",
            device.device_name,
            device.device_id,
        )

        try:
            self._device_detail_by_id[device.device_id] = await api_call(
                self._august_gateway.access_token, device.device_id
            )
        except ClientError as ex:
            _LOGGER.error(
                "Request error trying to retrieve %s details for %s. %s",
                device.device_id,
                device.device_name,
                ex,
            )
        _LOGGER.debug(
            "Completed retrieving detail for %s (%s)",
            device.device_name,
            device.device_id,
        )

    def _get_device_name(self, device_id):
        """Return doorbell or lock name as August has it stored."""
        if device_id in self._locks_by_id:
            return self._locks_by_id[device_id].device_name
        if device_id in self._doorbells_by_id:
            return self._doorbells_by_id[device_id].device_name

    async def async_lock(self, device_id):
        """Lock the device."""
        return await self._async_call_api_op_requires_bridge(
            device_id,
            self._api.async_lock_return_activities,
            self._august_gateway.access_token,
            device_id,
        )

    async def async_status_async(self, device_id, hyper_bridge):
        """Request status of the the device but do not wait for a response since it will come via pubnub."""
        return await self._async_call_api_op_requires_bridge(
            device_id,
            self._api.async_status_async,
            self._august_gateway.access_token,
            device_id,
            hyper_bridge,
        )

    async def async_lock_async(self, device_id, hyper_bridge):
        """Lock the device but do not wait for a response since it will come via pubnub."""
        return await self._async_call_api_op_requires_bridge(
            device_id,
            self._api.async_lock_async,
            self._august_gateway.access_token,
            device_id,
            hyper_bridge,
        )

    async def async_unlock(self, device_id):
        """Unlock the device."""
        return await self._async_call_api_op_requires_bridge(
            device_id,
            self._api.async_unlock_return_activities,
            self._august_gateway.access_token,
            device_id,
        )

    async def async_unlock_async(self, device_id, hyper_bridge):
        """Unlock the device but do not wait for a response since it will come via pubnub."""
        return await self._async_call_api_op_requires_bridge(
            device_id,
            self._api.async_unlock_async,
            self._august_gateway.access_token,
            device_id,
            hyper_bridge,
        )

    async def _async_call_api_op_requires_bridge(
        self, device_id, func, *args, **kwargs
    ):
        """Call an API that requires the bridge to be online and will change the device state."""
        ret = None
        try:
            ret = await func(*args, **kwargs)
        except AugustApiAIOHTTPError as err:
            device_name = self._get_device_name(device_id)
            if device_name is None:
                device_name = f"DeviceID: {device_id}"
            raise HomeAssistantError(f"{device_name}: {err}") from err

        return ret

    def _remove_inoperative_doorbells(self):
        for doorbell in list(self.doorbells):
            device_id = doorbell.device_id
            if self._device_detail_by_id.get(device_id):
                continue
            _LOGGER.info(
                "The doorbell %s could not be setup because the system could not fetch details about the doorbell",
                doorbell.device_name,
            )
            del self._doorbells_by_id[device_id]

    def _remove_inoperative_locks(self):
        # Remove non-operative locks as there must
        # be a bridge (August Connect) for them to
        # be usable
        for lock in list(self.locks):
            device_id = lock.device_id
            lock_detail = self._device_detail_by_id.get(device_id)
            if lock_detail is None:
                _LOGGER.info(
                    "The lock %s could not be setup because the system could not fetch details about the lock",
                    lock.device_name,
                )
            elif lock_detail.bridge is None:
                _LOGGER.info(
                    "The lock %s could not be setup because it does not have a bridge (Connect)",
                    lock.device_name,
                )
                del self._device_detail_by_id[device_id]
            # Bridge may come back online later so we still add the device since we will
            # have a pubnub subscription to tell use when it recovers
            else:
                continue
            del self._locks_by_id[device_id]


def _save_live_attrs(lock_detail):
    """Store the attributes that the lock detail api may have an invalid cache for.

    Since we are connected to pubnub we may have more current data
    then the api so we want to restore the most current data after
    updating battery state etc.
    """
    return {attr: getattr(lock_detail, attr) for attr in API_CACHED_ATTRS}


def _restore_live_attrs(lock_detail, attrs):
    """Restore the non-cache attributes after a cached update."""
    for attr, value in attrs.items():
        setattr(lock_detail, attr, value)
