"""Config flow for KNX."""
from __future__ import annotations

from typing import Any, Final

import voluptuous as vol
from xknx import XKNX
from xknx.io import DEFAULT_MCAST_GRP, DEFAULT_MCAST_PORT
from xknx.io.gateway_scanner import GatewayDescriptor, GatewayScanner

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_KNX_AUTOMATIC,
    CONF_KNX_CONNECTION_TYPE,
    CONF_KNX_INDIVIDUAL_ADDRESS,
    CONF_KNX_INITIAL_CONNECTION_TYPES,
    CONF_KNX_ROUTING,
    CONF_KNX_TUNNELING,
    CONF_KNX_TUNNELING_TCP,
    DOMAIN,
)
from .schema import ConnectionSchema

CONF_KNX_GATEWAY: Final = "gateway"
CONF_MAX_RATE_LIMIT: Final = 60
CONF_DEFAULT_LOCAL_IP: Final = "0.0.0.0"

DEFAULT_ENTRY_DATA: Final = {
    ConnectionSchema.CONF_KNX_STATE_UPDATER: ConnectionSchema.CONF_KNX_DEFAULT_STATE_UPDATER,
    ConnectionSchema.CONF_KNX_RATE_LIMIT: ConnectionSchema.CONF_KNX_DEFAULT_RATE_LIMIT,
    CONF_KNX_INDIVIDUAL_ADDRESS: XKNX.DEFAULT_ADDRESS,
    ConnectionSchema.CONF_KNX_MCAST_GRP: DEFAULT_MCAST_GRP,
    ConnectionSchema.CONF_KNX_MCAST_PORT: DEFAULT_MCAST_PORT,
}

CONF_KNX_TUNNELING_TYPE: Final = "tunneling_type"
CONF_KNX_LABEL_TUNNELING_TCP: Final = "TCP"
CONF_KNX_LABEL_TUNNELING_UDP: Final = "UDP"
CONF_KNX_LABEL_TUNNELING_UDP_ROUTE_BACK: Final = "UDP with route back / NAT mode"


class FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a KNX config flow."""

    VERSION = 1

    _found_tunnels: list[GatewayDescriptor]
    _selected_tunnel: GatewayDescriptor | None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KNXOptionsFlowHandler:
        """Get the options flow for this handler."""
        return KNXOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle a flow initialized by the user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        self._found_tunnels = []
        self._selected_tunnel = None
        return await self.async_step_type()

    async def async_step_type(self, user_input: dict | None = None) -> FlowResult:
        """Handle connection type configuration."""
        if user_input is not None:
            connection_type = user_input[CONF_KNX_CONNECTION_TYPE]
            if connection_type == CONF_KNX_AUTOMATIC:
                return self.async_create_entry(
                    title=CONF_KNX_AUTOMATIC.capitalize(),
                    data={**DEFAULT_ENTRY_DATA, **user_input},
                )

            if connection_type == CONF_KNX_ROUTING:
                return await self.async_step_routing()

            if connection_type == CONF_KNX_TUNNELING and self._found_tunnels:
                return await self.async_step_tunnel()

            return await self.async_step_manual_tunnel()

        errors: dict = {}
        supported_connection_types = CONF_KNX_INITIAL_CONNECTION_TYPES.copy()
        fields = {}
        gateways = await scan_for_gateways()

        if gateways:
            # add automatic only if a gateway responded
            supported_connection_types.insert(0, CONF_KNX_AUTOMATIC)
            self._found_tunnels = [
                gateway for gateway in gateways if gateway.supports_tunnelling
            ]

        fields = {
            vol.Required(CONF_KNX_CONNECTION_TYPE): vol.In(supported_connection_types)
        }

        return self.async_show_form(
            step_id="type", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_tunnel(self, user_input: dict | None = None) -> FlowResult:
        """Select a tunnel from a list. Will be skipped if the gateway scan was unsuccessful or if only one gateway was found."""
        if user_input is not None:
            self._selected_tunnel = next(
                tunnel
                for tunnel in self._found_tunnels
                if user_input[CONF_KNX_GATEWAY] == str(tunnel)
            )
            return await self.async_step_manual_tunnel()

        #  skip this step if the user has only one unique gateway.
        if len(self._found_tunnels) == 1:
            self._selected_tunnel = self._found_tunnels[0]
            return await self.async_step_manual_tunnel()

        errors: dict = {}
        tunnels_repr = {str(tunnel) for tunnel in self._found_tunnels}
        fields = {vol.Required(CONF_KNX_GATEWAY): vol.In(tunnels_repr)}

        return self.async_show_form(
            step_id="tunnel", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_manual_tunnel(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Manually configure tunnel connection parameters. Fields default to preselected gateway if one was found."""
        if user_input is not None:
            connection_type = user_input[CONF_KNX_TUNNELING_TYPE]
            return self.async_create_entry(
                title=f"{CONF_KNX_TUNNELING.capitalize()} @ {user_input[CONF_HOST]}",
                data={
                    **DEFAULT_ENTRY_DATA,
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_KNX_INDIVIDUAL_ADDRESS: user_input[
                        CONF_KNX_INDIVIDUAL_ADDRESS
                    ],
                    ConnectionSchema.CONF_KNX_ROUTE_BACK: (
                        connection_type == CONF_KNX_LABEL_TUNNELING_UDP_ROUTE_BACK
                    ),
                    ConnectionSchema.CONF_KNX_LOCAL_IP: user_input.get(
                        ConnectionSchema.CONF_KNX_LOCAL_IP
                    ),
                    CONF_KNX_CONNECTION_TYPE: (
                        CONF_KNX_TUNNELING_TCP
                        if connection_type == CONF_KNX_LABEL_TUNNELING_TCP
                        else CONF_KNX_TUNNELING
                    ),
                },
            )

        errors: dict = {}
        connection_methods: list[str] = [
            CONF_KNX_LABEL_TUNNELING_TCP,
            CONF_KNX_LABEL_TUNNELING_UDP,
            CONF_KNX_LABEL_TUNNELING_UDP_ROUTE_BACK,
        ]
        ip_address = ""
        port = DEFAULT_MCAST_PORT
        if self._selected_tunnel is not None:
            ip_address = self._selected_tunnel.ip_addr
            port = self._selected_tunnel.port
            if not self._selected_tunnel.supports_tunnelling_tcp:
                connection_methods.remove(CONF_KNX_LABEL_TUNNELING_TCP)

        fields = {
            vol.Required(CONF_KNX_TUNNELING_TYPE): vol.In(connection_methods),
            vol.Required(CONF_HOST, default=ip_address): str,
            vol.Required(CONF_PORT, default=port): cv.port,
            vol.Required(
                CONF_KNX_INDIVIDUAL_ADDRESS, default=XKNX.DEFAULT_ADDRESS
            ): str,
        }

        if self.show_advanced_options:
            fields[vol.Optional(ConnectionSchema.CONF_KNX_LOCAL_IP)] = str

        return self.async_show_form(
            step_id="manual_tunnel", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_routing(self, user_input: dict | None = None) -> FlowResult:
        """Routing setup."""
        if user_input is not None:
            return self.async_create_entry(
                title=CONF_KNX_ROUTING.capitalize(),
                data={
                    **DEFAULT_ENTRY_DATA,
                    ConnectionSchema.CONF_KNX_MCAST_GRP: user_input[
                        ConnectionSchema.CONF_KNX_MCAST_GRP
                    ],
                    ConnectionSchema.CONF_KNX_MCAST_PORT: user_input[
                        ConnectionSchema.CONF_KNX_MCAST_PORT
                    ],
                    CONF_KNX_INDIVIDUAL_ADDRESS: user_input[
                        CONF_KNX_INDIVIDUAL_ADDRESS
                    ],
                    ConnectionSchema.CONF_KNX_LOCAL_IP: user_input.get(
                        ConnectionSchema.CONF_KNX_LOCAL_IP
                    ),
                    CONF_KNX_CONNECTION_TYPE: CONF_KNX_ROUTING,
                },
            )

        errors: dict = {}
        fields = {
            vol.Required(
                CONF_KNX_INDIVIDUAL_ADDRESS, default=XKNX.DEFAULT_ADDRESS
            ): str,
            vol.Required(
                ConnectionSchema.CONF_KNX_MCAST_GRP, default=DEFAULT_MCAST_GRP
            ): str,
            vol.Required(
                ConnectionSchema.CONF_KNX_MCAST_PORT, default=DEFAULT_MCAST_PORT
            ): cv.port,
        }

        if self.show_advanced_options:
            fields[vol.Optional(ConnectionSchema.CONF_KNX_LOCAL_IP)] = str

        return self.async_show_form(
            step_id="routing", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_import(self, config: dict | None = None) -> FlowResult:
        """Import a config entry.

        Performs a one time import of the YAML configuration and creates a config entry based on it
        if not already done before.
        """
        if self._async_current_entries() or not config:
            return self.async_abort(reason="single_instance_allowed")

        data = {
            ConnectionSchema.CONF_KNX_RATE_LIMIT: min(
                config[ConnectionSchema.CONF_KNX_RATE_LIMIT], CONF_MAX_RATE_LIMIT
            ),
            ConnectionSchema.CONF_KNX_STATE_UPDATER: config[
                ConnectionSchema.CONF_KNX_STATE_UPDATER
            ],
            ConnectionSchema.CONF_KNX_MCAST_GRP: config[
                ConnectionSchema.CONF_KNX_MCAST_GRP
            ],
            ConnectionSchema.CONF_KNX_MCAST_PORT: config[
                ConnectionSchema.CONF_KNX_MCAST_PORT
            ],
            CONF_KNX_INDIVIDUAL_ADDRESS: config[CONF_KNX_INDIVIDUAL_ADDRESS],
        }

        if CONF_KNX_TUNNELING in config:
            return self.async_create_entry(
                title=f"{CONF_KNX_TUNNELING.capitalize()} @ {config[CONF_KNX_TUNNELING][CONF_HOST]}",
                data={
                    **DEFAULT_ENTRY_DATA,
                    CONF_HOST: config[CONF_KNX_TUNNELING][CONF_HOST],
                    CONF_PORT: config[CONF_KNX_TUNNELING][CONF_PORT],
                    ConnectionSchema.CONF_KNX_LOCAL_IP: config[CONF_KNX_TUNNELING].get(
                        ConnectionSchema.CONF_KNX_LOCAL_IP
                    ),
                    ConnectionSchema.CONF_KNX_ROUTE_BACK: config[CONF_KNX_TUNNELING][
                        ConnectionSchema.CONF_KNX_ROUTE_BACK
                    ],
                    CONF_KNX_CONNECTION_TYPE: CONF_KNX_TUNNELING,
                    **data,
                },
            )

        if CONF_KNX_ROUTING in config:
            return self.async_create_entry(
                title=CONF_KNX_ROUTING.capitalize(),
                data={
                    **DEFAULT_ENTRY_DATA,
                    CONF_KNX_CONNECTION_TYPE: CONF_KNX_ROUTING,
                    **data,
                },
            )

        return self.async_create_entry(
            title=CONF_KNX_AUTOMATIC.capitalize(),
            data={
                **DEFAULT_ENTRY_DATA,
                CONF_KNX_CONNECTION_TYPE: CONF_KNX_AUTOMATIC,
                **data,
            },
        )


class KNXOptionsFlowHandler(OptionsFlow):
    """Handle KNX options."""

    general_settings: dict
    current_config: dict

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize KNX options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage KNX options."""
        if user_input is not None:
            self.general_settings = user_input
            return await self.async_step_tunnel()

        supported_connection_types = [
            CONF_KNX_AUTOMATIC,
            CONF_KNX_TUNNELING,
            CONF_KNX_ROUTING,
        ]
        self.current_config = self.config_entry.data  # type: ignore[assignment]

        data_schema = {
            vol.Required(
                CONF_KNX_CONNECTION_TYPE,
                default=(
                    CONF_KNX_TUNNELING
                    if self.current_config.get(CONF_KNX_CONNECTION_TYPE)
                    == CONF_KNX_TUNNELING_TCP
                    else self.current_config.get(CONF_KNX_CONNECTION_TYPE)
                ),
            ): vol.In(supported_connection_types),
            vol.Required(
                CONF_KNX_INDIVIDUAL_ADDRESS,
                default=self.current_config[CONF_KNX_INDIVIDUAL_ADDRESS],
            ): str,
            vol.Required(
                ConnectionSchema.CONF_KNX_MCAST_GRP,
                default=self.current_config.get(
                    ConnectionSchema.CONF_KNX_MCAST_GRP, DEFAULT_MCAST_GRP
                ),
            ): str,
            vol.Required(
                ConnectionSchema.CONF_KNX_MCAST_PORT,
                default=self.current_config.get(
                    ConnectionSchema.CONF_KNX_MCAST_PORT, DEFAULT_MCAST_PORT
                ),
            ): cv.port,
        }

        if self.show_advanced_options:
            local_ip = (
                self.current_config.get(ConnectionSchema.CONF_KNX_LOCAL_IP)
                if self.current_config.get(ConnectionSchema.CONF_KNX_LOCAL_IP)
                is not None
                else CONF_DEFAULT_LOCAL_IP
            )
            data_schema[
                vol.Required(
                    ConnectionSchema.CONF_KNX_LOCAL_IP,
                    default=local_ip,
                )
            ] = str
            data_schema[
                vol.Required(
                    ConnectionSchema.CONF_KNX_STATE_UPDATER,
                    default=self.current_config.get(
                        ConnectionSchema.CONF_KNX_STATE_UPDATER,
                        ConnectionSchema.CONF_KNX_DEFAULT_STATE_UPDATER,
                    ),
                )
            ] = bool
            data_schema[
                vol.Required(
                    ConnectionSchema.CONF_KNX_RATE_LIMIT,
                    default=self.current_config.get(
                        ConnectionSchema.CONF_KNX_RATE_LIMIT,
                        ConnectionSchema.CONF_KNX_DEFAULT_RATE_LIMIT,
                    ),
                )
            ] = vol.All(vol.Coerce(int), vol.Range(min=1, max=CONF_MAX_RATE_LIMIT))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(data_schema),
            last_step=self.current_config.get(CONF_KNX_CONNECTION_TYPE)
            != CONF_KNX_TUNNELING,
        )

    async def async_step_tunnel(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage KNX tunneling options."""
        if (
            self.general_settings.get(CONF_KNX_CONNECTION_TYPE) == CONF_KNX_TUNNELING
            and user_input is None
        ):
            connection_methods: list[str] = [
                CONF_KNX_LABEL_TUNNELING_TCP,
                CONF_KNX_LABEL_TUNNELING_UDP,
                CONF_KNX_LABEL_TUNNELING_UDP_ROUTE_BACK,
            ]
            return self.async_show_form(
                step_id="tunnel",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_KNX_TUNNELING_TYPE,
                            default=get_knx_tunneling_type(self.current_config),
                        ): vol.In(connection_methods),
                        vol.Required(
                            CONF_HOST, default=self.current_config.get(CONF_HOST)
                        ): str,
                        vol.Required(
                            CONF_PORT, default=self.current_config.get(CONF_PORT, 3671)
                        ): cv.port,
                    }
                ),
                last_step=True,
            )

        entry_data = {
            **DEFAULT_ENTRY_DATA,
            **self.general_settings,
            ConnectionSchema.CONF_KNX_LOCAL_IP: self.general_settings.get(
                ConnectionSchema.CONF_KNX_LOCAL_IP
            )
            if self.general_settings.get(ConnectionSchema.CONF_KNX_LOCAL_IP)
            != CONF_DEFAULT_LOCAL_IP
            else None,
            CONF_HOST: self.current_config.get(CONF_HOST, ""),
        }

        if user_input is not None:
            connection_type = user_input[CONF_KNX_TUNNELING_TYPE]
            entry_data = {
                **entry_data,
                CONF_HOST: user_input[CONF_HOST],
                CONF_PORT: user_input[CONF_PORT],
                ConnectionSchema.CONF_KNX_ROUTE_BACK: (
                    connection_type == CONF_KNX_LABEL_TUNNELING_UDP_ROUTE_BACK
                ),
                CONF_KNX_CONNECTION_TYPE: (
                    CONF_KNX_TUNNELING_TCP
                    if connection_type == CONF_KNX_LABEL_TUNNELING_TCP
                    else CONF_KNX_TUNNELING
                ),
            }

        entry_title = str(entry_data[CONF_KNX_CONNECTION_TYPE]).capitalize()
        if entry_data[CONF_KNX_CONNECTION_TYPE] == CONF_KNX_TUNNELING:
            entry_title = f"{CONF_KNX_TUNNELING.capitalize()} @ {entry_data[CONF_HOST]}"
        if entry_data[CONF_KNX_CONNECTION_TYPE] == CONF_KNX_TUNNELING_TCP:
            entry_title = (
                f"{CONF_KNX_TUNNELING.capitalize()} (TCP) @ {entry_data[CONF_HOST]}"
            )

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data=entry_data,
            title=entry_title,
        )

        return self.async_create_entry(title="", data={})


def get_knx_tunneling_type(config_entry_data: dict) -> str:
    """Obtain the knx tunneling type based on the data in the config entry data."""
    connection_type = config_entry_data[CONF_KNX_CONNECTION_TYPE]
    route_back = config_entry_data.get(ConnectionSchema.CONF_KNX_ROUTE_BACK, False)
    if route_back and connection_type == CONF_KNX_TUNNELING:
        return CONF_KNX_LABEL_TUNNELING_UDP_ROUTE_BACK
    if connection_type == CONF_KNX_TUNNELING_TCP:
        return CONF_KNX_LABEL_TUNNELING_TCP

    return CONF_KNX_LABEL_TUNNELING_UDP


async def scan_for_gateways(stop_on_found: int = 0) -> list[GatewayDescriptor]:
    """Scan for gateways within the network."""
    xknx = XKNX()
    gatewayscanner = GatewayScanner(
        xknx, stop_on_found=stop_on_found, timeout_in_seconds=2
    )
    return await gatewayscanner.scan()
