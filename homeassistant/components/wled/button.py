"""Support for WLED button."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LOGGER
from .coordinator import WLEDDataUpdateCoordinator
from .helpers import wled_exception_handler
from .models import WLEDEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WLED button based on a config entry."""
    coordinator: WLEDDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            WLEDRestartButton(coordinator),
            WLEDUpdateButton(coordinator),
        ]
    )


class WLEDRestartButton(WLEDEntity, ButtonEntity):
    """Defines a WLED restart button."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: WLEDDataUpdateCoordinator) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator=coordinator)
        self._attr_name = f"{coordinator.data.info.name} Restart"
        self._attr_unique_id = f"{coordinator.data.info.mac_address}_restart"

    @wled_exception_handler
    async def async_press(self) -> None:
        """Send out a restart command."""
        await self.coordinator.wled.reset()


class WLEDUpdateButton(WLEDEntity, ButtonEntity):
    """Defines a WLED update button."""

    _attr_device_class = ButtonDeviceClass.UPDATE
    _attr_entity_category = EntityCategory.CONFIG

    # Disabled by default, as this entity is deprecated.
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: WLEDDataUpdateCoordinator) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator=coordinator)
        self._attr_name = f"{coordinator.data.info.name} Update"
        self._attr_unique_id = f"{coordinator.data.info.mac_address}_update"

    @property
    def available(self) -> bool:
        """Return if the entity and an update is available."""
        current = self.coordinator.data.info.version
        beta = self.coordinator.data.info.version_latest_beta
        stable = self.coordinator.data.info.version_latest_stable

        # If we already run a pre-release, allow upgrading to a newer
        # pre-release offer a normal upgrade otherwise.
        return (
            super().available
            and current is not None
            and (
                (stable is not None and stable > current)
                or (
                    beta is not None
                    and (current.alpha or current.beta or current.release_candidate)
                    and beta > current
                )
            )
        )

    @wled_exception_handler
    async def async_press(self) -> None:
        """Send out a update command."""
        LOGGER.warning(
            "The WLED update button '%s' is deprecated, please "
            "use the new update entity as a replacement",
            self.entity_id,
        )
        current = self.coordinator.data.info.version
        beta = self.coordinator.data.info.version_latest_beta
        stable = self.coordinator.data.info.version_latest_stable

        # If we already run a pre-release, allow update to a newer
        # pre-release or newer stable, otherwise, offer a normal stable updates.
        version = stable
        if (
            current is not None
            and beta is not None
            and (current.alpha or current.beta or current.release_candidate)
            and beta > current
            and beta > stable
        ):
            version = beta

        await self.coordinator.wled.upgrade(version=str(version))
