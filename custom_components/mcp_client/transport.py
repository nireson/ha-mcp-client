"""Streamable HTTP transport for MCP Gateway."""

from __future__ import annotations

import itertools
import json
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)


class MCPTransportError(Exception):
    """Error raised when the MCP transport encounters a protocol-level failure."""


class StreamableHTTPTransport:
    """Transport layer for MCP Gateway using Streamable HTTP."""

    def __init__(
        self,
        url: str,
        auth_token: str | None = None,
        timeout_connection: int = 30,
        timeout_execution: int = 60,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize transport."""
        self._url = url.rstrip("/")
        self._auth_token = auth_token
        self._timeout_connection = timeout_connection
        self._timeout_execution = timeout_execution
        self._external_session = session
        self._session: aiohttp.ClientSession | None = None
        self._session_id: str | None = None
        self._id_counter = itertools.count(1)

    async def connect(self) -> None:
        """Connect to the gateway and initialize the MCP session."""
        self._session = self._external_session or aiohttp.ClientSession()

        # Step 1: Send initialize request
        result, headers = await self._raw_request(
            {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "ha-mcp-client",
                        "version": "1.0.0",
                    },
                },
                "id": next(self._id_counter),
            }
        )

        self._session_id = headers.get("Mcp-Session-Id")
        _LOGGER.debug("MCP session initialized: %s", self._session_id)

        # Step 2: Send initialized notification
        await self._raw_request(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            expect_response=False,
        )

    async def disconnect(self) -> None:
        """Disconnect from the gateway."""
        if self._session and not self._session.closed and not self._external_session:
            await self._session.close()
        self._session = None
        self._session_id = None

    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    async def _raw_request(
        self,
        payload: dict,
        *,
        expect_response: bool = True,
        timeout_override: int | None = None,
    ) -> tuple[dict, dict]:
        """Make a request and parse SSE response."""
        if not self._session:
            raise RuntimeError("Not connected")

        total = timeout_override or self._timeout_connection
        timeout = aiohttp.ClientTimeout(total=total)
        async with self._session.post(
            self._url,
            json=payload,
            headers=self._build_headers(),
            timeout=timeout,
        ) as response:
            response.raise_for_status()

            if not expect_response:
                return {}, dict(response.headers)

            content_type = response.headers.get("Content-Type", "")

            if "text/event-stream" in content_type:
                return await self._parse_sse(response), dict(response.headers)

            return await response.json(), dict(response.headers)

    @staticmethod
    async def _parse_sse(response: aiohttp.ClientResponse) -> dict:
        """Parse a Server-Sent Events response, returning the first event's data."""
        data_lines: list[str] = []
        async for line in response.content:
            decoded = line.decode("utf-8").strip()
            if decoded.startswith("data: "):
                data_lines.append(decoded[6:])
            elif not decoded and data_lines:
                # Empty line signals end of an SSE event
                return json.loads("\n".join(data_lines))
        # Stream ended — flush any remaining buffered data lines
        if data_lines:
            return json.loads("\n".join(data_lines))
        raise MCPTransportError("SSE stream ended without any data")

    async def _request(
        self, payload: dict, *, timeout_override: int | None = None
    ) -> dict:
        """Make a request to the gateway and return the result."""
        result, _ = await self._raw_request(
            payload, timeout_override=timeout_override
        )
        if "error" in result:
            err = result["error"]
            raise MCPTransportError(
                f"JSON-RPC error {err.get('code')}: {err.get('message')}"
            )
        return result

    async def list_tools(self) -> list[dict]:
        """List available tools from the gateway."""
        result = await self._request(
            {"jsonrpc": "2.0", "method": "tools/list", "id": next(self._id_counter)}
        )
        return result.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call an MCP tool."""
        result = await self._request(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
                "id": next(self._id_counter),
            },
            timeout_override=self._timeout_execution,
        )
        return result.get("result", {})
