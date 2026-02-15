"""LLM API registration for MCP tools."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN
from .coordinator import MCPGatewayCoordinator

_LOGGER = logging.getLogger(__name__)


class MCPToolsAPI(llm.API):
    """Expose Docker MCP Gateway tools to HA conversation agents."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: MCPGatewayCoordinator,
    ) -> None:
        """Initialize the MCP Tools API."""
        super().__init__(
            hass=hass,
            id=f"{DOMAIN}-{entry.entry_id}",
            name=f"MCP Tools ({entry.title})",
        )
        self._entry = entry
        self._coordinator = coordinator

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return API instance with current MCP tools."""
        tools = [
            MCPTool(tool_schema, self._coordinator)
            for tool_schema in self._coordinator.tools
        ]

        return llm.APIInstance(
            api=self,
            api_prompt=(
                "You have access to external tools provided by an MCP server. "
                "Use these tools when the user's request matches their purpose. "
                "Tool results should be incorporated into your natural language response."
            ),
            llm_context=llm_context,
            tools=tools,
        )


class MCPTool(llm.Tool):
    """A single MCP tool wrapped as an HA LLM Tool."""

    def __init__(
        self,
        mcp_schema: dict[str, Any],
        coordinator: MCPGatewayCoordinator,
    ) -> None:
        """Initialize from MCP tool schema."""
        self.name = mcp_schema["name"]
        self.description = mcp_schema.get("description", "")
        self.parameters = self._build_vol_schema(mcp_schema.get("inputSchema", {}))
        self._coordinator = coordinator

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Execute the MCP tool via the gateway."""
        _LOGGER.debug(
            "Calling MCP tool %s with args: %s",
            tool_input.tool_name,
            tool_input.tool_args,
        )

        try:
            result = await self._coordinator.async_call_tool(
                tool_input.tool_name, tool_input.tool_args
            )
        except Exception as err:
            raise HomeAssistantError(
                f"MCP tool '{tool_input.tool_name}' failed: {err}"
            ) from err

        return self._extract_result(result)

    @staticmethod
    def _extract_result(result: dict) -> JsonObjectType:
        """Extract usable content from MCP tool result."""
        content_parts = result.get("content", [])
        text_parts = [
            part["text"] for part in content_parts if part.get("type") == "text"
        ]
        return {"result": "\n".join(text_parts) if text_parts else str(result)}

    @staticmethod
    def _build_vol_schema(json_schema: dict) -> vol.Schema:
        """Convert JSON Schema from MCP tool to voluptuous schema."""
        if not json_schema or "properties" not in json_schema:
            return vol.Schema({})

        schema_dict = {}
        required = set(json_schema.get("required", []))
        properties = json_schema.get("properties", {})

        for prop_name, prop_def in properties.items():
            python_type = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict,
            }.get(prop_def.get("type", "string"), str)

            if prop_name in required:
                key = vol.Required(prop_name)
            else:
                key = vol.Optional(prop_name)

            if "description" in prop_def:
                key = (
                    vol.Required(prop_name, description=prop_def["description"])
                    if prop_name in required
                    else vol.Optional(prop_name, description=prop_def["description"])
                )

            schema_dict[key] = python_type

        return vol.Schema(schema_dict)
