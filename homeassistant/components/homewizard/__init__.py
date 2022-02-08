"""The Homewizard integration."""
import logging

from aiohwenergy import DisabledError

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN, PLATFORMS
from .coordinator import HWEnergyDeviceUpdateCoordinator as Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Homewizard from a config entry."""

    _LOGGER.debug("__init__ async_setup_entry")

    # Migrate `homewizard_energy` (custom_component) to `homewizard`
    if entry.source == SOURCE_IMPORT and "old_config_entry_id" in entry.data:
        # Remove the old config entry ID from the entry data so we don't try this again
        # on the next setup
        data = entry.data.copy()
        old_config_entry_id = data.pop("old_config_entry_id")

        hass.config_entries.async_update_entry(entry, data=data)
        _LOGGER.debug(
            (
                "Setting up imported homewizard_energy entry %s for the first time as "
                "homewizard entry %s"
            ),
            old_config_entry_id,
            entry.entry_id,
        )

        ent_reg = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(ent_reg, old_config_entry_id):
            _LOGGER.debug("Removing %s", entity.entity_id)
            ent_reg.async_remove(entity.entity_id)

            _LOGGER.debug("Re-creating %s for the new config entry", entity.entity_id)
            # We will precreate the entity so that any customizations can be preserved
            new_entity = ent_reg.async_get_or_create(
                entity.domain,
                DOMAIN,
                entity.unique_id,
                suggested_object_id=entity.entity_id.split(".")[1],
                disabled_by=entity.disabled_by,
                config_entry=entry,
                original_name=entity.original_name,
                original_icon=entity.original_icon,
            )
            _LOGGER.debug("Re-created %s", new_entity.entity_id)

            # If there are customizations on the old entity, apply them to the new one
            if entity.name or entity.icon:
                ent_reg.async_update_entity(
                    new_entity.entity_id, name=entity.name, icon=entity.icon
                )

        # Remove the old config entry and now the entry is fully migrated
        hass.async_create_task(hass.config_entries.async_remove(old_config_entry_id))

    # Create coordinator
    coordinator = Coordinator(hass, entry.data[CONF_IP_ADDRESS])
    try:
        await coordinator.initialize_api()

    except DisabledError:
        _LOGGER.error("API is disabled, enable API in HomeWizard Energy app")
        return False

    except UpdateFailed as ex:
        raise ConfigEntryNotReady from ex

    await coordinator.async_config_entry_first_refresh()

    # Finalize
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("__init__ async_unload_entry")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        config_data = hass.data[DOMAIN].pop(entry.entry_id)
        await config_data.api.close()

    return unload_ok
