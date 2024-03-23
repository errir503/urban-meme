"""Describe group states."""

from typing import TYPE_CHECKING

from homeassistant.const import STATE_CLOSED, STATE_OPEN
from homeassistant.core import HomeAssistant, callback

if TYPE_CHECKING:
    from homeassistant.components.group import GroupIntegrationRegistry


@callback
def async_describe_on_off_states(
    hass: HomeAssistant, registry: "GroupIntegrationRegistry"
) -> None:
    """Describe group on off states."""
    # On means open, Off means closed
    registry.on_off_states({STATE_OPEN}, STATE_CLOSED)
