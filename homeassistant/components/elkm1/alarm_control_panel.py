"""Each ElkM1 area will be created as a separate alarm_control_panel."""
from __future__ import annotations

from elkm1_lib.const import AlarmState, ArmedStatus, ArmLevel, ArmUpState
import voluptuous as vol

from homeassistant.components.alarm_control_panel import (
    ATTR_CHANGED_BY,
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_ARMED_NIGHT,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMED,
    STATE_ALARM_PENDING,
    STATE_ALARM_TRIGGERED,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ElkAttachedEntity, ElkEntity, create_elk_entities
from .const import (
    ATTR_CHANGED_BY_ID,
    ATTR_CHANGED_BY_KEYPAD,
    ATTR_CHANGED_BY_TIME,
    DOMAIN,
    ELK_USER_CODE_SERVICE_SCHEMA,
)

DISPLAY_MESSAGE_SERVICE_SCHEMA = {
    vol.Optional("clear", default=2): vol.All(vol.Coerce(int), vol.In([0, 1, 2])),
    vol.Optional("beep", default=False): cv.boolean,
    vol.Optional("timeout", default=0): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=65535)
    ),
    vol.Optional("line1", default=""): cv.string,
    vol.Optional("line2", default=""): cv.string,
}

SERVICE_ALARM_DISPLAY_MESSAGE = "alarm_display_message"
SERVICE_ALARM_ARM_VACATION = "alarm_arm_vacation"
SERVICE_ALARM_ARM_HOME_INSTANT = "alarm_arm_home_instant"
SERVICE_ALARM_ARM_NIGHT_INSTANT = "alarm_arm_night_instant"
SERVICE_ALARM_BYPASS = "alarm_bypass"
SERVICE_ALARM_CLEAR_BYPASS = "alarm_clear_bypass"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ElkM1 alarm platform."""
    elk_data = hass.data[DOMAIN][config_entry.entry_id]
    elk = elk_data["elk"]
    entities: list[ElkEntity] = []
    create_elk_entities(elk_data, elk.areas, "area", ElkArea, entities)
    async_add_entities(entities, True)

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_ALARM_ARM_VACATION,
        ELK_USER_CODE_SERVICE_SCHEMA,
        "async_alarm_arm_vacation",
    )
    platform.async_register_entity_service(
        SERVICE_ALARM_ARM_HOME_INSTANT,
        ELK_USER_CODE_SERVICE_SCHEMA,
        "async_alarm_arm_home_instant",
    )
    platform.async_register_entity_service(
        SERVICE_ALARM_ARM_NIGHT_INSTANT,
        ELK_USER_CODE_SERVICE_SCHEMA,
        "async_alarm_arm_night_instant",
    )
    platform.async_register_entity_service(
        SERVICE_ALARM_DISPLAY_MESSAGE,
        DISPLAY_MESSAGE_SERVICE_SCHEMA,
        "async_display_message",
    )
    platform.async_register_entity_service(
        SERVICE_ALARM_BYPASS,
        ELK_USER_CODE_SERVICE_SCHEMA,
        "async_bypass",
    )
    platform.async_register_entity_service(
        SERVICE_ALARM_CLEAR_BYPASS,
        ELK_USER_CODE_SERVICE_SCHEMA,
        "async_clear_bypass",
    )


class ElkArea(ElkAttachedEntity, AlarmControlPanelEntity, RestoreEntity):
    """Representation of an Area / Partition within the ElkM1 alarm panel."""

    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )

    def __init__(self, element, elk, elk_data):
        """Initialize Area as Alarm Control Panel."""
        super().__init__(element, elk, elk_data)
        self._elk = elk
        self._changed_by_keypad = None
        self._changed_by_time = None
        self._changed_by_id = None
        self._changed_by = None
        self._state = None

    async def async_added_to_hass(self):
        """Register callback for ElkM1 changes."""
        await super().async_added_to_hass()
        if len(self._elk.areas.elements) == 1:
            for keypad in self._elk.keypads:
                keypad.add_callback(self._watch_keypad)
        self._element.add_callback(self._watch_area)

        # We do not get changed_by back from resync.
        if not (last_state := await self.async_get_last_state()):
            return

        if ATTR_CHANGED_BY_KEYPAD in last_state.attributes:
            self._changed_by_keypad = last_state.attributes[ATTR_CHANGED_BY_KEYPAD]
        if ATTR_CHANGED_BY_TIME in last_state.attributes:
            self._changed_by_time = last_state.attributes[ATTR_CHANGED_BY_TIME]
        if ATTR_CHANGED_BY_ID in last_state.attributes:
            self._changed_by_id = last_state.attributes[ATTR_CHANGED_BY_ID]
        if ATTR_CHANGED_BY in last_state.attributes:
            self._changed_by = last_state.attributes[ATTR_CHANGED_BY]

    def _watch_keypad(self, keypad, changeset):
        if keypad.area != self._element.index:
            return
        if changeset.get("last_user") is not None:
            self._changed_by_keypad = keypad.name
            self._changed_by_time = keypad.last_user_time.isoformat()
            self._changed_by_id = keypad.last_user + 1
            self._changed_by = self._elk.users.username(keypad.last_user)
            self.async_write_ha_state()

    def _watch_area(self, area, changeset):
        if not (last_log := changeset.get("last_log")):
            return
        # user_number only set for arm/disarm logs
        if not last_log.get("user_number"):
            return
        self._changed_by_keypad = None
        self._changed_by_id = last_log["user_number"]
        self._changed_by = self._elk.users.username(self._changed_by_id - 1)
        self._changed_by_time = last_log["timestamp"]
        self.async_write_ha_state()

    @property
    def code_format(self):
        """Return the alarm code format."""
        return CodeFormat.NUMBER

    @property
    def state(self):
        """Return the state of the element."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Attributes of the area."""
        attrs = self.initial_attrs()
        elmt = self._element
        attrs["is_exit"] = elmt.is_exit
        attrs["timer1"] = elmt.timer1
        attrs["timer2"] = elmt.timer2
        if elmt.armed_status is not None:
            attrs["armed_status"] = ArmedStatus(elmt.armed_status).name.lower()
        if elmt.arm_up_state is not None:
            attrs["arm_up_state"] = ArmUpState(elmt.arm_up_state).name.lower()
        if elmt.alarm_state is not None:
            attrs["alarm_state"] = AlarmState(elmt.alarm_state).name.lower()
        attrs[ATTR_CHANGED_BY_KEYPAD] = self._changed_by_keypad
        attrs[ATTR_CHANGED_BY_TIME] = self._changed_by_time
        attrs[ATTR_CHANGED_BY_ID] = self._changed_by_id
        return attrs

    @property
    def changed_by(self):
        """Last change triggered by."""
        return self._changed_by

    def _element_changed(self, element, changeset):
        elk_state_to_hass_state = {
            ArmedStatus.DISARMED.value: STATE_ALARM_DISARMED,
            ArmedStatus.ARMED_AWAY.value: STATE_ALARM_ARMED_AWAY,
            ArmedStatus.ARMED_STAY.value: STATE_ALARM_ARMED_HOME,
            ArmedStatus.ARMED_STAY_INSTANT.value: STATE_ALARM_ARMED_HOME,
            ArmedStatus.ARMED_TO_NIGHT.value: STATE_ALARM_ARMED_NIGHT,
            ArmedStatus.ARMED_TO_NIGHT_INSTANT.value: STATE_ALARM_ARMED_NIGHT,
            ArmedStatus.ARMED_TO_VACATION.value: STATE_ALARM_ARMED_AWAY,
        }

        if self._element.alarm_state is None:
            self._state = None
        elif self._area_is_in_alarm_state():
            self._state = STATE_ALARM_TRIGGERED
        elif self._entry_exit_timer_is_running():
            self._state = (
                STATE_ALARM_ARMING if self._element.is_exit else STATE_ALARM_PENDING
            )
        else:
            self._state = elk_state_to_hass_state[self._element.armed_status]

    def _entry_exit_timer_is_running(self):
        return self._element.timer1 > 0 or self._element.timer2 > 0

    def _area_is_in_alarm_state(self):
        return self._element.alarm_state >= AlarmState.FIRE_ALARM.value

    async def async_alarm_disarm(self, code=None):
        """Send disarm command."""
        self._element.disarm(int(code))

    async def async_alarm_arm_home(self, code=None):
        """Send arm home command."""
        self._element.arm(ArmLevel.ARMED_STAY.value, int(code))

    async def async_alarm_arm_away(self, code=None):
        """Send arm away command."""
        self._element.arm(ArmLevel.ARMED_AWAY.value, int(code))

    async def async_alarm_arm_night(self, code=None):
        """Send arm night command."""
        self._element.arm(ArmLevel.ARMED_NIGHT.value, int(code))

    async def async_alarm_arm_home_instant(self, code=None):
        """Send arm stay instant command."""
        self._element.arm(ArmLevel.ARMED_STAY_INSTANT.value, int(code))

    async def async_alarm_arm_night_instant(self, code=None):
        """Send arm night instant command."""
        self._element.arm(ArmLevel.ARMED_NIGHT_INSTANT.value, int(code))

    async def async_alarm_arm_vacation(self, code=None):
        """Send arm vacation command."""
        self._element.arm(ArmLevel.ARMED_VACATION.value, int(code))

    async def async_display_message(self, clear, beep, timeout, line1, line2):
        """Display a message on all keypads for the area."""
        self._element.display_message(clear, beep, timeout, line1, line2)

    async def async_bypass(self, code=None):
        """Bypass all zones in area."""
        self._element.bypass(code)

    async def async_clear_bypass(self, code=None):
        """Clear bypass for all zones in area."""
        self._element.clear_bypass(code)
