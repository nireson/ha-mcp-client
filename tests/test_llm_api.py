"""Tests for MCP Client LLM API."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import llm

from custom_components.mcp_client.coordinator import MCPGatewayCoordinator
from custom_components.mcp_client.llm_api import MCPTool, MCPToolsAPI


def test_mcp_tools_api_init() -> None:
    """Test MCPToolsAPI initialization."""
    mock_hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.title = "Test Gateway"
    mock_coordinator = MagicMock()

    api = MCPToolsAPI(mock_hass, mock_entry, mock_coordinator)

    assert api.id == "mcp_client-test_entry"
    assert api.name == "MCP Tools (Test Gateway)"


@pytest.mark.asyncio
async def test_mcp_tools_api_get_instance() -> None:
    """Test API instance retrieval."""
    mock_hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.title = "Test Gateway"

    mock_coordinator = MagicMock()
    mock_coordinator.tools = [{"name": "test_tool", "description": "A test tool"}]

    api = MCPToolsAPI(mock_hass, mock_entry, mock_coordinator)

    mock_llm_context = MagicMock()
    instance = await api.async_get_api_instance(mock_llm_context)

    assert instance.api == api
    assert len(instance.tools) == 1
    assert instance.tools[0].name == "test_tool"


def test_mcp_tool_init() -> None:
    """Test MCPTool initialization."""
    mock_coordinator = MagicMock()
    mcp_schema = {
        "name": "test_tool",
        "description": "A test tool",
        "inputSchema": {
            "type": "object",
            "properties": {
                "arg1": {"type": "string", "description": "First argument"},
                "arg2": {"type": "integer", "description": "Second argument"},
            },
            "required": ["arg1"],
        },
    }

    tool = MCPTool(mcp_schema, mock_coordinator)

    assert tool.name == "test_tool"
    assert tool.description == "A test tool"
    assert tool._coordinator == mock_coordinator


@pytest.mark.asyncio
async def test_mcp_tool_async_call() -> None:
    """Test MCPTool async_call."""
    mock_hass = MagicMock()
    mock_llm_context = MagicMock()

    mock_coordinator = MagicMock()
    mock_coordinator.async_call_tool = AsyncMock(
        return_value={"content": [{"type": "text", "text": "Result"}]}
    )

    mcp_schema = {
        "name": "test_tool",
        "description": "A test tool",
        "inputSchema": {"type": "object", "properties": {}},
    }

    tool = MCPTool(mcp_schema, mock_coordinator)

    mock_tool_input = MagicMock()
    mock_tool_input.tool_name = "test_tool"
    mock_tool_input.tool_args = {}

    result = await tool.async_call(mock_hass, mock_tool_input, mock_llm_context)

    assert result == {"result": "Result"}
    mock_coordinator.async_call_tool.assert_awaited_once_with("test_tool", {})
