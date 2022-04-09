"""Support for using humidifier with ecobee thermostats."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.humidifier import (
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.components.humidifier.const import (
    DEFAULT_MAX_HUMIDITY,
    DEFAULT_MIN_HUMIDITY,
    MODE_AUTO,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ECOBEE_MODEL_TO_NAME, MANUFACTURER

SCAN_INTERVAL = timedelta(minutes=3)

MODE_MANUAL = "manual"
MODE_OFF = "off"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ecobee thermostat humidifier entity."""
    data = hass.data[DOMAIN]
    entities = []
    for index in range(len(data.ecobee.thermostats)):
        thermostat = data.ecobee.get_thermostat(index)
        if thermostat["settings"]["hasHumidifier"]:
            entities.append(EcobeeHumidifier(data, index))

    async_add_entities(entities, True)


class EcobeeHumidifier(HumidifierEntity):
    """A humidifier class for an ecobee thermostat with humidifier attached."""

    _attr_supported_features = HumidifierEntityFeature.MODES

    def __init__(self, data, thermostat_index):
        """Initialize ecobee humidifier platform."""
        self.data = data
        self.thermostat_index = thermostat_index
        self.thermostat = self.data.ecobee.get_thermostat(self.thermostat_index)
        self._name = self.thermostat["name"]
        self._last_humidifier_on_mode = MODE_MANUAL

        self.update_without_throttle = False

    @property
    def name(self):
        """Return the name of the humidifier."""
        return self._name

    @property
    def unique_id(self):
        """Return unique_id for humidifier."""
        return f"{self.thermostat['identifier']}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the ecobee humidifier."""
        model: str | None
        try:
            model = f"{ECOBEE_MODEL_TO_NAME[self.thermostat['modelNumber']]} Thermostat"
        except KeyError:
            # Ecobee model is not in our list
            model = None

        return DeviceInfo(
            identifiers={(DOMAIN, self.thermostat["identifier"])},
            manufacturer=MANUFACTURER,
            model=model,
            name=self.name,
        )

    @property
    def available(self):
        """Return if device is available."""
        return self.thermostat["runtime"]["connected"]

    async def async_update(self):
        """Get the latest state from the thermostat."""
        if self.update_without_throttle:
            await self.data.update(no_throttle=True)
            self.update_without_throttle = False
        else:
            await self.data.update()
        self.thermostat = self.data.ecobee.get_thermostat(self.thermostat_index)
        if self.mode != MODE_OFF:
            self._last_humidifier_on_mode = self.mode

    @property
    def available_modes(self):
        """Return the list of available modes."""
        return [MODE_OFF, MODE_AUTO, MODE_MANUAL]

    @property
    def device_class(self):
        """Return the device class type."""
        return HumidifierDeviceClass.HUMIDIFIER

    @property
    def is_on(self):
        """Return True if the humidifier is on."""
        return self.mode != MODE_OFF

    @property
    def max_humidity(self):
        """Return the maximum humidity."""
        return DEFAULT_MAX_HUMIDITY

    @property
    def min_humidity(self):
        """Return the minimum humidity."""
        return DEFAULT_MIN_HUMIDITY

    @property
    def mode(self):
        """Return the current mode, e.g., off, auto, manual."""
        return self.thermostat["settings"]["humidifierMode"]

    @property
    def target_humidity(self) -> int:
        """Return the desired humidity set point."""
        return int(self.thermostat["runtime"]["desiredHumidity"])

    def set_mode(self, mode):
        """Set humidifier mode (auto, off, manual)."""
        if mode.lower() not in (self.available_modes):
            raise ValueError(
                f"Invalid mode value: {mode}  Valid values are {', '.join(self.available_modes)}."
            )

        self.data.ecobee.set_humidifier_mode(self.thermostat_index, mode)
        self.update_without_throttle = True

    def set_humidity(self, humidity):
        """Set the humidity level."""
        self.data.ecobee.set_humidity(self.thermostat_index, humidity)
        self.update_without_throttle = True

    def turn_off(self, **kwargs):
        """Set humidifier to off mode."""
        self.set_mode(MODE_OFF)

    def turn_on(self, **kwargs):
        """Set humidifier to on mode."""
        self.set_mode(self._last_humidifier_on_mode)
