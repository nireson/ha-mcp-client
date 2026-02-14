"""Streamable HTTP transport for MCP Gateway."""

from __future__ import annotations

import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)


class StreamableHTTPTransport:
    """Transport layer for MCP Gateway using Streamable HTTP."""

    def __init__(self, url: str, auth_token: str | None = None) -> None:
        """Initialize transport."""
        self._url = url.rstrip("/")
        self._auth_token = auth_token
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        """Connect to the gateway."""
        self._session = aiohttp.ClientSession()

    async def disconnect(self) -> None:
        """Disconnect from the gateway."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(self, payload: dict) -> dict:
        """Make a request to the gateway."""
        if not self._session:
            raise RuntimeError("Not connected")

        url = self._url
        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        async with self._session.post(
            url, json=payload, headers=headers, timeout=10
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def list_tools(self) -> list[dict]:
        """List available tools from the gateway."""
        result = await self._request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
        )
        return result.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call an MCP tool."""
        result = await self._request(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
                "id": 2,
            },
        )
        return result.get("result", {})
