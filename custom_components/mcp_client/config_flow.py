"""Config flow for MCP Client integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

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


def _tools_selector(tool_names: list[str]) -> SelectSelector:
    """Build a multi-select selector for MCP tools."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=name, label=name) for name in tool_names
            ],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


class MCPClientConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for MCP Client."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._gateway_url: str = ""
        self._auth_token: str = ""
        self._discovered_tools: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: gateway connection."""
        errors = {}

        if user_input is not None:
            self._gateway_url = user_input[CONF_GATEWAY_URL].rstrip("/")
            self._auth_token = user_input.get(CONF_AUTH_TOKEN, "")

            try:
                transport = StreamableHTTPTransport(
                    url=self._gateway_url,
                    auth_token=self._auth_token or None,
                )
                await transport.connect()
                tools = await transport.list_tools()
                await transport.disconnect()

                self._discovered_tools = [t["name"] for t in tools]

                if not self._discovered_tools:
                    errors["base"] = "no_tools_found"
                else:
                    return await self.async_step_tools()

            except aiohttp.ClientConnectionError:
                errors["base"] = "cannot_connect"
            except aiohttp.ClientResponseError as err:
                if err.status == 401:
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during MCP connection")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GATEWAY_URL): str,
                    vol.Optional(CONF_AUTH_TOKEN): str,
                }
            ),
            errors=errors,
        )

    async def async_step_tools(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle tool selection step."""
        if user_input is not None:
            selected_tools = user_input.get(CONF_ALLOWED_TOOLS, [])

            await self.async_set_unique_id(self._gateway_url)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"MCP Gateway ({self._gateway_url})",
                data={
                    CONF_GATEWAY_URL: self._gateway_url,
                    CONF_AUTH_TOKEN: self._auth_token,
                },
                options={
                    CONF_ALLOWED_TOOLS: selected_tools,
                    CONF_TIMEOUT_CONNECTION: DEFAULT_TIMEOUT_CONNECTION,
                    CONF_TIMEOUT_EXECUTION: DEFAULT_TIMEOUT_EXECUTION,
                },
            )

        return self.async_show_form(
            step_id="tools",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ALLOWED_TOOLS,
                        default=list(self._discovered_tools),
                    ): _tools_selector(self._discovered_tools),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> MCPClientOptionsFlow:
        """Return options flow handler."""
        return MCPClientOptionsFlow()


class MCPClientOptionsFlow(OptionsFlow):
    """Handle options for MCP Client."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage MCP Client options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        coordinator = self.config_entry.runtime_data
        current_tools = [t["name"] for t in coordinator.tools] if coordinator else []

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ALLOWED_TOOLS,
                        default=self.config_entry.options.get(
                            CONF_ALLOWED_TOOLS, current_tools
                        ),
                    ): _tools_selector(current_tools),
                    vol.Optional(
                        CONF_TIMEOUT_CONNECTION,
                        default=self.config_entry.options.get(
                            CONF_TIMEOUT_CONNECTION, DEFAULT_TIMEOUT_CONNECTION
                        ),
                    ): vol.All(int, vol.Range(min=5, max=60)),
                    vol.Optional(
                        CONF_TIMEOUT_EXECUTION,
                        default=self.config_entry.options.get(
                            CONF_TIMEOUT_EXECUTION, DEFAULT_TIMEOUT_EXECUTION
                        ),
                    ): vol.All(int, vol.Range(min=10, max=120)),
                }
            ),
        )
