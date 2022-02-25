"""Sensor platform for the GitHub integration."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GitHubDataUpdateCoordinator


@dataclass
class BaseEntityDescriptionMixin:
    """Mixin for required GitHub base description keys."""

    value_fn: Callable[[dict[str, Any]], StateType]


@dataclass
class BaseEntityDescription(SensorEntityDescription):
    """Describes GitHub sensor entity default overrides."""

    icon: str = "mdi:github"
    attr_fn: Callable[[dict[str, Any]], Mapping[str, Any] | None] = lambda data: None
    avabl_fn: Callable[[dict[str, Any]], bool] = lambda data: True


@dataclass
class GitHubSensorEntityDescription(BaseEntityDescription, BaseEntityDescriptionMixin):
    """Describes GitHub issue sensor entity."""


SENSOR_DESCRIPTIONS: tuple[GitHubSensorEntityDescription, ...] = (
    GitHubSensorEntityDescription(
        key="discussions_count",
        name="Discussions",
        native_unit_of_measurement="Discussions",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["discussion"]["total"],
    ),
    GitHubSensorEntityDescription(
        key="stargazers_count",
        name="Stars",
        icon="mdi:star",
        native_unit_of_measurement="Stars",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["stargazers_count"],
    ),
    GitHubSensorEntityDescription(
        key="subscribers_count",
        name="Watchers",
        icon="mdi:glasses",
        native_unit_of_measurement="Watchers",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["watchers"]["total"],
    ),
    GitHubSensorEntityDescription(
        key="forks_count",
        name="Forks",
        icon="mdi:source-fork",
        native_unit_of_measurement="Forks",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["forks_count"],
    ),
    GitHubSensorEntityDescription(
        key="issues_count",
        name="Issues",
        native_unit_of_measurement="Issues",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["issue"]["total"],
    ),
    GitHubSensorEntityDescription(
        key="pulls_count",
        name="Pull Requests",
        native_unit_of_measurement="Pull Requests",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["pull_request"]["total"],
    ),
    GitHubSensorEntityDescription(
        key="latest_commit",
        name="Latest Commit",
        value_fn=lambda data: data["default_branch_ref"]["commit"]["message"][:255],
        attr_fn=lambda data: {
            "sha": data["default_branch_ref"]["commit"]["sha"],
            "url": data["default_branch_ref"]["commit"]["url"],
        },
    ),
    GitHubSensorEntityDescription(
        key="latest_discussion",
        name="Latest Discussion",
        avabl_fn=lambda data: data["discussion"]["discussions"],
        value_fn=lambda data: data["discussion"]["discussions"][0]["title"][:255],
        attr_fn=lambda data: {
            "url": data["discussion"]["discussions"][0]["url"],
            "number": data["discussion"]["discussions"][0]["number"],
        },
    ),
    GitHubSensorEntityDescription(
        key="latest_release",
        name="Latest Release",
        avabl_fn=lambda data: data["release"] is not None,
        value_fn=lambda data: data["release"]["name"][:255],
        attr_fn=lambda data: {
            "url": data["release"]["url"],
            "tag": data["release"]["tag"],
        },
    ),
    GitHubSensorEntityDescription(
        key="latest_issue",
        name="Latest Issue",
        avabl_fn=lambda data: data["issue"]["issues"],
        value_fn=lambda data: data["issue"]["issues"][0]["title"][:255],
        attr_fn=lambda data: {
            "url": data["issue"]["issues"][0]["url"],
            "number": data["issue"]["issues"][0]["number"],
        },
    ),
    GitHubSensorEntityDescription(
        key="latest_pull_request",
        name="Latest Pull Request",
        avabl_fn=lambda data: data["pull_request"]["pull_requests"],
        value_fn=lambda data: data["pull_request"]["pull_requests"][0]["title"][:255],
        attr_fn=lambda data: {
            "url": data["pull_request"]["pull_requests"][0]["url"],
            "number": data["pull_request"]["pull_requests"][0]["number"],
        },
    ),
    GitHubSensorEntityDescription(
        key="latest_tag",
        name="Latest Tag",
        avabl_fn=lambda data: data["refs"]["tags"],
        value_fn=lambda data: data["refs"]["tags"][0]["name"][:255],
        attr_fn=lambda data: {
            "url": data["refs"]["tags"][0]["target"]["url"],
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GitHub sensor based on a config entry."""
    repositories: dict[str, GitHubDataUpdateCoordinator] = hass.data[DOMAIN]
    async_add_entities(
        (
            GitHubSensorEntity(coordinator, description)
            for description in SENSOR_DESCRIPTIONS
            for coordinator in repositories.values()
        ),
    )


class GitHubSensorEntity(CoordinatorEntity[dict[str, Any]], SensorEntity):
    """Defines a GitHub sensor entity."""

    _attr_attribution = "Data provided by the GitHub API"

    coordinator: GitHubDataUpdateCoordinator
    entity_description: GitHubSensorEntityDescription

    def __init__(
        self,
        coordinator: GitHubDataUpdateCoordinator,
        entity_description: GitHubSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)

        self.entity_description = entity_description
        self._attr_name = (
            f"{coordinator.data.get('full_name')} {entity_description.name}"
        )
        self._attr_unique_id = f"{coordinator.data.get('id')}_{entity_description.key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.repository)},
            name=coordinator.data.get("full_name"),
            manufacturer="GitHub",
            configuration_url=f"https://github.com/{coordinator.repository}",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.entity_description.avabl_fn(self.coordinator.data)
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the extra state attributes."""
        return self.entity_description.attr_fn(self.coordinator.data)
