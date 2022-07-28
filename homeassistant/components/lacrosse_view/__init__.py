"""The LaCrosse View integration."""
from __future__ import annotations

from datetime import datetime, timedelta

from lacrosse_view import LaCrosse, Location, LoginError, Sensor

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER, SCAN_INTERVAL

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LaCrosse View from a config entry."""

    async def get_data() -> list[Sensor]:
        """Get the data from the LaCrosse View."""
        now = datetime.utcnow()

        if hass.data[DOMAIN][entry.entry_id]["last_update"] < now - timedelta(
            minutes=59
        ):  # Get new token
            hass.data[DOMAIN][entry.entry_id]["last_update"] = now
            await api.login(entry.data["username"], entry.data["password"])

        # Get the timestamp for yesterday at 6 PM (this is what is used in the app, i noticed it when proxying the request)
        yesterday = now - timedelta(days=1)
        yesterday = yesterday.replace(hour=18, minute=0, second=0, microsecond=0)
        yesterday_timestamp = datetime.timestamp(yesterday)

        return await api.get_sensors(
            location=Location(id=entry.data["id"], name=entry.data["name"]),
            tz=hass.config.time_zone,
            start=str(int(yesterday_timestamp)),
            end=str(int(datetime.timestamp(now))),
        )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": LaCrosse(async_get_clientsession(hass)),
        "last_update": datetime.utcnow(),
    }
    api: LaCrosse = hass.data[DOMAIN][entry.entry_id]["api"]

    try:
        await api.login(entry.data["username"], entry.data["password"])
    except LoginError as error:
        raise ConfigEntryNotReady from error

    coordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name="LaCrosse View",
        update_method=get_data,
        update_interval=timedelta(seconds=SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
