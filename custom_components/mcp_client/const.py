"""Constants for MCP Client integration."""

DOMAIN = "mcp_client"

CONF_GATEWAY_URL = "gateway_url"
CONF_AUTH_TOKEN = "auth_token"
CONF_ALLOWED_TOOLS = "allowed_tools"
CONF_BLOCKED_TOOLS = "blocked_tools"
CONF_TIMEOUT_CONNECTION = "timeout_connection"
CONF_TIMEOUT_EXECUTION = "timeout_execution"
CONF_TLS_MODE = "tls_mode"

DEFAULT_TIMEOUT_CONNECTION = 10
DEFAULT_TIMEOUT_EXECUTION = 60

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_CLIENT_VERSION = "1.0.1"

TLS_HTTP_TRUSTED = "http_trusted"
TLS_VERIFY_FULL = "verify_full"
