"""Support for Litter-Robot button."""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import itertools
from typing import Any, Generic

from pylitterbot import FeederRobot, LitterRobot3

from homeassistant.components.button import (
    DOMAIN as PLATFORM,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import LitterRobotEntity, _RobotT, async_update_unique_id
from .hub import LitterRobotHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Litter-Robot cleaner using config entry."""
    hub: LitterRobotHub = hass.data[DOMAIN][entry.entry_id]
    entities: list[LitterRobotButtonEntity] = list(
        itertools.chain(
            (
                LitterRobotButtonEntity(
                    robot=robot, hub=hub, description=LITTER_ROBOT_BUTTON
                )
                for robot in hub.litter_robots()
                if isinstance(robot, LitterRobot3)
            ),
            (
                LitterRobotButtonEntity(
                    robot=robot, hub=hub, description=FEEDER_ROBOT_BUTTON
                )
                for robot in hub.feeder_robots()
            ),
        )
    )
    async_update_unique_id(hass, PLATFORM, entities)
    async_add_entities(entities)


@dataclass
class RequiredKeysMixin(Generic[_RobotT]):
    """A class that describes robot button entity required keys."""

    press_fn: Callable[[_RobotT], Coroutine[Any, Any, bool]]


@dataclass
class RobotButtonEntityDescription(ButtonEntityDescription, RequiredKeysMixin[_RobotT]):
    """A class that describes robot button entities."""


LITTER_ROBOT_BUTTON = RobotButtonEntityDescription[LitterRobot3](
    key="reset_waste_drawer",
    name="Reset Waste Drawer",
    icon="mdi:delete-variant",
    entity_category=EntityCategory.CONFIG,
    press_fn=lambda robot: robot.reset_waste_drawer(),
)
FEEDER_ROBOT_BUTTON = RobotButtonEntityDescription[FeederRobot](
    key="give_snack",
    name="Give snack",
    icon="mdi:candy-outline",
    press_fn=lambda robot: robot.give_snack(),
)


class LitterRobotButtonEntity(LitterRobotEntity[_RobotT], ButtonEntity):
    """Litter-Robot button entity."""

    entity_description: RobotButtonEntityDescription[_RobotT]

    async def async_press(self) -> None:
        """Press the button."""
        await self.entity_description.press_fn(self.robot)
        self.coordinator.async_set_updated_data(True)
