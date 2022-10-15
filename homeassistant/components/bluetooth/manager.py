"""The bluetooth integration."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
import itertools
import logging
import time
from typing import TYPE_CHECKING, Any, Final

from bleak.backends.scanner import AdvertisementDataCallback

from homeassistant import config_entries
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    HomeAssistant,
    callback as hass_callback,
)
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.event import async_track_time_interval

from .advertisement_tracker import AdvertisementTracker
from .const import (
    ADAPTER_ADDRESS,
    ADAPTER_PASSIVE_SCAN,
    FALLBACK_MAXIMUM_STALE_ADVERTISEMENT_SECONDS,
    NO_RSSI_VALUE,
    UNAVAILABLE_TRACK_SECONDS,
    AdapterDetails,
)
from .match import (
    ADDRESS,
    CALLBACK,
    CONNECTABLE,
    BluetoothCallbackMatcher,
    BluetoothCallbackMatcherIndex,
    BluetoothCallbackMatcherWithCallback,
    IntegrationMatcher,
    ble_device_matches,
)
from .models import (
    BaseHaScanner,
    BluetoothCallback,
    BluetoothChange,
    BluetoothServiceInfoBleak,
)
from .usage import install_multiple_bleak_catcher, uninstall_multiple_bleak_catcher
from .util import async_get_bluetooth_adapters, async_load_history_from_system

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData


FILTER_UUIDS: Final = "UUIDs"

APPLE_MFR_ID: Final = 76
APPLE_IBEACON_START_BYTE: Final = 0x02  # iBeacon (tilt_ble)
APPLE_HOMEKIT_START_BYTE: Final = 0x06  # homekit_controller
APPLE_DEVICE_ID_START_BYTE: Final = 0x10  # bluetooth_le_tracker
APPLE_START_BYTES_WANTED: Final = {
    APPLE_IBEACON_START_BYTE,
    APPLE_HOMEKIT_START_BYTE,
    APPLE_DEVICE_ID_START_BYTE,
}

RSSI_SWITCH_THRESHOLD = 6

MONOTONIC_TIME: Final = time.monotonic

_LOGGER = logging.getLogger(__name__)


def _dispatch_bleak_callback(
    callback: AdvertisementDataCallback | None,
    filters: dict[str, set[str]],
    device: BLEDevice,
    advertisement_data: AdvertisementData,
) -> None:
    """Dispatch the callback."""
    if not callback:
        # Callback destroyed right before being called, ignore
        return  # pragma: no cover

    if (uuids := filters.get(FILTER_UUIDS)) and not uuids.intersection(
        advertisement_data.service_uuids
    ):
        return

    try:
        callback(device, advertisement_data)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Error in callback: %s", callback)


class BluetoothManager:
    """Manage Bluetooth."""

    def __init__(
        self,
        hass: HomeAssistant,
        integration_matcher: IntegrationMatcher,
    ) -> None:
        """Init bluetooth manager."""
        self.hass = hass
        self._integration_matcher = integration_matcher
        self._cancel_unavailable_tracking: CALLBACK_TYPE | None = None

        self._advertisement_tracker = AdvertisementTracker()

        self._unavailable_callbacks: dict[
            str, list[Callable[[BluetoothServiceInfoBleak], None]]
        ] = {}
        self._connectable_unavailable_callbacks: dict[
            str, list[Callable[[BluetoothServiceInfoBleak], None]]
        ] = {}

        self._callback_index = BluetoothCallbackMatcherIndex()
        self._bleak_callbacks: list[
            tuple[AdvertisementDataCallback, dict[str, set[str]]]
        ] = []
        self._history: dict[str, BluetoothServiceInfoBleak] = {}
        self._connectable_history: dict[str, BluetoothServiceInfoBleak] = {}
        self._non_connectable_scanners: list[BaseHaScanner] = []
        self._connectable_scanners: list[BaseHaScanner] = []
        self._adapters: dict[str, AdapterDetails] = {}

    @property
    def supports_passive_scan(self) -> bool:
        """Return if passive scan is supported."""
        return any(adapter[ADAPTER_PASSIVE_SCAN] for adapter in self._adapters.values())

    def async_scanner_count(self, connectable: bool = True) -> int:
        """Return the number of scanners."""
        if connectable:
            return len(self._connectable_scanners)
        return len(self._connectable_scanners) + len(self._non_connectable_scanners)

    async def async_diagnostics(self) -> dict[str, Any]:
        """Diagnostics for the manager."""
        scanner_diagnostics = await asyncio.gather(
            *[
                scanner.async_diagnostics()
                for scanner in itertools.chain(
                    self._non_connectable_scanners, self._connectable_scanners
                )
            ]
        )
        return {
            "adapters": self._adapters,
            "scanners": scanner_diagnostics,
            "connectable_history": [
                service_info.as_dict()
                for service_info in self._connectable_history.values()
            ],
            "history": [
                service_info.as_dict() for service_info in self._history.values()
            ],
            "advertisement_tracker": self._advertisement_tracker.async_diagnostics(),
        }

    def _find_adapter_by_address(self, address: str) -> str | None:
        for adapter, details in self._adapters.items():
            if details[ADAPTER_ADDRESS] == address:
                return adapter
        return None

    async def async_get_bluetooth_adapters(
        self, cached: bool = True
    ) -> dict[str, AdapterDetails]:
        """Get bluetooth adapters."""
        if not cached or not self._adapters:
            self._adapters = await async_get_bluetooth_adapters()
        return self._adapters

    async def async_get_adapter_from_address(self, address: str) -> str | None:
        """Get adapter from address."""
        if adapter := self._find_adapter_by_address(address):
            return adapter
        self._adapters = await async_get_bluetooth_adapters()
        return self._find_adapter_by_address(address)

    async def async_setup(self) -> None:
        """Set up the bluetooth manager."""
        install_multiple_bleak_catcher()
        history = await async_load_history_from_system()
        # Everything is connectable so it fall into both
        # buckets since the host system can only provide
        # connectable devices
        self._history = history.copy()
        self._connectable_history = history.copy()
        self.async_setup_unavailable_tracking()

    @hass_callback
    def async_stop(self, event: Event) -> None:
        """Stop the Bluetooth integration at shutdown."""
        _LOGGER.debug("Stopping bluetooth manager")
        if self._cancel_unavailable_tracking:
            self._cancel_unavailable_tracking()
            self._cancel_unavailable_tracking = None
        uninstall_multiple_bleak_catcher()

    async def async_get_devices_by_address(
        self, address: str, connectable: bool
    ) -> list[BLEDevice]:
        """Get devices by address."""
        types_ = (True,) if connectable else (True, False)
        return [
            device
            for device in await asyncio.gather(
                *(
                    scanner.async_get_device_by_address(address)
                    for type_ in types_
                    for scanner in self._get_scanners_by_type(type_)
                )
            )
            if device is not None
        ]

    @hass_callback
    def async_all_discovered_devices(self, connectable: bool) -> Iterable[BLEDevice]:
        """Return all of discovered devices from all the scanners including duplicates."""
        yield from itertools.chain.from_iterable(
            scanner.discovered_devices for scanner in self._get_scanners_by_type(True)
        )
        if not connectable:
            yield from itertools.chain.from_iterable(
                scanner.discovered_devices
                for scanner in self._get_scanners_by_type(False)
            )

    @hass_callback
    def async_discovered_devices(self, connectable: bool) -> list[BLEDevice]:
        """Return all of combined best path to discovered from all the scanners."""
        return [
            history.device
            for history in self._get_history_by_type(connectable).values()
        ]

    @hass_callback
    def async_setup_unavailable_tracking(self) -> None:
        """Set up the unavailable tracking."""
        self._cancel_unavailable_tracking = async_track_time_interval(
            self.hass,
            self._async_check_unavailable,
            timedelta(seconds=UNAVAILABLE_TRACK_SECONDS),
        )

    @hass_callback
    def _async_check_unavailable(self, now: datetime) -> None:
        """Watch for unavailable devices and cleanup state history."""
        monotonic_now = MONOTONIC_TIME()
        connectable_history = self._connectable_history
        all_history = self._history
        removed_addresses: set[str] = set()

        for connectable in (True, False):
            unavailable_callbacks = self._get_unavailable_callbacks_by_type(connectable)
            intervals = self._advertisement_tracker.intervals
            history = connectable_history if connectable else all_history
            history_set = set(history)
            active_addresses = {
                device.address
                for device in self.async_all_discovered_devices(connectable)
            }
            disappeared = history_set.difference(active_addresses)
            for address in disappeared:
                #
                # For non-connectable devices we also check the device has exceeded
                # the advertising interval before we mark it as unavailable
                # since it may have gone to sleep and since we do not need an active connection
                # to it we can only determine its availability by the lack of advertisements
                #
                if not connectable and (advertising_interval := intervals.get(address)):
                    time_since_seen = monotonic_now - history[address].time
                    if time_since_seen <= advertising_interval:
                        continue

                service_info = history.pop(address)
                removed_addresses.add(address)

                if not (callbacks := unavailable_callbacks.get(address)):
                    continue

                for callback in callbacks:
                    try:
                        callback(service_info)
                    except Exception:  # pylint: disable=broad-except
                        _LOGGER.exception("Error in unavailable callback")

        # If we removed the device from both the connectable history
        # and all history then we can remove it from the advertisement tracker
        for address in removed_addresses:
            if address not in connectable_history and address not in all_history:
                self._advertisement_tracker.async_remove_address(address)

    def _prefer_previous_adv_from_different_source(
        self, old: BluetoothServiceInfoBleak, new: BluetoothServiceInfoBleak
    ) -> bool:
        """Prefer previous advertisement from a different source if it is better."""
        if new.time - old.time > (
            stale_seconds := self._advertisement_tracker.intervals.get(
                new.address, FALLBACK_MAXIMUM_STALE_ADVERTISEMENT_SECONDS
            )
        ):
            # If the old advertisement is stale, any new advertisement is preferred
            _LOGGER.debug(
                "%s (%s): Switching from %s[%s] to %s[%s] (time elapsed:%s > stale seconds:%s)",
                new.advertisement.local_name,
                new.device.address,
                old.source,
                old.connectable,
                new.source,
                new.connectable,
                new.time - old.time,
                stale_seconds,
            )
            return False
        if new.device.rssi - RSSI_SWITCH_THRESHOLD > (old.device.rssi or NO_RSSI_VALUE):
            # If new advertisement is RSSI_SWITCH_THRESHOLD more, the new one is preferred
            _LOGGER.debug(
                "%s (%s): Switching from %s[%s] to %s[%s] (new rssi:%s - threshold:%s > old rssi:%s)",
                new.advertisement.local_name,
                new.device.address,
                old.source,
                old.connectable,
                new.source,
                new.connectable,
                new.device.rssi,
                RSSI_SWITCH_THRESHOLD,
                old.device.rssi,
            )
            return False
        return True

    @hass_callback
    def scanner_adv_received(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Handle a new advertisement from any scanner.

        Callbacks from all the scanners arrive here.
        """

        # Pre-filter noisy apple devices as they can account for 20-35% of the
        # traffic on a typical network.
        advertisement_data = service_info.advertisement
        manufacturer_data = advertisement_data.manufacturer_data
        if (
            len(manufacturer_data) == 1
            and (apple_data := manufacturer_data.get(APPLE_MFR_ID))
            and apple_data[0] not in APPLE_START_BYTES_WANTED
            and not advertisement_data.service_data
        ):
            return

        device = service_info.device
        connectable = service_info.connectable
        address = device.address
        all_history = self._connectable_history if connectable else self._history
        source = service_info.source
        if (
            (old_service_info := all_history.get(address))
            and source != old_service_info.source
            and self._prefer_previous_adv_from_different_source(
                old_service_info, service_info
            )
        ):
            return

        self._history[address] = service_info

        if connectable:
            self._connectable_history[address] = service_info
            # Bleak callbacks must get a connectable device

        # Track advertisement intervals to determine when we need to
        # switch adapters or mark a device as unavailable
        tracker = self._advertisement_tracker
        if (last_source := tracker.sources.get(address)) and last_source != source:
            # Source changed, remove the old address from the tracker
            tracker.async_remove_address(address)
        if address not in tracker.intervals:
            tracker.async_collect(service_info)

        # If the advertisement data is the same as the last time we saw it, we
        # don't need to do anything else.
        if old_service_info and not (
            service_info.manufacturer_data != old_service_info.manufacturer_data
            or service_info.service_data != old_service_info.service_data
            or service_info.service_uuids != old_service_info.service_uuids
            or service_info.name != old_service_info.name
        ):
            return

        if connectable:
            # Bleak callbacks must get a connectable device
            for callback_filters in self._bleak_callbacks:
                _dispatch_bleak_callback(*callback_filters, device, advertisement_data)

        matched_domains = self._integration_matcher.match_domains(service_info)
        _LOGGER.debug(
            "%s: %s %s connectable: %s match: %s rssi: %s",
            source,
            address,
            advertisement_data,
            connectable,
            matched_domains,
            device.rssi,
        )

        for match in self._callback_index.match_callbacks(service_info):
            callback = match[CALLBACK]
            try:
                callback(service_info, BluetoothChange.ADVERTISEMENT)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Error in bluetooth callback")

        for domain in matched_domains:
            discovery_flow.async_create_flow(
                self.hass,
                domain,
                {"source": config_entries.SOURCE_BLUETOOTH},
                service_info,
            )

    @hass_callback
    def async_track_unavailable(
        self,
        callback: Callable[[BluetoothServiceInfoBleak], None],
        address: str,
        connectable: bool,
    ) -> Callable[[], None]:
        """Register a callback."""
        unavailable_callbacks = self._get_unavailable_callbacks_by_type(connectable)
        unavailable_callbacks.setdefault(address, []).append(callback)

        @hass_callback
        def _async_remove_callback() -> None:
            unavailable_callbacks[address].remove(callback)
            if not unavailable_callbacks[address]:
                del unavailable_callbacks[address]

        return _async_remove_callback

    @hass_callback
    def async_register_callback(
        self,
        callback: BluetoothCallback,
        matcher: BluetoothCallbackMatcher | None,
    ) -> Callable[[], None]:
        """Register a callback."""
        callback_matcher = BluetoothCallbackMatcherWithCallback(callback=callback)
        if not matcher:
            callback_matcher[CONNECTABLE] = True
        else:
            # We could write out every item in the typed dict here
            # but that would be a bit inefficient and verbose.
            callback_matcher.update(matcher)  # type: ignore[typeddict-item]
            callback_matcher[CONNECTABLE] = matcher.get(CONNECTABLE, True)

        connectable = callback_matcher[CONNECTABLE]
        self._callback_index.add_callback_matcher(callback_matcher)

        @hass_callback
        def _async_remove_callback() -> None:
            self._callback_index.remove_callback_matcher(callback_matcher)

        # If we have history for the subscriber, we can trigger the callback
        # immediately with the last packet so the subscriber can see the
        # device.
        all_history = self._get_history_by_type(connectable)
        if (
            (address := callback_matcher.get(ADDRESS))
            and (service_info := all_history.get(address))
            and ble_device_matches(callback_matcher, service_info)
        ):
            try:
                callback(service_info, BluetoothChange.ADVERTISEMENT)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Error in bluetooth callback")

        return _async_remove_callback

    @hass_callback
    def async_ble_device_from_address(
        self, address: str, connectable: bool
    ) -> BLEDevice | None:
        """Return the BLEDevice if present."""
        all_history = self._get_history_by_type(connectable)
        if history := all_history.get(address):
            return history.device
        return None

    @hass_callback
    def async_address_present(self, address: str, connectable: bool) -> bool:
        """Return if the address is present."""
        return address in self._get_history_by_type(connectable)

    @hass_callback
    def async_discovered_service_info(
        self, connectable: bool
    ) -> Iterable[BluetoothServiceInfoBleak]:
        """Return all the discovered services info."""
        return self._get_history_by_type(connectable).values()

    @hass_callback
    def async_last_service_info(
        self, address: str, connectable: bool
    ) -> BluetoothServiceInfoBleak | None:
        """Return the last service info for an address."""
        return self._get_history_by_type(connectable).get(address)

    @hass_callback
    def async_rediscover_address(self, address: str) -> None:
        """Trigger discovery of devices which have already been seen."""
        self._integration_matcher.async_clear_address(address)

    def _get_scanners_by_type(self, connectable: bool) -> list[BaseHaScanner]:
        """Return the scanners by type."""
        return (
            self._connectable_scanners
            if connectable
            else self._non_connectable_scanners
        )

    def _get_unavailable_callbacks_by_type(
        self, connectable: bool
    ) -> dict[str, list[Callable[[BluetoothServiceInfoBleak], None]]]:
        """Return the unavailable callbacks by type."""
        return (
            self._connectable_unavailable_callbacks
            if connectable
            else self._unavailable_callbacks
        )

    def _get_history_by_type(
        self, connectable: bool
    ) -> dict[str, BluetoothServiceInfoBleak]:
        """Return the history by type."""
        return self._connectable_history if connectable else self._history

    def async_register_scanner(
        self, scanner: BaseHaScanner, connectable: bool
    ) -> CALLBACK_TYPE:
        """Register a new scanner."""
        scanners = self._get_scanners_by_type(connectable)

        def _unregister_scanner() -> None:
            self._advertisement_tracker.async_remove_source(scanner.source)
            scanners.remove(scanner)

        scanners.append(scanner)
        return _unregister_scanner

    @hass_callback
    def async_register_bleak_callback(
        self, callback: AdvertisementDataCallback, filters: dict[str, set[str]]
    ) -> CALLBACK_TYPE:
        """Register a callback."""
        callback_entry = (callback, filters)
        self._bleak_callbacks.append(callback_entry)

        @hass_callback
        def _remove_callback() -> None:
            self._bleak_callbacks.remove(callback_entry)

        # Replay the history since otherwise we miss devices
        # that were already discovered before the callback was registered
        # or we are in passive mode
        for history in self._connectable_history.values():
            _dispatch_bleak_callback(
                callback, filters, history.device, history.advertisement
            )

        return _remove_callback
