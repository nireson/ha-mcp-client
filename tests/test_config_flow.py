"""Tests for MCP Client config flow."""

from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import RESULT_TYPE_CREATE_ENTRY, RESULT_TYPE_FORM

from custom_components.mcp_client.config_flow import MCPClientConfigFlow


@pytest.mark.asyncio
async def test_step_user_connection_error(hass: HomeAssistant) -> None:
    """Test handling of connection error in user step."""
    result = await hass.config_entries.flow.async_init(
        "mcp_client", context={"source": "user"}
    )

    assert result["type"] == RESULT_TYPE_FORM
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_step_user_cannot_connect(hass: HomeAssistant) -> None:
    """Test handling of cannot connect error."""
    with patch(
        "custom_components.mcp_client.config_flow.StreamableHTTPTransport"
    ) as mock_transport:
        mock_instance = AsyncMock()
        mock_instance.connect.side_effect = aiohttp.ClientConnectionError()
        mock_transport.return_value = mock_instance

        result = await hass.config_entries.flow.async_init(
            "mcp_client", context={"source": "user"}
        )

        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_step_user_valid_connection(hass: HomeAssistant) -> None:
    """Test successful connection and tool discovery."""
    test_tools = [
        {"name": "tool1", "description": "Test tool 1"},
        {"name": "tool2", "description": "Test tool 2"},
    ]

    with patch(
        "custom_components.mcp_client.config_flow.StreamableHTTPTransport"
    ) as mock_transport:
        mock_instance = AsyncMock()
        mock_instance.connect = AsyncMock()
        mock_instance.list_tools = AsyncMock(return_value=test_tools)
        mock_instance.disconnect = AsyncMock()
        mock_transport.return_value = mock_instance

        result = await hass.config_entries.flow.async_init(
            "mcp_client", context={"source": "user"}
        )

        assert result["type"] == RESULT_TYPE_FORM
        assert result["step_id"] == "tools"
