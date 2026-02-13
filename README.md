# MCP Client for Home Assistant

HACS custom integration for connecting Home Assistant to Docker MCP Gateway.

## Installation

1. Install via HACS (search for "MCP Client" or add as custom repository)
2. Restart Home Assistant
3. Settings → Devices & Services → Add Integration → "MCP Client (Docker Gateway)"
4. Enter gateway URL and optional auth token
5. Select which tools to expose
6. Enable in your voice assistant under "Control Home Assistant"

## Configuration

- **Gateway URL**: URL of your Docker MCP Gateway (e.g., `http://192.168.1.50:8080/mcp`)
- **Auth Token**: Optional Bearer token for authentication
- **Allowed Tools**: Select which MCP tools to expose to your voice assistant
- **Timeouts**: Configure connection and execution timeouts

## Requirements

- Home Assistant 2025.1.0 or later
- Docker MCP Gateway running and accessible
- Any conversation agent that supports HA's LLM API (Ollama, OpenAI, Anthropic, etc.)

## License

MIT License
