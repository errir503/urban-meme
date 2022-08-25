"""The bluetooth integration matchers."""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import translate
from functools import lru_cache
import re
from typing import TYPE_CHECKING, Final, TypedDict

from lru import LRU  # pylint: disable=no-name-in-module

from homeassistant.loader import BluetoothMatcher, BluetoothMatcherOptional

from .models import BluetoothServiceInfoBleak

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from bleak.backends.scanner import AdvertisementData


MAX_REMEMBER_ADDRESSES: Final = 2048


ADDRESS: Final = "address"
CONNECTABLE: Final = "connectable"
LOCAL_NAME: Final = "local_name"
SERVICE_UUID: Final = "service_uuid"
SERVICE_DATA_UUID: Final = "service_data_uuid"
MANUFACTURER_ID: Final = "manufacturer_id"
MANUFACTURER_DATA_START: Final = "manufacturer_data_start"


class BluetoothCallbackMatcherOptional(TypedDict, total=False):
    """Matcher for the bluetooth integration for callback optional fields."""

    address: str


class BluetoothCallbackMatcher(
    BluetoothMatcherOptional,
    BluetoothCallbackMatcherOptional,
):
    """Callback matcher for the bluetooth integration."""


@dataclass(frozen=False)
class IntegrationMatchHistory:
    """Track which fields have been seen."""

    manufacturer_data: bool
    service_data: set[str]
    service_uuids: set[str]


def seen_all_fields(
    previous_match: IntegrationMatchHistory, advertisement_data: AdvertisementData
) -> bool:
    """Return if we have seen all fields."""
    if not previous_match.manufacturer_data and advertisement_data.manufacturer_data:
        return False
    if advertisement_data.service_data and (
        not previous_match.service_data
        or not previous_match.service_data.issuperset(advertisement_data.service_data)
    ):
        return False
    if advertisement_data.service_uuids and (
        not previous_match.service_uuids
        or not previous_match.service_uuids.issuperset(advertisement_data.service_uuids)
    ):
        return False
    return True


class IntegrationMatcher:
    """Integration matcher for the bluetooth integration."""

    def __init__(self, integration_matchers: list[BluetoothMatcher]) -> None:
        """Initialize the matcher."""
        self._integration_matchers = integration_matchers
        # Some devices use a random address so we need to use
        # an LRU to avoid memory issues.
        self._matched: MutableMapping[str, IntegrationMatchHistory] = LRU(
            MAX_REMEMBER_ADDRESSES
        )
        self._matched_connectable: MutableMapping[str, IntegrationMatchHistory] = LRU(
            MAX_REMEMBER_ADDRESSES
        )

    def async_clear_address(self, address: str) -> None:
        """Clear the history matches for a set of domains."""
        self._matched.pop(address, None)
        self._matched_connectable.pop(address, None)

    def _get_matched_by_type(
        self, connectable: bool
    ) -> MutableMapping[str, IntegrationMatchHistory]:
        """Return the matches by type."""
        return self._matched_connectable if connectable else self._matched

    def match_domains(self, service_info: BluetoothServiceInfoBleak) -> set[str]:
        """Return the domains that are matched."""
        device = service_info.device
        advertisement_data = service_info.advertisement
        matched = self._get_matched_by_type(service_info.connectable)
        matched_domains: set[str] = set()
        if (previous_match := matched.get(device.address)) and seen_all_fields(
            previous_match, advertisement_data
        ):
            # We have seen all fields so we can skip the rest of the matchers
            return matched_domains
        matched_domains = {
            matcher["domain"]
            for matcher in self._integration_matchers
            if ble_device_matches(matcher, service_info)
        }
        if not matched_domains:
            return matched_domains
        if previous_match:
            previous_match.manufacturer_data |= bool(
                advertisement_data.manufacturer_data
            )
            previous_match.service_data |= set(advertisement_data.service_data)
            previous_match.service_uuids |= set(advertisement_data.service_uuids)
        else:
            matched[device.address] = IntegrationMatchHistory(
                manufacturer_data=bool(advertisement_data.manufacturer_data),
                service_data=set(advertisement_data.service_data),
                service_uuids=set(advertisement_data.service_uuids),
            )
        return matched_domains


def ble_device_matches(
    matcher: BluetoothCallbackMatcher | BluetoothMatcher,
    service_info: BluetoothServiceInfoBleak,
) -> bool:
    """Check if a ble device and advertisement_data matches the matcher."""
    device = service_info.device
    if (address := matcher.get(ADDRESS)) is not None and device.address != address:
        return False

    if matcher.get(CONNECTABLE, True) and not service_info.connectable:
        return False

    advertisement_data = service_info.advertisement
    if (
        service_uuid := matcher.get(SERVICE_UUID)
    ) is not None and service_uuid not in advertisement_data.service_uuids:
        return False

    if (
        service_data_uuid := matcher.get(SERVICE_DATA_UUID)
    ) is not None and service_data_uuid not in advertisement_data.service_data:
        return False

    if (
        manfacturer_id := matcher.get(MANUFACTURER_ID)
    ) is not None and manfacturer_id not in advertisement_data.manufacturer_data:
        return False

    if (manufacturer_data_start := matcher.get(MANUFACTURER_DATA_START)) is not None:
        manufacturer_data_start_bytes = bytearray(manufacturer_data_start)
        if not any(
            manufacturer_data.startswith(manufacturer_data_start_bytes)
            for manufacturer_data in advertisement_data.manufacturer_data.values()
        ):
            return False

    if (local_name := matcher.get(LOCAL_NAME)) is not None and (
        (device_name := advertisement_data.local_name or device.name) is None
        or not _memorized_fnmatch(
            device_name,
            local_name,
        )
    ):
        return False

    return True


@lru_cache(maxsize=4096, typed=True)
def _compile_fnmatch(pattern: str) -> re.Pattern:
    """Compile a fnmatch pattern."""
    return re.compile(translate(pattern))


@lru_cache(maxsize=1024, typed=True)
def _memorized_fnmatch(name: str, pattern: str) -> bool:
    """Memorized version of fnmatch that has a larger lru_cache.

    The default version of fnmatch only has a lru_cache of 256 entries.
    With many devices we quickly reach that limit and end up compiling
    the same pattern over and over again.

    Bluetooth has its own memorized fnmatch with its own lru_cache
    since the data is going to be relatively the same
    since the devices will not change frequently.
    """
    return bool(_compile_fnmatch(pattern).match(name))
