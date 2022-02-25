"""The Flux LED/MagicLight integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Final, cast

from flux_led import DeviceType
from flux_led.aio import AIOWifiLedBulb
from flux_led.const import ATTR_ID, WhiteChannelType
from flux_led.scanner import FluxLEDDiscovery

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_WHITE_CHANNEL_TYPE,
    DISCOVER_SCAN_TIMEOUT,
    DOMAIN,
    FLUX_LED_DISCOVERY,
    FLUX_LED_EXCEPTIONS,
    SIGNAL_STATE_UPDATED,
    STARTUP_SCAN_TIMEOUT,
)
from .coordinator import FluxLedUpdateCoordinator
from .discovery import (
    async_build_cached_discovery,
    async_clear_discovery_cache,
    async_discover_device,
    async_discover_devices,
    async_get_discovery,
    async_trigger_discovery,
    async_update_entry_from_discovery,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS_BY_TYPE: Final = {
    DeviceType.Bulb: [
        Platform.BUTTON,
        Platform.LIGHT,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.SENSOR,
        Platform.SWITCH,
    ],
    DeviceType.Switch: [Platform.BUTTON, Platform.SELECT, Platform.SWITCH],
}
DISCOVERY_INTERVAL: Final = timedelta(minutes=15)
REQUEST_REFRESH_DELAY: Final = 1.5
NAME_TO_WHITE_CHANNEL_TYPE: Final = {
    option.name.lower(): option for option in WhiteChannelType
}


@callback
def async_wifi_bulb_for_host(
    host: str, discovery: FluxLEDDiscovery | None
) -> AIOWifiLedBulb:
    """Create a AIOWifiLedBulb from a host."""
    return AIOWifiLedBulb(host, discovery=discovery)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the flux_led component."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[FLUX_LED_DISCOVERY] = await async_discover_devices(
        hass, STARTUP_SCAN_TIMEOUT
    )

    async def _async_discovery(*_: Any) -> None:
        async_trigger_discovery(
            hass, await async_discover_devices(hass, DISCOVER_SCAN_TIMEOUT)
        )

    async_trigger_discovery(hass, domain_data[FLUX_LED_DISCOVERY])
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_discovery)
    async_track_time_interval(hass, _async_discovery, DISCOVERY_INTERVAL)
    return True


async def _async_migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate entities when the mac address gets discovered."""
    if not (unique_id := entry.unique_id):
        return
    entry_id = entry.entry_id

    @callback
    def _async_migrator(entity_entry: er.RegistryEntry) -> dict[str, Any] | None:
        # Old format {entry_id}.....
        # New format {unique_id}....
        entity_unique_id = entity_entry.unique_id
        if not entity_unique_id.startswith(entry_id):
            return None
        new_unique_id = f"{unique_id}{entity_unique_id[len(entry_id):]}"
        _LOGGER.info(
            "Migrating unique_id from [%s] to [%s]",
            entity_unique_id,
            new_unique_id,
        )
        return {"new_unique_id": new_unique_id}

    await er.async_migrate_entries(hass, entry.entry_id, _async_migrator)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Flux LED/MagicLight from a config entry."""
    host = entry.data[CONF_HOST]
    discovery_cached = True
    if discovery := async_get_discovery(hass, host):
        discovery_cached = False
    else:
        discovery = async_build_cached_discovery(entry)
    device: AIOWifiLedBulb = async_wifi_bulb_for_host(host, discovery=discovery)
    signal = SIGNAL_STATE_UPDATED.format(device.ipaddr)
    device.discovery = discovery
    if white_channel_type := entry.data.get(CONF_WHITE_CHANNEL_TYPE):
        device.white_channel_channel_type = NAME_TO_WHITE_CHANNEL_TYPE[
            white_channel_type
        ]

    @callback
    def _async_state_changed(*_: Any) -> None:
        _LOGGER.debug("%s: Device state updated: %s", device.ipaddr, device.raw_state)
        async_dispatcher_send(hass, signal)

    try:
        await device.async_setup(_async_state_changed)
    except FLUX_LED_EXCEPTIONS as ex:
        raise ConfigEntryNotReady(
            str(ex) or f"Timed out trying to connect to {device.ipaddr}"
        ) from ex

    # UDP probe after successful connect only
    if discovery_cached:
        if directed_discovery := await async_discover_device(hass, host):
            device.discovery = discovery = directed_discovery
            discovery_cached = False

    if entry.unique_id and discovery.get(ATTR_ID):
        mac = dr.format_mac(cast(str, discovery[ATTR_ID]))
        if mac != entry.unique_id:
            # The device is offline and another flux_led device is now using the ip address
            raise ConfigEntryNotReady(
                f"Unexpected device found at {host}; Expected {entry.unique_id}, found {mac}"
            )

    if not discovery_cached:
        # Only update the entry once we have verified the unique id
        # is either missing or we have verified it matches
        async_update_entry_from_discovery(hass, entry, discovery, device.model_num)

    await _async_migrate_unique_ids(hass, entry)

    coordinator = FluxLedUpdateCoordinator(hass, device, entry)
    hass.data[DOMAIN][entry.entry_id] = coordinator
    platforms = PLATFORMS_BY_TYPE[device.device_type]
    hass.config_entries.async_setup_platforms(entry, platforms)

    async def _async_sync_time(*args: Any) -> None:
        """Set the time every morning at 02:40:30."""
        await device.async_set_time()

    await _async_sync_time()  # set at startup
    entry.async_on_unload(async_track_time_change(hass, _async_sync_time, 2, 40, 30))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    device: AIOWifiLedBulb = hass.data[DOMAIN][entry.entry_id].device
    platforms = PLATFORMS_BY_TYPE[device.device_type]
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, platforms):
        # Make sure we probe the device again in case something has changed externally
        async_clear_discovery_cache(hass, entry.data[CONF_HOST])
        del hass.data[DOMAIN][entry.entry_id]
        await device.async_stop()
    return unload_ok
