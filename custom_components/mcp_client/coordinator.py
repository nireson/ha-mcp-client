"""Coordinator for MCP Gateway connection."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_ALLOWED_TOOLS, CONF_AUTH_TOKEN, CONF_GATEWAY_URL, DOMAIN
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
        self._transport = StreamableHTTPTransport(
            url=self._gateway_url,
            auth_token=self._auth_token or None,
        )
        await self._transport.connect()

    async def async_disconnect(self) -> None:
        """Disconnect from the gateway."""
        if self._transport:
            await self._transport.disconnect()

    async def _async_update_data(self) -> None:
        """Fetch data from the gateway (refresh tools)."""
        if not self._transport:
            raise HomeAssistantError("Transport not initialized")
        try:
            tools = await self._transport.list_tools()
            self._tools = self._filter_tools(tools)
        except Exception as err:
            _LOGGER.error("Failed to update gateway data: %s", err)
            raise

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
            result = await self._transport.call_tool(tool_name, arguments)
            return result
        except Exception as err:
            _LOGGER.error("Error calling tool %s: %s", tool_name, err)
            raise
