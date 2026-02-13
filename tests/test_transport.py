"""Tests for MCP Client transport layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.mcp_client.transport import StreamableHTTPTransport


@pytest.mark.asyncio
async def test_connect() -> None:
    """Test connection setup."""
    transport = StreamableHTTPTransport(url="http://localhost:8080/mcp")

    await transport.connect()

    assert transport._session is not None
    assert not transport._session.closed


@pytest.mark.asyncio
async def test_disconnect() -> None:
    """Test disconnection."""
    transport = StreamableHTTPTransport(url="http://localhost:8080/mcp")

    await transport.connect()
    await transport.disconnect()

    assert transport._session is not None
    assert transport._session.closed


@pytest.mark.asyncio
async def test_list_tools() -> None:
    """Test listing tools from gateway."""
    test_tools = [{"name": "test_tool", "description": "A test tool"}]

    mock_response = MagicMock()
    mock_response.raise_for_status = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={"jsonrpc": "2.0", "result": {"tools": test_tools}}
    )

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value = mock_response

        transport = StreamableHTTPTransport(url="http://localhost:8080/mcp")
        await transport.connect()
        tools = await transport.list_tools()

        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"


@pytest.mark.asyncio
async def test_call_tool() -> None:
    """Test calling a tool."""
    test_result = {"content": [{"type": "text", "text": "Tool executed successfully"}]}

    mock_response = MagicMock()
    mock_response.raise_for_status = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={"jsonrpc": "2.0", "result": test_result}
    )

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value = mock_response

        transport = StreamableHTTPTransport(url="http://localhost:8080/mcp")
        await transport.connect()
        result = await transport.call_tool("test_tool", {"arg": "value"})

        assert result == test_result
