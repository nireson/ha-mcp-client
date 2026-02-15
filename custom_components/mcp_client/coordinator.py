"""Coordinator for MCP Gateway connection."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ALLOWED_TOOLS,
    CONF_AUTH_TOKEN,
    CONF_GATEWAY_URL,
    CONF_TIMEOUT_CONNECTION,
    CONF_TIMEOUT_EXECUTION,
    DEFAULT_TIMEOUT_CONNECTION,
    DEFAULT_TIMEOUT_EXECUTION,
    DOMAIN,
)
from .transport import StreamableHTTPTransport

_LOGGER = logging.getLogger(__name__)


class MCPGatewayCoordinator(DataUpdateCoordinator[None]):
    """Coordinator for MCP Gateway connection and tool management."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.entry_id}",
            update_interval=timedelta(minutes=5),
        )
        self._hass = hass
        self._entry = entry
        self._transport: StreamableHTTPTransport | None = None
        self._tools: list[dict] = []
        self._gateway_url = entry.data[CONF_GATEWAY_URL]
        self._auth_token = entry.data.get(CONF_AUTH_TOKEN, "")

    async def async_setup(self) -> None:
        """Set up the coordinator and connect to the gateway."""
        session = async_get_clientsession(self._hass)
        self._transport = StreamableHTTPTransport(
            url=self._gateway_url,
            auth_token=self._auth_token or None,
            timeout_connection=self._entry.options.get(
                CONF_TIMEOUT_CONNECTION, DEFAULT_TIMEOUT_CONNECTION
            ),
            timeout_execution=self._entry.options.get(
                CONF_TIMEOUT_EXECUTION, DEFAULT_TIMEOUT_EXECUTION
            ),
            session=session,
        )
        await self._transport.connect()

    async def async_disconnect(self) -> None:
        """Disconnect from the gateway."""
        if self._transport:
            await self._transport.disconnect()

    async def _async_update_data(self) -> None:
        """Fetch data from the gateway (refresh tools)."""
        if not self._transport:
            raise UpdateFailed("Transport not initialized")
        try:
            tools = await self._transport.list_tools()
            self._tools = self._filter_tools(tools)
        except Exception as err:
            raise UpdateFailed(f"Failed to update gateway data: {err}") from err

    def _filter_tools(self, tools: list[dict]) -> list[dict]:
        """Filter tools based on configuration."""
        allowed = self._entry.options.get(CONF_ALLOWED_TOOLS, [])
        if not allowed:
            return tools
        return [t for t in tools if t["name"] in allowed]

    @property
    def tools(self) -> list[dict]:
        """Return the list of available tools."""
        return self._tools

    async def async_call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool via the gateway."""
        if not self._transport:
            raise HomeAssistantError("Transport not initialized")
        try:
            return await self._transport.call_tool(tool_name, arguments)
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(
                f"Error calling tool {tool_name}: {err}"
            ) from err
