# MCP Client Integration Review

**Date:** February 15, 2026
**Reviewer:** Claude Opus 4.6
**Scope:** `custom_components/mcp_client/`
**Version:** v1.0.1

---

## 1. HA Integration Standards

### manifest.json — COMPLIANT

All required fields present: `domain`, `name`, `codeowners`, `config_flow`, `version`, `integration_type`, `iot_class`.
Version `1.0.1` matches latest git tag `v1.0.1`.

### strings.json / translations/en.json — COMPLIANT

- Error keys (`cannot_connect`, `invalid_auth`, `no_tools_found`, `unknown`) all match codes used in `config_flow.py`
- `translations/en.json` mirrors `strings.json` exactly
- Options flow keys (`allowed_tools`, `timeout_connection`, `timeout_execution`) match the options schema

### hacs.json — COMPLIANT

`zip_release` is not set — correct for HACS pulling directly from the repo.

---

## 2. Findings

### ERROR — Transport leak on failed first refresh

**File:** `__init__.py:24-28`

```python
await coordinator.async_setup()       # connects transport
entry.runtime_data = coordinator
await coordinator.async_config_entry_first_refresh()  # may raise ConfigEntryNotReady
```

If `async_config_entry_first_refresh()` raises `ConfigEntryNotReady` (e.g., gateway temporarily unreachable), `async_setup_entry` fails. Home Assistant does **not** call `async_unload_entry` for a failed setup, so `coordinator.async_disconnect()` is never invoked. The `aiohttp.ClientSession` from `async_get_clientsession` is shared so it won't leak, but the MCP session remains logically open on the server side (the `Mcp-Session-Id` is never terminated).

**Fix:** Wrap the first refresh in a try/except and call `coordinator.async_disconnect()` on failure before re-raising:

```python
try:
    await coordinator.async_config_entry_first_refresh()
except ConfigEntryNotReady:
    await coordinator.async_disconnect()
    raise
```

---

### ERROR — SSE parser has no JSON error handling

**File:** `transport.py:129-132`

```python
return json.loads("\n".join(data_lines))
```

`json.loads` is called on raw SSE data with no try/except. A malformed response from the gateway will raise an unhandled `json.JSONDecodeError` that propagates as an opaque traceback instead of a meaningful `MCPTransportError`.

**Fix:** Wrap both `json.loads` calls in the method:

```python
try:
    return json.loads("\n".join(data_lines))
except json.JSONDecodeError as err:
    raise MCPTransportError(f"Invalid JSON in SSE data: {err}") from err
```

---

### WARNING — `security.py:filter_tool_results` is dead code

**File:** `security.py:15-20`

`filter_tool_results` is defined but never imported or called anywhere in the integration. There is no `diagnostics.py` platform, so auth token redaction for diagnostics never actually happens.

Either implement a `diagnostics.py` that uses it, or remove it to avoid giving a false sense of security.

---

### WARNING — `security.py:validate_tool_input` is a no-op

**File:** `security.py:23-25`

```python
def validate_tool_input(schema: dict, input_data: dict) -> dict:
    """Validate tool input against schema."""
    return input_data
```

This function is never called and does nothing. It should either be implemented or removed. Having a function named `validate_tool_input` that performs no validation is misleading.

---

### WARNING — `_build_vol_schema` does not handle nested or complex types

**File:** `llm_api.py:109-142`

The schema builder handles flat properties with primitive types correctly (including `required` vs `optional`). However:

- `"type": "array"` maps to bare `list` — item type constraints are lost
- `"type": "object"` maps to bare `dict` — nested property schemas are lost
- `"enum"` constraints are ignored
- `"oneOf"` / `"anyOf"` union types are ignored

This won't crash — voluptuous will accept any list/dict — but it means the LLM can pass malformed nested data that the MCP server may reject. For most MCP tools with simple string/number parameters, this works fine.

**Fix (if needed):** Add recursive handling for nested objects and `vol.All(list, [item_type])` for typed arrays. Prioritize this only if MCP tools with complex schemas are in use.

---

### WARNING — Hardcoded protocol version string

**File:** `transport.py:49`

```python
"protocolVersion": "2024-11-05",
```

And the client info version at line 53:

```python
"version": "1.0.0",
```

Both are hardcoded inline. The protocol version should be a constant in `const.py`, and the client version should reference `manifest.json`'s version (or a shared constant) to avoid version drift.

---

### WARNING — Redundant `self._hass` in coordinator

**File:** `coordinator.py:39`

```python
self._hass = hass
```

`DataUpdateCoordinator` already stores `self.hass`. The redundant `self._hass` attribute is unused (the coordinator never references it) and should be removed to avoid confusion about which to use.

---

### INFO — `config_flow.py:107` broad exception catch is acceptable but could log more context

**File:** `config_flow.py:107-109`

```python
except Exception:
    _LOGGER.exception("Unexpected error during MCP connection")
    errors["base"] = "unknown"
```

This follows standard HA config flow patterns (catch-all with `"unknown"` error key). `_LOGGER.exception()` captures the full traceback. No change required, but binding the exception (`except Exception as err:`) would allow including the error type in the message if desired.

---

### INFO — Options flow shows empty tool selector when coordinator unavailable

**File:** `config_flow.py:175-176`

```python
coordinator = self.config_entry.runtime_data
current_tools = [t["name"] for t in coordinator.tools] if coordinator else []
```

If the coordinator is `None` (entry not fully loaded), the tool selector renders empty. The user can still save, but the UX is confusing. Consider showing an error or aborting the options flow if the coordinator isn't available.

---

### INFO — No `async_migrate_entry` for future schema changes

**File:** `config_flow.py:57`

```python
VERSION = 1
```

No `async_migrate_entry` function exists. This is fine at VERSION 1, but should be added when VERSION is incremented to handle schema migrations gracefully.

---

### INFO — Gateway URL logged at INFO level

**File:** `__init__.py:34-36`

```python
_LOGGER.info(
    "MCP Client connected to %s — %d tools registered",
    entry.data["gateway_url"],
```

The gateway URL is logged at INFO. This is generally fine since URLs shouldn't contain credentials (auth is via a separate token field). If URL-embedded credentials are a concern, move to DEBUG level.

---

## 3. Summary

| Severity | Count | Items |
|----------|-------|-------|
| Error    | 2     | Transport leak on failed setup; unhandled JSON parse in SSE |
| Warning  | 5     | Dead security code (x2); incomplete schema types; hardcoded versions; redundant field |
| Info     | 4     | Broad catch style; empty options UX; no migration function; URL logging |
| Compliant| 3     | manifest.json; strings/translations; hacs.json |

## 4. Priority Actions

**P0 — Fix now:**
1. Add disconnect-on-failure guard in `async_setup_entry` (transport leak)
2. Add `json.JSONDecodeError` handling in `_parse_sse` (opaque crashes)

**P1 — Should fix:**
3. Remove or implement `security.py` functions (dead/misleading code)
4. Move protocol version to `const.py`

**P2 — Nice to have:**
5. Handle complex JSON Schema types in `_build_vol_schema` if needed
6. Clean up redundant `self._hass`
7. Add `diagnostics.py` platform with proper token redaction

---

## 5. Accuracy Notes on Previous Review

The prior `INTEGRATION_REVIEW.md` contained several inaccurate findings:

- **Error #2 was fabricated:** Claimed a "typo" in the options flow schema keys. No typo exists — `CONF_ALLOWED_TOOLS` is used correctly on both line 183 and 185.
- **Error #3 was wrong:** Claimed `required` handling was missing. The code at line 115 (`required = set(json_schema.get("required", []))`) and lines 128-131 clearly implement it.
- **Warning #5 was wrong:** Criticized `finally: await transport.disconnect()` as incorrect. This is the standard resource cleanup pattern — `finally` ensures cleanup regardless of success or failure.
- **Warning #8 was wrong:** Criticized wrapping exceptions as `UpdateFailed` in `_async_update_data`. This is the documented HA `DataUpdateCoordinator` pattern.

---

*Generated by Claude Opus 4.6 against commit `1c1fa5a`*
