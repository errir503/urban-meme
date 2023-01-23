"""Support for Google Mail Sensors."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from googleapiclient.http import HttpRequest

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import GoogleMailEntity

SCAN_INTERVAL = timedelta(minutes=15)

SENSOR_TYPE = SensorEntityDescription(
    key="vacation_end_date",
    name="Vacation end date",
    icon="mdi:clock",
    device_class=SensorDeviceClass.TIMESTAMP,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Google Mail sensor."""
    async_add_entities(
        [GoogleMailSensor(hass.data[DOMAIN][entry.entry_id], SENSOR_TYPE)], True
    )


class GoogleMailSensor(GoogleMailEntity, SensorEntity):
    """Representation of a Google Mail sensor."""

    async def async_update(self) -> None:
        """Get the vacation data."""
        service = await self.auth.get_resource()
        settings: HttpRequest = service.users().settings().getVacation(userId="me")
        data = await self.hass.async_add_executor_job(settings.execute)

        if data["enableAutoReply"]:
            value = datetime.fromtimestamp(int(data["endTime"]) / 1000, tz=timezone.utc)
        else:
            value = None
        self._attr_native_value = value
