"""Interfaces with iAlarm control panels."""
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up a iAlarm alarm control panel based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([IAlarmPanel(coordinator)], False)


class IAlarmPanel(CoordinatorEntity, AlarmControlPanelEntity):
    """Representation of an iAlarm device."""

    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_AWAY
    )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer="Antifurto365 - Meian",
            name=self.name,
        )

    @property
    def unique_id(self):
        """Return a unique id."""
        return self.coordinator.mac

    @property
    def name(self):
        """Return the name."""
        return "iAlarm"

    @property
    def state(self):
        """Return the state of the device."""
        return self.coordinator.state

    def alarm_disarm(self, code=None):
        """Send disarm command."""
        self.coordinator.ialarm.disarm()

    def alarm_arm_home(self, code=None):
        """Send arm home command."""
        self.coordinator.ialarm.arm_stay()

    def alarm_arm_away(self, code=None):
        """Send arm away command."""
        self.coordinator.ialarm.arm_away()
