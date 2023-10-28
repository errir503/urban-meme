"""Support for Freebox alarms."""
import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_NIGHT,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMED,
    STATE_ALARM_TRIGGERED,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FreeboxHomeCategory
from .home_base import FreeboxHomeEntity
from .router import FreeboxRouter

FREEBOX_TO_STATUS = {
    "alarm1_arming": STATE_ALARM_ARMING,
    "alarm2_arming": STATE_ALARM_ARMING,
    "alarm1_armed": STATE_ALARM_ARMED_AWAY,
    "alarm2_armed": STATE_ALARM_ARMED_NIGHT,
    "alarm1_alert_timer": STATE_ALARM_TRIGGERED,
    "alarm2_alert_timer": STATE_ALARM_TRIGGERED,
    "alert": STATE_ALARM_TRIGGERED,
}


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up alarm panel."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]

    alarm_entities: list[AlarmControlPanelEntity] = []

    for node in router.home_devices.values():
        if node["category"] == FreeboxHomeCategory.ALARM:
            alarm_entities.append(FreeboxAlarm(hass, router, node))

    if alarm_entities:
        async_add_entities(alarm_entities, True)


class FreeboxAlarm(FreeboxHomeEntity, AlarmControlPanelEntity):
    """Representation of a Freebox alarm."""

    def __init__(
        self, hass: HomeAssistant, router: FreeboxRouter, node: dict[str, Any]
    ) -> None:
        """Initialize an alarm."""
        super().__init__(hass, router, node)

        # Commands
        self._command_trigger = self.get_command_id(
            node["type"]["endpoints"], "slot", "trigger"
        )
        self._command_arm_away = self.get_command_id(
            node["type"]["endpoints"], "slot", "alarm1"
        )
        self._command_arm_home = self.get_command_id(
            node["type"]["endpoints"], "slot", "alarm2"
        )
        self._command_disarm = self.get_command_id(
            node["type"]["endpoints"], "slot", "off"
        )
        self._command_state = self.get_command_id(
            node["type"]["endpoints"], "signal", "state"
        )
        self._set_features(self._router.home_devices[self._id])

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        if await self.set_home_endpoint_value(self._command_disarm):
            self._set_state(STATE_ALARM_DISARMED)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        if await self.set_home_endpoint_value(self._command_arm_away):
            self._set_state(STATE_ALARM_ARMING)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""
        if await self.set_home_endpoint_value(self._command_arm_home):
            self._set_state(STATE_ALARM_ARMING)

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Send alarm trigger command."""
        if await self.set_home_endpoint_value(self._command_trigger):
            self._set_state(STATE_ALARM_TRIGGERED)

    async def async_update_signal(self):
        """Update signal."""
        state = await self.get_home_endpoint_value(self._command_state)
        if state:
            self._set_state(state)

    def _set_features(self, node: dict[str, Any]) -> None:
        """Add alarm features."""
        # Search if the arm home feature is present => has an "alarm2" endpoint
        can_arm_home = False
        for nodeid, local_node in self._router.home_devices.items():
            if nodeid == local_node["id"]:
                alarm2 = next(
                    filter(
                        lambda x: (x["name"] == "alarm2" and x["ep_type"] == "signal"),
                        local_node["show_endpoints"],
                    ),
                    None,
                )
                if alarm2:
                    can_arm_home = alarm2["value"]
                    break

        if can_arm_home:
            self._attr_supported_features = (
                AlarmControlPanelEntityFeature.ARM_AWAY
                | AlarmControlPanelEntityFeature.ARM_HOME
            )

        else:
            self._attr_supported_features = AlarmControlPanelEntityFeature.ARM_AWAY

    def _set_state(self, state: str) -> None:
        """Update state."""
        self._attr_state = FREEBOX_TO_STATUS.get(state)
        if not self._attr_state:
            self._attr_state = STATE_ALARM_DISARMED
        self.async_write_ha_state()
