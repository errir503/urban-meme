"""Demo fan platform that has a fake fan."""
from __future__ import annotations

from homeassistant.components.fan import (
    SUPPORT_DIRECTION,
    SUPPORT_OSCILLATE,
    SUPPORT_PRESET_MODE,
    SUPPORT_SET_SPEED,
    FanEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

PRESET_MODE_AUTO = "auto"
PRESET_MODE_SMART = "smart"
PRESET_MODE_SLEEP = "sleep"
PRESET_MODE_ON = "on"

FULL_SUPPORT = SUPPORT_SET_SPEED | SUPPORT_OSCILLATE | SUPPORT_DIRECTION
LIMITED_SUPPORT = SUPPORT_SET_SPEED


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the demo fan platform."""
    async_add_entities(
        [
            DemoPercentageFan(
                hass,
                "fan1",
                "Living Room Fan",
                FULL_SUPPORT,
                [
                    PRESET_MODE_AUTO,
                    PRESET_MODE_SMART,
                    PRESET_MODE_SLEEP,
                    PRESET_MODE_ON,
                ],
            ),
            DemoPercentageFan(
                hass,
                "fan2",
                "Ceiling Fan",
                LIMITED_SUPPORT,
                None,
            ),
            AsyncDemoPercentageFan(
                hass,
                "fan3",
                "Percentage Full Fan",
                FULL_SUPPORT,
                [
                    PRESET_MODE_AUTO,
                    PRESET_MODE_SMART,
                    PRESET_MODE_SLEEP,
                    PRESET_MODE_ON,
                ],
            ),
            DemoPercentageFan(
                hass,
                "fan4",
                "Percentage Limited Fan",
                LIMITED_SUPPORT,
                [
                    PRESET_MODE_AUTO,
                    PRESET_MODE_SMART,
                    PRESET_MODE_SLEEP,
                    PRESET_MODE_ON,
                ],
            ),
            AsyncDemoPercentageFan(
                hass,
                "fan5",
                "Preset Only Limited Fan",
                SUPPORT_PRESET_MODE,
                [
                    PRESET_MODE_AUTO,
                    PRESET_MODE_SMART,
                    PRESET_MODE_SLEEP,
                    PRESET_MODE_ON,
                ],
            ),
        ]
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Demo config entry."""
    await async_setup_platform(hass, {}, async_add_entities)


class BaseDemoFan(FanEntity):
    """A demonstration fan component that uses legacy fan speeds."""

    def __init__(
        self,
        hass,
        unique_id: str,
        name: str,
        supported_features: int,
        preset_modes: list[str] | None,
    ) -> None:
        """Initialize the entity."""
        self.hass = hass
        self._unique_id = unique_id
        self._supported_features = supported_features
        self._percentage: int | None = None
        self._preset_modes = preset_modes
        self._preset_mode: str | None = None
        self._oscillating: bool | None = None
        self._direction: str | None = None
        self._name = name
        if supported_features & SUPPORT_OSCILLATE:
            self._oscillating = False
        if supported_features & SUPPORT_DIRECTION:
            self._direction = "forward"

    @property
    def unique_id(self):
        """Return the unique id."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Get entity name."""
        return self._name

    @property
    def should_poll(self):
        """No polling needed for a demo fan."""
        return False

    @property
    def current_direction(self) -> str | None:
        """Fan direction."""
        return self._direction

    @property
    def oscillating(self) -> bool | None:
        """Oscillating."""
        return self._oscillating

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return self._supported_features


class DemoPercentageFan(BaseDemoFan, FanEntity):
    """A demonstration fan component that uses percentages."""

    @property
    def percentage(self) -> int | None:
        """Return the current speed."""
        return self._percentage

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return 3

    def set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        self._percentage = percentage
        self._preset_mode = None
        self.schedule_update_ha_state()

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        return self._preset_mode

    @property
    def preset_modes(self) -> list[str] | None:
        """Return a list of available preset modes."""
        return self._preset_modes

    def set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if self.preset_modes and preset_mode in self.preset_modes:
            self._preset_mode = preset_mode
            self._percentage = None
            self.schedule_update_ha_state()
        else:
            raise ValueError(f"Invalid preset mode: {preset_mode}")

    def turn_on(
        self,
        speed: str = None,
        percentage: int = None,
        preset_mode: str = None,
        **kwargs,
    ) -> None:
        """Turn on the entity."""
        if preset_mode:
            self.set_preset_mode(preset_mode)
            return

        if percentage is None:
            percentage = 67

        self.set_percentage(percentage)

    def turn_off(self, **kwargs) -> None:
        """Turn off the entity."""
        self.set_percentage(0)

    def set_direction(self, direction: str) -> None:
        """Set the direction of the fan."""
        self._direction = direction
        self.schedule_update_ha_state()

    def oscillate(self, oscillating: bool) -> None:
        """Set oscillation."""
        self._oscillating = oscillating
        self.schedule_update_ha_state()


class AsyncDemoPercentageFan(BaseDemoFan, FanEntity):
    """An async demonstration fan component that uses percentages."""

    @property
    def percentage(self) -> int | None:
        """Return the current speed."""
        return self._percentage

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return 3

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        self._percentage = percentage
        self._preset_mode = None
        self.async_write_ha_state()

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        return self._preset_mode

    @property
    def preset_modes(self) -> list[str] | None:
        """Return a list of available preset modes."""
        return self._preset_modes

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if self.preset_modes is None or preset_mode not in self.preset_modes:
            raise ValueError(
                "{preset_mode} is not a valid preset_mode: {self.preset_modes}"
            )
        self._preset_mode = preset_mode
        self._percentage = None
        self.async_write_ha_state()

    async def async_turn_on(
        self,
        speed: str = None,
        percentage: int = None,
        preset_mode: str = None,
        **kwargs,
    ) -> None:
        """Turn on the entity."""
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
            return

        if percentage is None:
            percentage = 67

        await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the entity."""
        await self.async_oscillate(False)
        await self.async_set_percentage(0)

    async def async_set_direction(self, direction: str) -> None:
        """Set the direction of the fan."""
        self._direction = direction
        self.async_write_ha_state()

    async def async_oscillate(self, oscillating: bool) -> None:
        """Set oscillation."""
        self._oscillating = oscillating
        self.async_write_ha_state()
