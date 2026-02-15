"""MCP Client integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import llm

from .const import DOMAIN
from .coordinator import MCPGatewayCoordinator
from .llm_api import MCPToolsAPI

_LOGGER = logging.getLogger(__name__)

type MCPClientConfigEntry = ConfigEntry[MCPGatewayCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MCPClientConfigEntry) -> bool:
    """Set up MCP Client from a config entry."""
    coordinator = MCPGatewayCoordinator(hass, entry)

    await coordinator.async_setup()

    entry.runtime_data = coordinator

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await coordinator.async_disconnect()
        raise

    api = MCPToolsAPI(hass, entry, coordinator)
    unreg = llm.async_register_api(hass, api)
    entry.async_on_unload(unreg)

    _LOGGER.info(
        "MCP Client connected to %s — %d tools registered",
        entry.data["gateway_url"],
        len(coordinator.tools),
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MCPClientConfigEntry) -> bool:
    """Unload MCP Client config entry."""
    await entry.runtime_data.async_disconnect()
    return True
