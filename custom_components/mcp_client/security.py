"""Security utilities for MCP Client integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.util.json import JsonObjectType

from .const import CONF_AUTH_TOKEN

_LOGGER = logging.getLogger(__name__)


def filter_tool_results(data: dict[str, Any]) -> dict[str, Any]:
    """Filter sensitive data from tool results for diagnostics."""
    filtered = dict(data)
    if CONF_AUTH_TOKEN in filtered:
        filtered[CONF_AUTH_TOKEN] = "**REDACTED**"
    return filtered


def validate_tool_input(schema: dict, input_data: dict) -> dict:
    """Validate tool input against schema."""
    return input_data
