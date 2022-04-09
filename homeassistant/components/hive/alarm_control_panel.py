"""Support for the Hive alarm."""
from datetime import timedelta

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_NIGHT,
    STATE_ALARM_DISARMED,
    STATE_ALARM_TRIGGERED,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HiveEntity
from .const import DOMAIN

ICON = "mdi:security"
PARALLEL_UPDATES = 0
SCAN_INTERVAL = timedelta(seconds=15)
HIVETOHA = {
    "home": STATE_ALARM_DISARMED,
    "asleep": STATE_ALARM_ARMED_NIGHT,
    "away": STATE_ALARM_ARMED_AWAY,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Hive thermostat based on a config entry."""

    hive = hass.data[DOMAIN][entry.entry_id]
    if devices := hive.session.deviceList.get("alarm_control_panel"):
        async_add_entities(
            [HiveAlarmControlPanelEntity(hive, dev) for dev in devices], True
        )


class HiveAlarmControlPanelEntity(HiveEntity, AlarmControlPanelEntity):
    """Representation of a Hive alarm."""

    _attr_icon = ICON
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_NIGHT
        | AlarmControlPanelEntityFeature.ARM_AWAY
    )

    @property
    def unique_id(self):
        """Return unique ID of entity."""
        return self._unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this AdGuard Home instance."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device["device_id"])},
            model=self.device["deviceData"]["model"],
            manufacturer=self.device["deviceData"]["manufacturer"],
            name=self.device["device_name"],
            sw_version=self.device["deviceData"]["version"],
            via_device=(DOMAIN, self.device["parentDevice"]),
        )

    @property
    def name(self):
        """Return the name of the alarm."""
        return self.device["haName"]

    @property
    def available(self):
        """Return if the device is available."""
        return self.device["deviceData"]["online"]

    @property
    def state(self):
        """Return state of alarm."""
        if self.device["status"]["state"]:
            return STATE_ALARM_TRIGGERED
        return HIVETOHA[self.device["status"]["mode"]]

    async def async_alarm_disarm(self, code=None):
        """Send disarm command."""
        await self.hive.alarm.setMode(self.device, "home")

    async def async_alarm_arm_night(self, code=None):
        """Send arm night command."""
        await self.hive.alarm.setMode(self.device, "asleep")

    async def async_alarm_arm_away(self, code=None):
        """Send arm away command."""
        await self.hive.alarm.setMode(self.device, "away")

    async def async_update(self):
        """Update all Node data from Hive."""
        await self.hive.session.updateData(self.device)
        self.device = await self.hive.alarm.getAlarm(self.device)
