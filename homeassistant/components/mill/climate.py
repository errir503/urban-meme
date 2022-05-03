"""Support for mill wifi-enabled home heaters."""
import mill
import voluptuous as vol

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_OFF,
    FAN_ON,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_IP_ADDRESS,
    CONF_USERNAME,
    PRECISION_WHOLE,
    TEMP_CELSIUS,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_AWAY_TEMP,
    ATTR_COMFORT_TEMP,
    ATTR_ROOM_NAME,
    ATTR_SLEEP_TEMP,
    CLOUD,
    CONNECTION_TYPE,
    DOMAIN,
    LOCAL,
    MANUFACTURER,
    MAX_TEMP,
    MIN_TEMP,
    SERVICE_SET_ROOM_TEMP,
)

SET_ROOM_TEMP_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ROOM_NAME): cv.string,
        vol.Optional(ATTR_AWAY_TEMP): cv.positive_int,
        vol.Optional(ATTR_COMFORT_TEMP): cv.positive_int,
        vol.Optional(ATTR_SLEEP_TEMP): cv.positive_int,
    }
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Mill climate."""
    if entry.data.get(CONNECTION_TYPE) == LOCAL:
        mill_data_coordinator = hass.data[DOMAIN][LOCAL][entry.data[CONF_IP_ADDRESS]]
        async_add_entities([LocalMillHeater(mill_data_coordinator)])
        return

    mill_data_coordinator = hass.data[DOMAIN][CLOUD][entry.data[CONF_USERNAME]]

    entities = [
        MillHeater(mill_data_coordinator, mill_device)
        for mill_device in mill_data_coordinator.data.values()
        if isinstance(mill_device, mill.Heater)
    ]
    async_add_entities(entities)

    async def set_room_temp(service: ServiceCall) -> None:
        """Set room temp."""
        room_name = service.data.get(ATTR_ROOM_NAME)
        sleep_temp = service.data.get(ATTR_SLEEP_TEMP)
        comfort_temp = service.data.get(ATTR_COMFORT_TEMP)
        away_temp = service.data.get(ATTR_AWAY_TEMP)
        await mill_data_coordinator.mill_data_connection.set_room_temperatures_by_name(
            room_name, sleep_temp, comfort_temp, away_temp
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_ROOM_TEMP, set_room_temp, schema=SET_ROOM_TEMP_SCHEMA
    )


class MillHeater(CoordinatorEntity, ClimateEntity):
    """Representation of a Mill Thermostat device."""

    _attr_fan_modes = [FAN_ON, FAN_OFF]
    _attr_max_temp = MAX_TEMP
    _attr_min_temp = MIN_TEMP
    _attr_target_temperature_step = PRECISION_WHOLE
    _attr_temperature_unit = TEMP_CELSIUS

    def __init__(self, coordinator, heater):
        """Initialize the thermostat."""

        super().__init__(coordinator)

        self._available = False

        self._id = heater.device_id
        self._attr_unique_id = heater.device_id
        self._attr_name = heater.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, heater.device_id)},
            manufacturer=MANUFACTURER,
            model=f"Generation {heater.generation}",
            name=self.name,
        )
        if heater.is_gen1:
            self._attr_hvac_modes = [HVACMode.HEAT]
        else:
            self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]

        if heater.generation < 3:
            self._attr_supported_features = (
                ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
            )
        else:
            self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

        self._update_attr(heater)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.coordinator.mill_data_connection.set_heater_temp(
            self._id, int(temperature)
        )
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        fan_status = 1 if fan_mode == FAN_ON else 0
        await self.coordinator.mill_data_connection.heater_control(
            self._id, fan_status=fan_status
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        heater = self.coordinator.data[self._id]

        if hvac_mode == HVACMode.HEAT:
            await self.coordinator.mill_data_connection.heater_control(
                self._id, power_status=1
            )
            await self.coordinator.async_request_refresh()
        elif hvac_mode == HVACMode.OFF and not heater.is_gen1:
            await self.coordinator.mill_data_connection.heater_control(
                self._id, power_status=0
            )
            await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super().available and self._available

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attr(self.coordinator.data[self._id])
        self.async_write_ha_state()

    @callback
    def _update_attr(self, heater):
        self._available = heater.available
        self._attr_extra_state_attributes = {
            "open_window": heater.open_window,
            "heating": heater.is_heating,
            "controlled_by_tibber": heater.tibber_control,
            "heater_generation": heater.generation,
        }
        if heater.room:
            self._attr_extra_state_attributes["room"] = heater.room.name
            self._attr_extra_state_attributes["avg_room_temp"] = heater.room.avg_temp
        else:
            self._attr_extra_state_attributes["room"] = "Independent device"
        self._attr_target_temperature = heater.set_temp
        self._attr_current_temperature = heater.current_temp
        self._attr_fan_mode = FAN_ON if heater.fan_status == 1 else HVACMode.OFF
        if heater.is_heating == 1:
            self._attr_hvac_action = HVACAction.HEATING
        else:
            self._attr_hvac_action = HVACAction.IDLE
        if heater.is_gen1 or heater.power_status == 1:
            self._attr_hvac_mode = HVACMode.HEAT
        else:
            self._attr_hvac_mode = HVACMode.OFF


class LocalMillHeater(CoordinatorEntity, ClimateEntity):
    """Representation of a Mill Thermostat device."""

    _attr_hvac_mode = HVACMode.HEAT
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_max_temp = MAX_TEMP
    _attr_min_temp = MIN_TEMP
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = PRECISION_WHOLE
    _attr_temperature_unit = TEMP_CELSIUS

    def __init__(self, coordinator):
        """Initialize the thermostat."""
        super().__init__(coordinator)
        self._attr_name = coordinator.mill_data_connection.name
        if mac := coordinator.mill_data_connection.mac_address:
            self._attr_unique_id = mac
            self._attr_device_info = DeviceInfo(
                connections={(CONNECTION_NETWORK_MAC, mac)},
                configuration_url=self.coordinator.mill_data_connection.url,
                manufacturer=MANUFACTURER,
                model="Generation 3",
                name=coordinator.mill_data_connection.name,
                sw_version=coordinator.mill_data_connection.version,
            )

        self._update_attr()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.coordinator.mill_data_connection.set_target_temperature(
            int(temperature)
        )
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attr()
        self.async_write_ha_state()

    @callback
    def _update_attr(self) -> None:
        data = self.coordinator.data
        self._attr_target_temperature = data["set_temperature"]
        self._attr_current_temperature = data["ambient_temperature"]

        if data["current_power"] > 0:
            self._attr_hvac_action = HVACAction.HEATING
        else:
            self._attr_hvac_action = HVACAction.IDLE
