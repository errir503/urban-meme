"""Handle intents with scripts."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.const import CONF_TYPE, SERVICE_RELOAD
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import (
    config_validation as cv,
    intent,
    script,
    service,
    template,
)
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = "intent_script"

CONF_INTENTS = "intents"
CONF_SPEECH = "speech"
CONF_REPROMPT = "reprompt"

CONF_ACTION = "action"
CONF_CARD = "card"
CONF_TITLE = "title"
CONF_CONTENT = "content"
CONF_TEXT = "text"
CONF_ASYNC_ACTION = "async_action"

DEFAULT_CONF_ASYNC_ACTION = False

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: {
            cv.string: {
                vol.Optional(CONF_ACTION): cv.SCRIPT_SCHEMA,
                vol.Optional(
                    CONF_ASYNC_ACTION, default=DEFAULT_CONF_ASYNC_ACTION
                ): cv.boolean,
                vol.Optional(CONF_CARD): {
                    vol.Optional(CONF_TYPE, default="simple"): cv.string,
                    vol.Required(CONF_TITLE): cv.template,
                    vol.Required(CONF_CONTENT): cv.template,
                },
                vol.Optional(CONF_SPEECH): {
                    vol.Optional(CONF_TYPE, default="plain"): cv.string,
                    vol.Required(CONF_TEXT): cv.template,
                },
                vol.Optional(CONF_REPROMPT): {
                    vol.Optional(CONF_TYPE, default="plain"): cv.string,
                    vol.Required(CONF_TEXT): cv.template,
                },
            }
        }
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_reload(hass: HomeAssistant, servie_call: ServiceCall) -> None:
    """Handle start Intent Script service call."""
    new_config = await async_integration_yaml_config(hass, DOMAIN)
    existing_intents = hass.data[DOMAIN]

    for intent_type in existing_intents:
        intent.async_remove(hass, intent_type)

    if not new_config or DOMAIN not in new_config:
        hass.data[DOMAIN] = {}
        return

    new_intents = new_config[DOMAIN]

    async_load_intents(hass, new_intents)


def async_load_intents(hass: HomeAssistant, intents: dict):
    """Load YAML intents into the intent system."""
    template.attach(hass, intents)
    hass.data[DOMAIN] = intents

    for intent_type, conf in intents.items():
        if CONF_ACTION in conf:
            conf[CONF_ACTION] = script.Script(
                hass, conf[CONF_ACTION], f"Intent Script {intent_type}", DOMAIN
            )
        intent.async_register(hass, ScriptIntentHandler(intent_type, conf))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the intent script component."""
    intents = config[DOMAIN]

    async_load_intents(hass, intents)

    async def _handle_reload(servie_call: ServiceCall) -> None:
        return await async_reload(hass, servie_call)

    service.async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_RELOAD,
        _handle_reload,
    )

    return True


class ScriptIntentHandler(intent.IntentHandler):
    """Respond to an intent with a script."""

    def __init__(self, intent_type, config):
        """Initialize the script intent handler."""
        self.intent_type = intent_type
        self.config = config

    async def async_handle(self, intent_obj: intent.Intent):
        """Handle the intent."""
        speech = self.config.get(CONF_SPEECH)
        reprompt = self.config.get(CONF_REPROMPT)
        card = self.config.get(CONF_CARD)
        action = self.config.get(CONF_ACTION)
        is_async_action = self.config.get(CONF_ASYNC_ACTION)
        slots = {key: value["value"] for key, value in intent_obj.slots.items()}

        _LOGGER.debug(
            "Intent named %s received with slots: %s",
            intent_obj.intent_type,
            {
                key: value
                for key, value in slots.items()
                if not key.startswith("_") and not key.endswith("_raw_value")
            },
        )

        if action is not None:
            if is_async_action:
                intent_obj.hass.async_create_task(
                    action.async_run(slots, intent_obj.context)
                )
            else:
                await action.async_run(slots, intent_obj.context)

        response = intent_obj.create_response()

        if speech is not None:
            response.async_set_speech(
                speech[CONF_TEXT].async_render(slots, parse_result=False),
                speech[CONF_TYPE],
            )

        if reprompt is not None:
            text_reprompt = reprompt[CONF_TEXT].async_render(slots, parse_result=False)
            if text_reprompt:
                response.async_set_reprompt(
                    text_reprompt,
                    reprompt[CONF_TYPE],
                )

        if card is not None:
            response.async_set_card(
                card[CONF_TITLE].async_render(slots, parse_result=False),
                card[CONF_CONTENT].async_render(slots, parse_result=False),
                card[CONF_TYPE],
            )

        return response
