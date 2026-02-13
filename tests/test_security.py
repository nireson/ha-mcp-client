"""Tests for MCP Client security."""

import pytest

from custom_components.mcp_client.security import (
    filter_tool_results,
    validate_tool_input,
)


def test_filter_tool_results_redacts_auth_token() -> None:
    """Test that auth tokens are redacted from results."""
    diagnostic_data = {
        "gateway_url": "http://localhost:8080/mcp",
        "auth_token": "secret123",
        "tools": ["tool1", "tool2"],
    }

    filtered = filter_tool_results(diagnostic_data)

    assert filtered["auth_token"] == "**REDACTED**"
    assert filtered["gateway_url"] == "http://localhost:8080/mcp"


def test_validate_tool_input_valid() -> None:
    """Test validation of valid tool input."""
    schema = {"type": "object", "properties": {"arg": {"type": "string"}}}
    input_data = {"arg": "value"}

    validated = validate_tool_input(schema, input_data)

    assert validated["arg"] == "value"


def test_validate_tool_input_invalid() -> None:
    """Test validation of invalid tool input."""
    schema = {"type": "object", "properties": {"arg": {"type": "string"}}}
    input_data = {"arg": 123}

    with pytest.raises(Exception):
        validate_tool_input(schema, input_data)
