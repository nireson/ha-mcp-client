# HACS Custom Integration: `mcp_client` for Home Assistant

**Date:** February 13, 2026  
**Status:** Implementation Proposal  
**Target:** Packaged as a HACS-installable custom integration, fully configurable via HA UI

---

## Executive Summary

Yes — this is not only possible, it's the natural packaging for this project. The architecture we've designed maps directly onto HA's custom integration model with zero compromises. The integration:

- Installs via HACS (one click from the HACS storefront or as a custom repository)
- Configures entirely through the HA UI (Settings → Devices & Services → Add Integration)
- Registers MCP tools as an **LLM API** via HA's official `llm.async_register_api()` framework
- Requires no YAML editing, no SSH access, no manual file placement
- Works with any HA conversation agent that supports LLM APIs (Ollama, OpenAI, Anthropic, Google, home-llm, etc.)

The user experience is: install via HACS → add integration → enter gateway URL and token → select which tools to expose → enable the API in your conversation agent → done.

---

## Why a HACS Integration (Not an Add-on)

These are two different things in HA's ecosystem, and the distinction matters:

| | HACS Integration | HA Add-on |
|---|---|---|
| **What it is** | Python code in `custom_components/` | A separate Docker container managed by Supervisor |
| **Runs as** | Part of HA Core's Python process | An independent service alongside HA |
| **Configurable via** | HA UI config flow (Settings → Devices & Services) | Add-on config panel |
| **Can register LLM tools** | Yes — direct access to `llm.async_register_api()` | No — would need a REST/WS bridge |
| **Can extend conversation agents** | Yes — first-class integration | No — runs in a separate container |
| **Installation** | HACS → search → install → restart | Supervisor → Add-on Store → install |
| **Requirements** | Any HA installation method | HA OS or Supervised only |

A **HACS custom integration** is the correct choice because the core value of this project is registering MCP tools with HA's LLM framework. That requires running inside HA's Python process, which only integrations can do. An add-on would need an awkward REST bridge and couldn't directly register tools.

---

## Repository Structure

```
mcp-client-ha/                          ← GitHub repository root
├── custom_components/
│   └── mcp_client/                     ← The actual integration
│       ├── __init__.py                 # Integration setup & teardown
│       ├── manifest.json               # HA integration manifest
│       ├── config_flow.py              # UI configuration flow
│       ├── const.py                    # Constants, defaults
│       ├── coordinator.py              # Gateway connection lifecycle
│       ├── transport.py                # Streamable HTTP MCP client
│       ├── llm_api.py                  # LLM API & Tool registration
│       ├── security.py                 # Validation, filtering, rate limiting
│       ├── strings.json                # UI strings (English)
│       └── translations/
│           └── en.json                 # Translations
├── hacs.json                           # HACS metadata
├── README.md                           # User documentation
├── LICENSE                             # License file
├── tests/                              # Test suite
│   ├── conftest.py
│   ├── test_config_flow.py
│   ├── test_transport.py
│   ├── test_llm_api.py
│   └── test_security.py
└── .github/
    └── workflows/
        ├── validate.yml                # HACS validation action
        ├── tests.yml                   # pytest CI
        └── release.yml                 # GitHub release automation
```

### HACS Metadata

```json
// hacs.json
{
  "name": "MCP Client for Docker Gateway",
  "hacs": "2.0.0",
  "homeassistant": "2025.1.0",
  "render_readme": true,
  "zip_release": true,
  "filename": "mcp_client.zip"
}
```

### Integration Manifest

```json
// custom_components/mcp_client/manifest.json
{
  "domain": "mcp_client",
  "name": "MCP Client (Docker Gateway)",
  "codeowners": ["@your-github-username"],
  "config_flow": true,
  "dependencies": [],
  "documentation": "https://github.com/your-repo/mcp-client-ha",
  "integration_type": "service",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/your-repo/mcp-client-ha/issues",
  "requirements": [],
  "version": "1.0.0"
}
```

Note: **zero external requirements**. The integration uses only `aiohttp` and `voluptuous`, both of which are already bundled with HA Core. This means no pip installs, no dependency conflicts, no version pinning headaches.

---

## Integration Lifecycle

### `__init__.py` — Setup & Teardown

```python
"""MCP Client integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import DOMAIN
from .coordinator import MCPGatewayCoordinator
from .llm_api import MCPToolsAPI

_LOGGER = logging.getLogger(__name__)

type MCPClientConfigEntry = ConfigEntry[MCPGatewayCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: MCPClientConfigEntry
) -> bool:
    """Set up MCP Client from a config entry."""
    coordinator = MCPGatewayCoordinator(hass, entry)

    # Connect to gateway and discover tools
    await coordinator.async_setup()

    # Store coordinator on the config entry for access by other components
    entry.runtime_data = coordinator

    # Start periodic health checks / tool refresh
    await coordinator.async_config_entry_first_refresh()

    # Register our tools as an LLM API so conversation agents can use them
    # This is the critical integration point with HA's LLM framework
    api = MCPToolsAPI(hass, entry, coordinator)
    unreg = llm.async_register_api(hass, api)
    entry.async_on_unload(unreg)

    _LOGGER.info(
        "MCP Client connected to %s — %d tools registered",
        entry.data["gateway_url"],
        len(coordinator.tools),
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MCPClientConfigEntry
) -> bool:
    """Unload MCP Client config entry."""
    # LLM API is auto-unregistered via entry.async_on_unload
    await entry.runtime_data.async_disconnect()
    return True
```

### `llm_api.py` — The LLM Tool Registration Bridge

This is the most important file. It translates MCP tools into HA's `llm.Tool` format and registers them via HA's official `llm.API` framework. Once registered, any conversation agent (Ollama, OpenAI, Anthropic, etc.) can discover and call these tools.

```python
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
    """Expose Docker MCP Gateway tools to HA conversation agents.

    This registers as an LLM API that appears alongside the built-in
    Assist API in conversation agent configuration. Users can enable
    it under Settings → Voice Assistants → [Agent] → Control Home Assistant.
    """

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
    """A single MCP tool wrapped as an HA LLM Tool.

    Translates the MCP tool's JSON Schema into a voluptuous schema
    for HA compatibility, and routes calls to the MCP Gateway.
    """

    def __init__(
        self,
        mcp_schema: dict[str, Any],
        coordinator: MCPGatewayCoordinator,
    ) -> None:
        """Initialize from MCP tool schema."""
        self.name = mcp_schema["name"]
        self.description = mcp_schema.get("description", "")
        self.parameters = self._build_vol_schema(
            mcp_schema.get("inputSchema", {})
        )
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

        # MCP tool results contain a 'content' array with text/image blocks
        # Extract text content for the LLM
        return self._extract_result(result)

    @staticmethod
    def _extract_result(result: dict) -> JsonObjectType:
        """Extract usable content from MCP tool result."""
        content_parts = result.get("content", [])
        text_parts = [
            part["text"]
            for part in content_parts
            if part.get("type") == "text"
        ]
        return {"result": "\n".join(text_parts) if text_parts else str(result)}

    @staticmethod
    def _build_vol_schema(json_schema: dict) -> vol.Schema:
        """Convert JSON Schema from MCP tool to voluptuous schema.

        HA's LLM framework uses voluptuous for parameter validation.
        MCP tools publish JSON Schema. This bridges the two.
        """
        if not json_schema or "properties" not in json_schema:
            return vol.Schema({})

        schema_dict = {}
        required = set(json_schema.get("required", []))
        properties = json_schema.get("properties", {})

        for prop_name, prop_def in properties.items():
            # Map JSON Schema types to Python types
            python_type = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
            }.get(prop_def.get("type", "string"), str)

            if prop_name in required:
                key = vol.Required(prop_name)
            else:
                key = vol.Optional(prop_name)

            # Add description as voluptuous description
            if "description" in prop_def:
                key = key.description  # vol uses this for LLM hints
                key = (
                    vol.Required(prop_name, description=prop_def["description"])
                    if prop_name in required
                    else vol.Optional(prop_name, description=prop_def["description"])
                )

            schema_dict[key] = python_type

        return vol.Schema(schema_dict)
```

### `config_flow.py` — UI Configuration

This provides the full setup experience through Settings → Devices & Services → Add Integration → "MCP Client (Docker Gateway)".

```python
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

from .const import (
    CONF_ALLOWED_TOOLS,
    CONF_BLOCKED_TOOLS,
    CONF_GATEWAY_URL,
    CONF_AUTH_TOKEN,
    CONF_TIMEOUT_CONNECTION,
    CONF_TIMEOUT_EXECUTION,
    CONF_TLS_MODE,
    DEFAULT_TIMEOUT_CONNECTION,
    DEFAULT_TIMEOUT_EXECUTION,
    DOMAIN,
    TLS_HTTP_TRUSTED,
    TLS_VERIFY_FULL,
)
from .transport import StreamableHTTPTransport

_LOGGER = logging.getLogger(__name__)


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

            # Validate connection by attempting tool discovery
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
                    # Proceed to tool selection step
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

        # Determine TLS warning
        description_placeholders = {}

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GATEWAY_URL): str,
                    vol.Optional(CONF_AUTH_TOKEN): str,
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_tools(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle tool selection step."""
        if user_input is not None:
            selected_tools = user_input.get(CONF_ALLOWED_TOOLS, [])

            # Prevent duplicate config entries for the same gateway
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

        # Build multi-select for discovered tools
        tool_options = {
            tool: tool for tool in self._discovered_tools
        }

        return self.async_show_form(
            step_id="tools",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ALLOWED_TOOLS,
                        default=self._discovered_tools,  # All selected by default
                    ): vol.All(
                        vol.Coerce(list),
                        [vol.In(tool_options)],
                    ),
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
    """Handle options for MCP Client (reconfigure tools, timeouts)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage MCP Client options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        # Re-discover tools from gateway for the selection list
        coordinator = self.config_entry.runtime_data
        current_tools = [t["name"] for t in coordinator.tools] if coordinator else []
        tool_options = {tool: tool for tool in current_tools}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ALLOWED_TOOLS,
                        default=self.config_entry.options.get(
                            CONF_ALLOWED_TOOLS, current_tools
                        ),
                    ): vol.All(
                        vol.Coerce(list),
                        [vol.In(tool_options)],
                    ),
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
```

### `strings.json` — UI Strings

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Connect to MCP Gateway",
        "description": "Enter the URL of your Docker MCP Gateway and an optional authentication token.",
        "data": {
          "gateway_url": "Gateway URL",
          "auth_token": "Authentication Token"
        },
        "data_description": {
          "gateway_url": "e.g., http://192.168.1.50:8080/mcp",
          "auth_token": "Bearer token for gateway authentication (leave blank if none)"
        }
      },
      "tools": {
        "title": "Select MCP Tools",
        "description": "Choose which tools to expose to your voice assistant. Deselect any tools you don't want the LLM to use.",
        "data": {
          "allowed_tools": "Available Tools"
        }
      }
    },
    "error": {
      "cannot_connect": "Cannot connect to the MCP Gateway. Verify the URL and that the gateway is running.",
      "invalid_auth": "Authentication failed. Check your token.",
      "no_tools_found": "Connected successfully but no tools were found on the gateway.",
      "unknown": "An unexpected error occurred."
    },
    "abort": {
      "already_configured": "This gateway is already configured."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "MCP Client Options",
        "data": {
          "allowed_tools": "Enabled Tools",
          "timeout_connection": "Connection Timeout (seconds)",
          "timeout_execution": "Tool Execution Timeout (seconds)"
        }
      }
    }
  }
}
```

---

## User Experience Walkthrough

### Installation (One-Time)

```
1. Open HACS in Home Assistant
2. Click "Integrations" tab
3. Click the ⋮ menu → "Custom repositories"
4. Enter: https://github.com/your-repo/mcp-client-ha
   Category: Integration
5. Search for "MCP Client" → Install
6. Restart Home Assistant
```

Once the integration is submitted to the HACS default repository, steps 3-4 are replaced by simply searching for it in the HACS storefront.

### Configuration (Per Gateway)

```
1. Settings → Devices & Services → Add Integration
2. Search "MCP Client (Docker Gateway)"
3. Enter gateway URL: http://192.168.1.50:8080/mcp
4. Enter auth token (if applicable)
5. [Test Connection] → shows discovered tools
6. Select which tools to expose ☑/☐
7. Submit
```

### Enabling for a Conversation Agent

```
1. Settings → Voice Assistants → [Your Assistant]
2. Click gear icon next to your conversation agent (e.g., Ollama)
3. Under "Control Home Assistant", enable:
   - ☑ Assist  (HA native tools)
   - ☑ MCP Tools (MCP Gateway)    ← this is our registered API
4. Save
```

From this point, the voice assistant can use both HA-native tools (lights, switches, etc.) and MCP tools (weather, search, whatever you've configured on the gateway).

### Reconfiguration

```
1. Settings → Devices & Services → MCP Client → Configure
2. Add/remove tools from the enabled list
3. Adjust timeouts
4. Save (takes effect immediately, no restart needed)
```

---

## What Happens at Runtime

```
Voice: "What's the weather in Brooklin?"
         │
         ▼
┌─────────────────────┐
│  STT (Whisper, etc.) │
│  "what's the weather │
│   in brooklin"       │
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  Conversation Agent  │     chat_log.llm_api.tools includes:
│  (Ollama, OpenAI)    │     - HA native: turn_on, turn_off, get_state...
│                      │     - MCP tools: get_forecast, search_web...
│  LLM selects tool:   │
│  get_forecast(       │     ← LLM decides based on tool descriptions
│    location="Brooklin,│
│    ME", days=1)      │
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  MCPTool.async_call  │     Our llm.Tool implementation
│  → coordinator       │
│  → transport.call_   │
│    tool()            │
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  HTTP POST           │     POST http://192.168.1.50:8080/mcp
│  to Docker MCP       │     {"jsonrpc":"2.0","id":5,
│  Gateway             │      "method":"tools/call",
│                      │      "params":{"name":"get_forecast",
│                      │       "arguments":{"location":"Brooklin, ME",
│                      │        "days":1}}}
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  Gateway routes to   │     Weather MCP server container
│  weather container   │     processes the request
│  → returns forecast  │
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  LLM receives result │     Generates natural language
│  → TTS               │
│                      │
│  "Tomorrow should be │
│   partly cloudy with │
│   a high around 28°F"│
└─────────────────────┘
```

---

## Multiple Gateway Support

The integration supports multiple config entries. If you have two Docker hosts running MCP Gateways with different tools:

```
Config Entry 1: MCP Gateway (192.168.1.50)  → weather, news
Config Entry 2: MCP Gateway (192.168.1.60)  → github, calendar
```

Each registers its own LLM API. Conversation agents can enable one or both under "Control Home Assistant."

---

## CI/CD & Publishing

### GitHub Actions

```yaml
# .github/workflows/validate.yml
name: HACS Validation
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration

# .github/workflows/tests.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: |
          pip install pytest pytest-asyncio pytest-homeassistant-custom-component
          pip install homeassistant
      - run: pytest tests/
```

### Versioning & Releases

HACS tracks versions via GitHub releases. The workflow:

1. Bump version in `manifest.json`
2. Create a GitHub release with a tag (e.g., `v1.0.0`)
3. HACS picks it up automatically
4. Users see the update in HACS → Integrations

### Submitting to HACS Default Repository

Once the integration is stable and tested, submit it to the [HACS default repository](https://github.com/hacs/default) so it appears in the HACS storefront without users needing to add a custom repository. Requirements:

- Public GitHub repo with description and topics
- Valid `hacs.json` and `manifest.json`
- README with setup instructions
- HACS validation action passing
- Stable release tagged

---

## Security Notes for Distribution

When distributing as a HACS integration, a few security considerations specific to the packaging:

**Credential storage:** Auth tokens entered in the config flow are stored in HA's `.storage/core.config_entries` file, which is encrypted at rest by HA's auth system. They never appear in `configuration.yaml`, logs, or diagnostics output.

**No network calls during install:** The integration makes zero network calls until a config entry is created and the user provides a gateway URL. HACS only downloads the code from GitHub.

**Minimal permissions:** The integration requires no special HA permissions beyond what any LLM API registration needs. It doesn't create entities, devices, or service calls — it only registers tools for conversation agents to use.

**Diagnostics support:** If you add diagnostics, always redact the auth token:

```python
# diagnostics.py
async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    return {
        "gateway_url": entry.data.get("gateway_url"),
        "auth_token": "**REDACTED**",
        "tools": [t["name"] for t in entry.runtime_data.tools],
        "connected": entry.runtime_data.last_update_success,
    }
```

---

## Summary

| Question | Answer |
|----------|--------|
| Can this be a HACS integration? | Yes, it's the ideal packaging. |
| Does it require YAML? | No, fully UI-configured. |
| Does it work with all HA installation methods? | Yes (HA OS, Supervised, Container, Core). |
| Does it work with any conversation agent? | Any that supports HA's LLM API framework. |
| External dependencies? | None — uses only HA-bundled libraries. |
| Can users install it today via custom repo? | Yes, before HACS default submission. |
| Can multiple gateways be configured? | Yes, via multiple config entries. |
| Is a restart required after config changes? | Only after initial install. Options changes are live. |
