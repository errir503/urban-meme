"""Integration with the Rachio Iro sprinkler system controller."""
from abc import abstractmethod
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN as DOMAIN_RACHIO,
    KEY_DEVICE_ID,
    KEY_RAIN_SENSOR_TRIPPED,
    KEY_STATUS,
    KEY_SUBTYPE,
    SIGNAL_RACHIO_CONTROLLER_UPDATE,
    SIGNAL_RACHIO_RAIN_SENSOR_UPDATE,
    STATUS_ONLINE,
)
from .device import RachioPerson
from .entity import RachioDevice
from .webhooks import (
    SUBTYPE_COLD_REBOOT,
    SUBTYPE_OFFLINE,
    SUBTYPE_ONLINE,
    SUBTYPE_RAIN_SENSOR_DETECTION_OFF,
    SUBTYPE_RAIN_SENSOR_DETECTION_ON,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Rachio binary sensors."""
    entities = await hass.async_add_executor_job(_create_entities, hass, config_entry)
    async_add_entities(entities)


def _create_entities(hass: HomeAssistant, config_entry: ConfigEntry) -> list[Entity]:
    entities: list[Entity] = []
    person: RachioPerson = hass.data[DOMAIN_RACHIO][config_entry.entry_id]
    for controller in person.controllers:
        entities.append(RachioControllerOnlineBinarySensor(controller))
        entities.append(RachioRainSensor(controller))
    return entities


class RachioControllerBinarySensor(RachioDevice, BinarySensorEntity):
    """Represent a binary sensor that reflects a Rachio state."""

    _attr_has_entity_name = True

    @callback
    def _async_handle_any_update(self, *args, **kwargs) -> None:
        """Determine whether an update event applies to this device."""
        if args[0][KEY_DEVICE_ID] != self._controller.controller_id:
            # For another device
            return

        # For this device
        self._async_handle_update(args, kwargs)

    @abstractmethod
    def _async_handle_update(self, *args, **kwargs) -> None:
        """Handle an update to the state of this sensor."""


class RachioControllerOnlineBinarySensor(RachioControllerBinarySensor):
    """Represent a binary sensor that reflects if the controller is online."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def unique_id(self) -> str:
        """Return a unique id for this entity."""
        return f"{self._controller.controller_id}-online"

    @callback
    def _async_handle_update(self, *args, **kwargs) -> None:
        """Handle an update to the state of this sensor."""
        if args[0][0][KEY_SUBTYPE] in (SUBTYPE_ONLINE, SUBTYPE_COLD_REBOOT):
            self._attr_is_on = True
        elif args[0][0][KEY_SUBTYPE] == SUBTYPE_OFFLINE:
            self._attr_is_on = False

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        self._attr_is_on = self._controller.init_data[KEY_STATUS] == STATUS_ONLINE

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_RACHIO_CONTROLLER_UPDATE,
                self._async_handle_any_update,
            )
        )


class RachioRainSensor(RachioControllerBinarySensor):
    """Represent a binary sensor that reflects the status of the rain sensor."""

    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_translation_key = "rain"

    @property
    def unique_id(self) -> str:
        """Return a unique id for this entity."""
        return f"{self._controller.controller_id}-rain_sensor"

    @callback
    def _async_handle_update(self, *args, **kwargs) -> None:
        """Handle an update to the state of this sensor."""
        if args[0][0][KEY_SUBTYPE] == SUBTYPE_RAIN_SENSOR_DETECTION_ON:
            self._attr_is_on = True
        elif args[0][0][KEY_SUBTYPE] == SUBTYPE_RAIN_SENSOR_DETECTION_OFF:
            self._attr_is_on = False

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        self._attr_is_on = self._controller.init_data[KEY_RAIN_SENSOR_TRIPPED]

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_RACHIO_RAIN_SENSOR_UPDATE,
                self._async_handle_any_update,
            )
        )
