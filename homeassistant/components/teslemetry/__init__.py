"""Teslemetry integration."""

import asyncio
from typing import Final

from tesla_fleet_api import EnergySpecific, Teslemetry, VehicleSpecific
from tesla_fleet_api.exceptions import (
    InvalidToken,
    SubscriptionRequired,
    TeslaFleetError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, LOGGER
from .coordinator import (
    TeslemetryEnergyDataCoordinator,
    TeslemetryVehicleDataCoordinator,
)
from .models import TeslemetryData, TeslemetryEnergyData, TeslemetryVehicleData

PLATFORMS: Final = [Platform.CLIMATE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Teslemetry config."""

    access_token = entry.data[CONF_ACCESS_TOKEN]

    # Create API connection
    teslemetry = Teslemetry(
        session=async_get_clientsession(hass),
        access_token=access_token,
    )
    try:
        products = (await teslemetry.products())["response"]
    except InvalidToken:
        LOGGER.error("Access token is invalid, unable to connect to Teslemetry")
        return False
    except SubscriptionRequired:
        LOGGER.error("Subscription required, unable to connect to Telemetry")
        return False
    except TeslaFleetError as e:
        raise ConfigEntryNotReady from e

    # Create array of classes
    vehicles: list[TeslemetryVehicleData] = []
    energysites: list[TeslemetryEnergyData] = []
    for product in products:
        if "vin" in product:
            vin = product["vin"]
            api = VehicleSpecific(teslemetry.vehicle, vin)
            coordinator = TeslemetryVehicleDataCoordinator(hass, api)
            vehicles.append(
                TeslemetryVehicleData(
                    api=api,
                    coordinator=coordinator,
                    vin=vin,
                )
            )
        elif "energy_site_id" in product:
            site_id = product["energy_site_id"]
            api = EnergySpecific(teslemetry.energy, site_id)
            energysites.append(
                TeslemetryEnergyData(
                    api=api,
                    coordinator=TeslemetryEnergyDataCoordinator(hass, api),
                    id=site_id,
                    info=product,
                )
            )

    # Do all coordinator first refreshes simultaneously
    await asyncio.gather(
        *(
            vehicle.coordinator.async_config_entry_first_refresh()
            for vehicle in vehicles
        ),
        *(
            energysite.coordinator.async_config_entry_first_refresh()
            for energysite in energysites
        ),
    )

    # Setup Platforms
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = TeslemetryData(
        vehicles, energysites
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Teslemetry Config."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
