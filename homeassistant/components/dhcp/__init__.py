"""The dhcp integration."""

from dataclasses import dataclass
from datetime import timedelta
import fnmatch
from ipaddress import ip_address as make_ip_address
import logging
import os
import threading
from typing import Any, Final

from aiodiscover import DiscoverHosts
from aiodiscover.discovery import (
    HOSTNAME as DISCOVERY_HOSTNAME,
    IP_ADDRESS as DISCOVERY_IP_ADDRESS,
    MAC_ADDRESS as DISCOVERY_MAC_ADDRESS,
)
from scapy.config import conf
from scapy.error import Scapy_Exception

from homeassistant import config_entries
from homeassistant.components.device_tracker.const import (
    ATTR_HOST_NAME,
    ATTR_IP,
    ATTR_MAC,
    ATTR_SOURCE_TYPE,
    DOMAIN as DEVICE_TRACKER_DOMAIN,
    SOURCE_TYPE_ROUTER,
)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
    STATE_HOME,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.data_entry_flow import BaseServiceInfo
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.event import (
    async_track_state_added_domain,
    async_track_time_interval,
)
from homeassistant.helpers.frame import report
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_dhcp
from homeassistant.util.async_ import run_callback_threadsafe
from homeassistant.util.network import is_invalid, is_link_local, is_loopback

from .const import DOMAIN

FILTER = "udp and (port 67 or 68)"
REQUESTED_ADDR = "requested_addr"
MESSAGE_TYPE = "message-type"
HOSTNAME: Final = "hostname"
MAC_ADDRESS: Final = "macaddress"
IP_ADDRESS: Final = "ip"
DHCP_REQUEST = 3
SCAN_INTERVAL = timedelta(minutes=60)

_LOGGER = logging.getLogger(__name__)


@dataclass
class DhcpServiceInfo(BaseServiceInfo):
    """Prepared info from dhcp entries."""

    ip: str
    hostname: str
    macaddress: str

    def __getitem__(self, name: str) -> Any:
        """
        Enable method for compatibility reason.

        Deprecated, and will be removed in version 2022.6.
        """
        report(
            f"accessed discovery_info['{name}'] instead of discovery_info.{name}; "
            "this will fail in version 2022.6",
            exclude_integrations={DOMAIN},
            error_if_core=False,
        )
        return getattr(self, name)

    def get(self, name: str, default: Any = None) -> Any:
        """
        Enable method for compatibility reason.

        Deprecated, and will be removed in version 2022.6.
        """
        report(
            f"accessed discovery_info.get('{name}') instead of discovery_info.{name}; "
            "this will fail in version 2022.6",
            exclude_integrations={DOMAIN},
            error_if_core=False,
        )
        if hasattr(self, name):
            return getattr(self, name)
        return default


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the dhcp component."""

    async def _initialize(_):
        address_data = {}
        integration_matchers = await async_get_dhcp(hass)
        watchers = []

        for cls in (DHCPWatcher, DeviceTrackerWatcher, NetworkWatcher):
            watcher = cls(hass, address_data, integration_matchers)
            await watcher.async_start()
            watchers.append(watcher)

        async def _async_stop(*_):
            for watcher in watchers:
                await watcher.async_stop()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _initialize)
    return True


class WatcherBase:
    """Base class for dhcp and device tracker watching."""

    def __init__(self, hass, address_data, integration_matchers):
        """Initialize class."""
        super().__init__()

        self.hass = hass
        self._integration_matchers = integration_matchers
        self._address_data = address_data

    def process_client(self, ip_address, hostname, mac_address):
        """Process a client."""
        return run_callback_threadsafe(
            self.hass.loop,
            self.async_process_client,
            ip_address,
            hostname,
            mac_address,
        ).result()

    @callback
    def async_process_client(self, ip_address, hostname, mac_address):
        """Process a client."""
        made_ip_address = make_ip_address(ip_address)

        if (
            is_link_local(made_ip_address)
            or is_loopback(made_ip_address)
            or is_invalid(made_ip_address)
        ):
            # Ignore self assigned addresses, loopback, invalid
            return

        data = self._address_data.get(ip_address)
        if (
            data
            and data[MAC_ADDRESS] == mac_address
            and data[HOSTNAME].startswith(hostname)
        ):
            # If the address data is the same no need
            # to process it
            return

        data = {MAC_ADDRESS: mac_address, HOSTNAME: hostname}
        self._address_data[ip_address] = data

        lowercase_hostname = data[HOSTNAME].lower()
        uppercase_mac = data[MAC_ADDRESS].upper()

        _LOGGER.debug(
            "Processing updated address data for %s: mac=%s hostname=%s",
            ip_address,
            uppercase_mac,
            lowercase_hostname,
        )

        matched_domains = set()
        for entry in self._integration_matchers:
            if MAC_ADDRESS in entry and not fnmatch.fnmatch(
                uppercase_mac, entry[MAC_ADDRESS]
            ):
                continue

            if HOSTNAME in entry and not fnmatch.fnmatch(
                lowercase_hostname, entry[HOSTNAME]
            ):
                continue

            _LOGGER.debug("Matched %s against %s", data, entry)
            if entry["domain"] in matched_domains:
                # Only match once per domain
                continue

            matched_domains.add(entry["domain"])
            discovery_flow.async_create_flow(
                self.hass,
                entry["domain"],
                {"source": config_entries.SOURCE_DHCP},
                DhcpServiceInfo(
                    ip=ip_address,
                    hostname=lowercase_hostname,
                    macaddress=data[MAC_ADDRESS],
                ),
            )


class NetworkWatcher(WatcherBase):
    """Class to query ptr records routers."""

    def __init__(self, hass, address_data, integration_matchers):
        """Initialize class."""
        super().__init__(hass, address_data, integration_matchers)
        self._unsub = None
        self._discover_hosts = None
        self._discover_task = None

    async def async_stop(self):
        """Stop scanning for new devices on the network."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._discover_task:
            self._discover_task.cancel()
            self._discover_task = None

    async def async_start(self):
        """Start scanning for new devices on the network."""
        self._discover_hosts = DiscoverHosts()
        self._unsub = async_track_time_interval(
            self.hass, self.async_start_discover, SCAN_INTERVAL
        )
        self.async_start_discover()

    @callback
    def async_start_discover(self, *_):
        """Start a new discovery task if one is not running."""
        if self._discover_task and not self._discover_task.done():
            return
        self._discover_task = self.hass.async_create_task(self.async_discover())

    async def async_discover(self):
        """Process discovery."""
        for host in await self._discover_hosts.async_discover():
            self.async_process_client(
                host[DISCOVERY_IP_ADDRESS],
                host[DISCOVERY_HOSTNAME],
                _format_mac(host[DISCOVERY_MAC_ADDRESS]),
            )


class DeviceTrackerWatcher(WatcherBase):
    """Class to watch dhcp data from routers."""

    def __init__(self, hass, address_data, integration_matchers):
        """Initialize class."""
        super().__init__(hass, address_data, integration_matchers)
        self._unsub = None

    async def async_stop(self):
        """Stop watching for new device trackers."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def async_start(self):
        """Stop watching for new device trackers."""
        self._unsub = async_track_state_added_domain(
            self.hass, [DEVICE_TRACKER_DOMAIN], self._async_process_device_event
        )
        for state in self.hass.states.async_all(DEVICE_TRACKER_DOMAIN):
            self._async_process_device_state(state)

    @callback
    def _async_process_device_event(self, event: Event):
        """Process a device tracker state change event."""
        self._async_process_device_state(event.data["new_state"])

    @callback
    def _async_process_device_state(self, state: State):
        """Process a device tracker state."""
        if state.state != STATE_HOME:
            return

        attributes = state.attributes

        if attributes.get(ATTR_SOURCE_TYPE) != SOURCE_TYPE_ROUTER:
            return

        ip_address = attributes.get(ATTR_IP)
        hostname = attributes.get(ATTR_HOST_NAME, "")
        mac_address = attributes.get(ATTR_MAC)

        if ip_address is None or mac_address is None:
            return

        self.async_process_client(ip_address, hostname, _format_mac(mac_address))


class DHCPWatcher(WatcherBase):
    """Class to watch dhcp requests."""

    def __init__(self, hass, address_data, integration_matchers):
        """Initialize class."""
        super().__init__(hass, address_data, integration_matchers)
        self._sniffer = None
        self._started = threading.Event()

    async def async_stop(self):
        """Stop watching for new device trackers."""
        await self.hass.async_add_executor_job(self._stop)

    def _stop(self):
        """Stop the thread."""
        if self._started.is_set():
            self._sniffer.stop()

    async def async_start(self):
        """Start watching for dhcp packets."""
        await self.hass.async_add_executor_job(self._start)

    def _start(self):
        """Start watching for dhcp packets."""
        # Local import because importing from scapy has side effects such as opening
        # sockets
        from scapy import (  # pylint: disable=import-outside-toplevel,unused-import  # noqa: F401
            arch,
        )
        from scapy.layers.dhcp import DHCP  # pylint: disable=import-outside-toplevel
        from scapy.layers.inet import IP  # pylint: disable=import-outside-toplevel
        from scapy.layers.l2 import Ether  # pylint: disable=import-outside-toplevel

        #
        # Importing scapy.sendrecv will cause a scapy resync which will
        # import scapy.arch.read_routes which will import scapy.sendrecv
        #
        # We avoid this circular import by importing arch above to ensure
        # the module is loaded and avoid the problem
        #
        from scapy.sendrecv import (  # pylint: disable=import-outside-toplevel
            AsyncSniffer,
        )

        def _handle_dhcp_packet(packet):
            """Process a dhcp packet."""
            if DHCP not in packet:
                return

            options = packet[DHCP].options
            request_type = _decode_dhcp_option(options, MESSAGE_TYPE)
            if request_type != DHCP_REQUEST:
                # Not a DHCP request
                return

            ip_address = _decode_dhcp_option(options, REQUESTED_ADDR) or packet[IP].src
            hostname = _decode_dhcp_option(options, HOSTNAME) or ""
            mac_address = _format_mac(packet[Ether].src)

            if ip_address is not None and mac_address is not None:
                self.process_client(ip_address, hostname, mac_address)

        # disable scapy promiscuous mode as we do not need it
        conf.sniff_promisc = 0

        try:
            _verify_l2socket_setup(FILTER)
        except (Scapy_Exception, OSError) as ex:
            if os.geteuid() == 0:
                _LOGGER.error("Cannot watch for dhcp packets: %s", ex)
            else:
                _LOGGER.debug(
                    "Cannot watch for dhcp packets without root or CAP_NET_RAW: %s", ex
                )
            return

        try:
            _verify_working_pcap(FILTER)
        except (Scapy_Exception, ImportError) as ex:
            _LOGGER.error(
                "Cannot watch for dhcp packets without a functional packet filter: %s",
                ex,
            )
            return

        self._sniffer = AsyncSniffer(
            filter=FILTER,
            started_callback=self._started.set,
            prn=_handle_dhcp_packet,
            store=0,
        )

        self._sniffer.start()
        if self._sniffer.thread:
            self._sniffer.thread.name = self.__class__.__name__


def _decode_dhcp_option(dhcp_options, key):
    """Extract and decode data from a packet option."""
    for option in dhcp_options:
        if len(option) < 2 or option[0] != key:
            continue

        value = option[1]
        if value is None or key != HOSTNAME:
            return value

        # hostname is unicode
        try:
            return value.decode()
        except (AttributeError, UnicodeDecodeError):
            return None


def _format_mac(mac_address):
    """Format a mac address for matching."""
    return format_mac(mac_address).replace(":", "")


def _verify_l2socket_setup(cap_filter):
    """Create a socket using the scapy configured l2socket.

    Try to create the socket
    to see if we have permissions
    since AsyncSniffer will do it another
    thread so we will not be able to capture
    any permission or bind errors.
    """
    conf.L2socket(filter=cap_filter)


def _verify_working_pcap(cap_filter):
    """Verify we can create a packet filter.

    If we cannot create a filter we will be listening for
    all traffic which is too intensive.
    """
    # Local import because importing from scapy has side effects such as opening
    # sockets
    from scapy.arch.common import (  # pylint: disable=import-outside-toplevel
        compile_filter,
    )

    compile_filter(cap_filter)
