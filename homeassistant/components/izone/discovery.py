"""Internal discovery service for  iZone AC."""
import pizone

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DATA_DISCOVERY_SERVICE,
    DISPATCH_CONTROLLER_DISCONNECTED,
    DISPATCH_CONTROLLER_DISCOVERED,
    DISPATCH_CONTROLLER_RECONNECTED,
    DISPATCH_CONTROLLER_UPDATE,
    DISPATCH_ZONE_UPDATE,
)


class DiscoveryService(pizone.Listener):
    """Discovery data and interfacing with pizone library."""

    def __init__(self, hass):
        """Initialise discovery service."""
        super().__init__()
        self.hass = hass
        self.pi_disco = None

    # Listener interface
    def controller_discovered(self, ctrl: pizone.Controller) -> None:
        """Handle new controller discoverery."""
        async_dispatcher_send(self.hass, DISPATCH_CONTROLLER_DISCOVERED, ctrl)

    def controller_disconnected(self, ctrl: pizone.Controller, ex: Exception) -> None:
        """On disconnect from controller."""
        async_dispatcher_send(self.hass, DISPATCH_CONTROLLER_DISCONNECTED, ctrl, ex)

    def controller_reconnected(self, ctrl: pizone.Controller) -> None:
        """On reconnect to controller."""
        async_dispatcher_send(self.hass, DISPATCH_CONTROLLER_RECONNECTED, ctrl)

    def controller_update(self, ctrl: pizone.Controller) -> None:
        """System update message is received from the controller."""
        async_dispatcher_send(self.hass, DISPATCH_CONTROLLER_UPDATE, ctrl)

    def zone_update(self, ctrl: pizone.Controller, zone: pizone.Zone) -> None:
        """Zone update message is received from the controller."""
        async_dispatcher_send(self.hass, DISPATCH_ZONE_UPDATE, ctrl, zone)


async def async_start_discovery_service(hass: HomeAssistant):
    """Set up the pizone internal discovery."""
    if disco := hass.data.get(DATA_DISCOVERY_SERVICE):
        # Already started
        return disco

    # discovery local services
    disco = DiscoveryService(hass)
    hass.data[DATA_DISCOVERY_SERVICE] = disco

    # Start the pizone discovery service, disco is the listener
    session = aiohttp_client.async_get_clientsession(hass)
    disco.pi_disco = pizone.discovery(disco, session=session)
    await disco.pi_disco.start_discovery()

    async def shutdown_event(event):
        await async_stop_discovery_service(hass)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown_event)

    return disco


async def async_stop_discovery_service(hass: HomeAssistant):
    """Stop the discovery service."""
    if not (disco := hass.data.get(DATA_DISCOVERY_SERVICE)):
        return

    await disco.pi_disco.close()
    del hass.data[DATA_DISCOVERY_SERVICE]
