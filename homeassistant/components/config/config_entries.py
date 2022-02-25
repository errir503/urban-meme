"""Http views to control the config manager."""
from __future__ import annotations

from http import HTTPStatus

from aiohttp import web
import aiohttp.web_exceptions
import voluptuous as vol

from homeassistant import config_entries, data_entry_flow
from homeassistant.auth.permissions.const import CAT_CONFIG_ENTRIES, POLICY_EDIT
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import DependencyError, Unauthorized
from homeassistant.helpers.data_entry_flow import (
    FlowManagerIndexView,
    FlowManagerResourceView,
)
from homeassistant.loader import async_get_config_flows


async def async_setup(hass):
    """Enable the Home Assistant views."""
    hass.http.register_view(ConfigManagerEntryIndexView)
    hass.http.register_view(ConfigManagerEntryResourceView)
    hass.http.register_view(ConfigManagerEntryResourceReloadView)
    hass.http.register_view(ConfigManagerFlowIndexView(hass.config_entries.flow))
    hass.http.register_view(ConfigManagerFlowResourceView(hass.config_entries.flow))
    hass.http.register_view(ConfigManagerAvailableFlowView)

    hass.http.register_view(OptionManagerFlowIndexView(hass.config_entries.options))
    hass.http.register_view(OptionManagerFlowResourceView(hass.config_entries.options))

    websocket_api.async_register_command(hass, config_entry_disable)
    websocket_api.async_register_command(hass, config_entry_update)
    websocket_api.async_register_command(hass, config_entries_progress)
    websocket_api.async_register_command(hass, ignore_config_flow)

    return True


class ConfigManagerEntryIndexView(HomeAssistantView):
    """View to get available config entries."""

    url = "/api/config/config_entries/entry"
    name = "api:config:config_entries:entry"

    async def get(self, request):
        """List available config entries."""
        hass = request.app["hass"]

        return self.json(
            [entry_json(entry) for entry in hass.config_entries.async_entries()]
        )


class ConfigManagerEntryResourceView(HomeAssistantView):
    """View to interact with a config entry."""

    url = "/api/config/config_entries/entry/{entry_id}"
    name = "api:config:config_entries:entry:resource"

    async def delete(self, request, entry_id):
        """Delete a config entry."""
        if not request["hass_user"].is_admin:
            raise Unauthorized(config_entry_id=entry_id, permission="remove")

        hass = request.app["hass"]

        try:
            result = await hass.config_entries.async_remove(entry_id)
        except config_entries.UnknownEntry:
            return self.json_message("Invalid entry specified", HTTPStatus.NOT_FOUND)

        return self.json(result)


class ConfigManagerEntryResourceReloadView(HomeAssistantView):
    """View to reload a config entry."""

    url = "/api/config/config_entries/entry/{entry_id}/reload"
    name = "api:config:config_entries:entry:resource:reload"

    async def post(self, request, entry_id):
        """Reload a config entry."""
        if not request["hass_user"].is_admin:
            raise Unauthorized(config_entry_id=entry_id, permission="remove")

        hass = request.app["hass"]
        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry:
            return self.json_message("Invalid entry specified", HTTPStatus.NOT_FOUND)
        assert isinstance(entry, config_entries.ConfigEntry)

        try:
            await hass.config_entries.async_reload(entry_id)
        except config_entries.OperationNotAllowed:
            return self.json_message("Entry cannot be reloaded", HTTPStatus.FORBIDDEN)

        return self.json({"require_restart": not entry.state.recoverable})


def _prepare_config_flow_result_json(result, prepare_result_json):
    """Convert result to JSON."""
    if result["type"] != data_entry_flow.RESULT_TYPE_CREATE_ENTRY:
        return prepare_result_json(result)

    data = result.copy()
    data["result"] = entry_json(result["result"])
    data.pop("data")
    return data


class ConfigManagerFlowIndexView(FlowManagerIndexView):
    """View to create config flows."""

    url = "/api/config/config_entries/flow"
    name = "api:config:config_entries:flow"

    async def get(self, request):
        """Not implemented."""
        # pylint: disable=no-self-use
        raise aiohttp.web_exceptions.HTTPMethodNotAllowed("GET", ["POST"])

    # pylint: disable=arguments-differ
    async def post(self, request):
        """Handle a POST request."""
        if not request["hass_user"].is_admin:
            raise Unauthorized(perm_category=CAT_CONFIG_ENTRIES, permission="add")

        # pylint: disable=no-value-for-parameter
        try:
            return await super().post(request)
        except DependencyError as exc:
            return web.Response(
                text=f"Failed dependencies {', '.join(exc.failed_dependencies)}",
                status=HTTPStatus.BAD_REQUEST,
            )

    def _prepare_result_json(self, result):
        """Convert result to JSON."""
        return _prepare_config_flow_result_json(result, super()._prepare_result_json)


class ConfigManagerFlowResourceView(FlowManagerResourceView):
    """View to interact with the flow manager."""

    url = "/api/config/config_entries/flow/{flow_id}"
    name = "api:config:config_entries:flow:resource"

    async def get(self, request, flow_id):
        """Get the current state of a data_entry_flow."""
        if not request["hass_user"].is_admin:
            raise Unauthorized(perm_category=CAT_CONFIG_ENTRIES, permission="add")

        return await super().get(request, flow_id)

    # pylint: disable=arguments-differ
    async def post(self, request, flow_id):
        """Handle a POST request."""
        if not request["hass_user"].is_admin:
            raise Unauthorized(perm_category=CAT_CONFIG_ENTRIES, permission="add")

        # pylint: disable=no-value-for-parameter
        return await super().post(request, flow_id)

    def _prepare_result_json(self, result):
        """Convert result to JSON."""
        return _prepare_config_flow_result_json(result, super()._prepare_result_json)


class ConfigManagerAvailableFlowView(HomeAssistantView):
    """View to query available flows."""

    url = "/api/config/config_entries/flow_handlers"
    name = "api:config:config_entries:flow_handlers"

    async def get(self, request):
        """List available flow handlers."""
        hass = request.app["hass"]
        return self.json(await async_get_config_flows(hass))


class OptionManagerFlowIndexView(FlowManagerIndexView):
    """View to create option flows."""

    url = "/api/config/config_entries/options/flow"
    name = "api:config:config_entries:option:flow"

    # pylint: disable=arguments-differ
    async def post(self, request):
        """Handle a POST request.

        handler in request is entry_id.
        """
        if not request["hass_user"].is_admin:
            raise Unauthorized(perm_category=CAT_CONFIG_ENTRIES, permission=POLICY_EDIT)

        # pylint: disable=no-value-for-parameter
        return await super().post(request)


class OptionManagerFlowResourceView(FlowManagerResourceView):
    """View to interact with the option flow manager."""

    url = "/api/config/config_entries/options/flow/{flow_id}"
    name = "api:config:config_entries:options:flow:resource"

    async def get(self, request, flow_id):
        """Get the current state of a data_entry_flow."""
        if not request["hass_user"].is_admin:
            raise Unauthorized(perm_category=CAT_CONFIG_ENTRIES, permission=POLICY_EDIT)

        return await super().get(request, flow_id)

    # pylint: disable=arguments-differ
    async def post(self, request, flow_id):
        """Handle a POST request."""
        if not request["hass_user"].is_admin:
            raise Unauthorized(perm_category=CAT_CONFIG_ENTRIES, permission=POLICY_EDIT)

        # pylint: disable=no-value-for-parameter
        return await super().post(request, flow_id)


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "config_entries/flow/progress"})
def config_entries_progress(hass, connection, msg):
    """List flows that are in progress but not started by a user.

    Example of a non-user initiated flow is a discovered Hue hub that
    requires user interaction to finish setup.
    """
    connection.send_result(
        msg["id"],
        [
            flw
            for flw in hass.config_entries.flow.async_progress()
            if flw["context"]["source"] != config_entries.SOURCE_USER
        ],
    )


def send_entry_not_found(
    connection: websocket_api.ActiveConnection, msg_id: int
) -> None:
    """Send Config entry not found error."""
    connection.send_error(
        msg_id, websocket_api.const.ERR_NOT_FOUND, "Config entry not found"
    )


def get_entry(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    entry_id: str,
    msg_id: int,
) -> config_entries.ConfigEntry | None:
    """Get entry, send error message if it doesn't exist."""
    if (entry := hass.config_entries.async_get_entry(entry_id)) is None:
        send_entry_not_found(connection, msg_id)
    return entry


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "config_entries/update",
        "entry_id": str,
        vol.Optional("title"): str,
        vol.Optional("pref_disable_new_entities"): bool,
        vol.Optional("pref_disable_polling"): bool,
    }
)
@websocket_api.async_response
async def config_entry_update(hass, connection, msg):
    """Update config entry."""
    changes = dict(msg)
    changes.pop("id")
    changes.pop("type")
    changes.pop("entry_id")

    entry = get_entry(hass, connection, msg["entry_id"], msg["id"])
    if entry is None:
        return

    old_disable_polling = entry.pref_disable_polling

    hass.config_entries.async_update_entry(entry, **changes)

    result = {
        "config_entry": entry_json(entry),
        "require_restart": False,
    }

    if (
        old_disable_polling != entry.pref_disable_polling
        and entry.state is config_entries.ConfigEntryState.LOADED
    ):
        if not await hass.config_entries.async_reload(entry.entry_id):
            result["require_restart"] = (
                entry.state is config_entries.ConfigEntryState.FAILED_UNLOAD
            )

    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "config_entries/disable",
        "entry_id": str,
        # We only allow setting disabled_by user via API.
        # No Enum support like this in voluptuous, use .value
        "disabled_by": vol.Any(config_entries.ConfigEntryDisabler.USER.value, None),
    }
)
@websocket_api.async_response
async def config_entry_disable(hass, connection, msg):
    """Disable config entry."""
    if (disabled_by := msg["disabled_by"]) is not None:
        disabled_by = config_entries.ConfigEntryDisabler(disabled_by)

    result = False
    try:
        result = await hass.config_entries.async_set_disabled_by(
            msg["entry_id"], disabled_by
        )
    except config_entries.OperationNotAllowed:
        # Failed to unload the config entry
        pass
    except config_entries.UnknownEntry:
        send_entry_not_found(connection, msg["id"])
        return

    result = {"require_restart": not result}

    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {"type": "config_entries/ignore_flow", "flow_id": str, "title": str}
)
@websocket_api.async_response
async def ignore_config_flow(hass, connection, msg):
    """Ignore a config flow."""
    flow = next(
        (
            flw
            for flw in hass.config_entries.flow.async_progress()
            if flw["flow_id"] == msg["flow_id"]
        ),
        None,
    )

    if flow is None:
        send_entry_not_found(connection, msg["id"])
        return

    if "unique_id" not in flow["context"]:
        connection.send_error(
            msg["id"], "no_unique_id", "Specified flow has no unique ID."
        )
        return

    await hass.config_entries.flow.async_init(
        flow["handler"],
        context={"source": config_entries.SOURCE_IGNORE},
        data={"unique_id": flow["context"]["unique_id"], "title": msg["title"]},
    )
    connection.send_result(msg["id"])


@callback
def entry_json(entry: config_entries.ConfigEntry) -> dict:
    """Return JSON value of a config entry."""
    handler = config_entries.HANDLERS.get(entry.domain)
    # work out if handler has support for options flow
    supports_options = handler is not None and handler.async_supports_options_flow(
        entry
    )

    return {
        "entry_id": entry.entry_id,
        "domain": entry.domain,
        "title": entry.title,
        "source": entry.source,
        "state": entry.state.value,
        "supports_options": supports_options,
        "supports_remove_device": entry.supports_remove_device,
        "supports_unload": entry.supports_unload,
        "pref_disable_new_entities": entry.pref_disable_new_entities,
        "pref_disable_polling": entry.pref_disable_polling,
        "disabled_by": entry.disabled_by,
        "reason": entry.reason,
    }
