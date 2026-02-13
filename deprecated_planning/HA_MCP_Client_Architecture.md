# Home Assistant MCP Client Architecture

## Overview

This document outlines the architecture for enabling Home Assistant to function as an MCP (Model Context Protocol) client, allowing the home assistant voice assistant to call external MCP servers and use their tools, prompts, and resources.

### Current State
- ✅ Home Assistant native MCP Server integration (HA → MCP)
- ❌ Home Assistant MCP Client integration (MCP → HA)
- **Gap**: No ability for HA to consume external MCP tools/services

### Goal
Enable Home Assistant's AI/voice services to use MCP servers as an extension point for additional functionality, tools, and knowledge sources.

---

## Architecture Components

### 1. Core MCP Client Component

#### File Structure
```
/homeassistant/components/mcp_client/
├── __init__.py           # Component registration
├── config_flow.py        # Configuration UI for adding MCP servers
├── manager.py            # MCP server connection manager
├── client.py             # Basic MCP client implementation
├── transports/           # Transport protocols implementation
│   ├── stdio.py
│   ├── sse.py
│   └── websocket.py
├── server_interface.py   # MCP server interaction layer
├── tools.py              # Tool invocation handler
├── prompts.py            # Prompt retrieval handler
└── resources.py          # Resource access handler
```

#### Key Classes

##### `MCPClient`
- Manages connection to MCP servers
- Handles initialization and lifecycle
- Transport protocol abstraction
- Connection state tracking

##### `MCPTransport`
- Base class for transport implementations
- stdio, SSE, WebSocket transports
- Async request/response handling
- Error handling and reconnection

##### `MCPManager`
- Manages multiple MCP server connections
- Service discovery
- Connection pooling
- Health monitoring

---

## Transport Protocols

### STDIO Transport

**Use Case**: Local MCP servers, Docker containers

**Implementation Requirements**:
- Fork process for running server
- stdin/stdout for communication
- Async I/O for message passing
- Process lifecycle management

**Security Considerations**:
- Validate server command and arguments
- Run in restricted, isolated environment
- Resource usage limits
- Process timeout handling

### SSE Transport

**Use Case**: HTTP-based MCP servers, remote servers

**Implementation Requirements**:
- HTTP client for SSE connections
- Event streaming parsing
- Connection reconnection logic
- Header management (auth tokens)

**Security Considerations**:
- HTTPS/TLS enforcement
- CORS configuration
- API key/token authentication
- Request/response throttling

### WebSocket Transport

**Use Case**: Real-time MCP servers, local services

**Implementation Requirements**:
- WebSocket client implementation
- Ping/pong heartbeats
- Message serialization
- Connection resilience

**Security Considerations**:
- WebSocket protocol validation
- Rate limiting
- Connection timeouts
- Token-based authentication

---

## Security Architecture

### 1. Credential Management

#### API Token Storage
- **Storage**: Secrets store (Home Assistant's native secret manager)
- **Access**: Component-level, scoped to specific MCP server
- **Rotation**: Config flow support for token updates

#### Credential Types
```python
# Environment variables (for process-based servers)
- API_TOKEN: Standard bearer token

# HTTP Headers (SSE/WebSocket)
- Authorization: Bearer {token}
- X-API-Key: {api_key}

# Custom credentials (extensible)
- Custom header values
- Basic auth credentials
```

**Security Best Practices**:
- Never store credentials in configuration files
- Use HA secrets manager for sensitive data
- Rotate tokens regularly
- Implement token validation on connection

### 2. Network Security

#### Transport Proteocols
- Force TLS/HTTPS for remote connections
- Certificate pinning for known servers
- Self-signed certificate validation

#### Service Boundaries
- Network isolation where possible
- Rate limiting per server
- Connection pooling with max connections
- Circuit breaker pattern for failed connections

### 3. Resource Isolation

#### Process Security
- Execute MCP servers in isolated containers (Docker) when possible
- Resource limits (CPU, memory)
- Security context/perimeter configuration

#### Data Sanitization
- Validate all inputs from MCP servers
- Input sanitization for tool parameters
- Output validation before HA consumption
- Rate limiting protection against DoS

### 4. Authentication & Authorization

#### Authentication Flow
```
1. User configures MCP server URL and credentials
2. HA validates connection and token
3. Establishes authenticated MCP session
4. Validates server capabilities and permissions
5. Establishes persistent connection
```

#### Authorization Model
- **Scope-based access**: Limit what operations HA can perform
- **Per-server policies**: Fine-grained control per MCP server
- **Audit logging**: Record all MCP server interactions

---

## Configuration System

### Configuration Schema
```yaml
# Configuration.yaml example
mcp_client:
  enabled: true
  servers:
    - server_id: "example_mcp_server"
      command: "python"
      args: ["-m", "example_server"]
      transport: "stdio"
      env:
        API_TOKEN: !secret mcp_token
      auto_discovery: true
      health_check_interval: 30

    - server_id: "remote_api_server"
      url: "https://api.example.com/mcp"
      transport: "sse"
      headers:
        Authorization: !secret remote_mcp_token
      reconnect_on_disconnect: true
      max_retries: 5

    - server_id: "local_service"
      url: "ws://localhost:8080/mcp"
      transport: "websocket"
      timeout: 10
```

### Configuration Flow
- **Setup**: Add multiple MCP servers via HA UI
- **Validation**: Validate configuration schema
- **Discovery**: Auto-detect accessible servers (optional)
- **Management**: Start/stop/monitor servers
- **Error Handling**: Graceful degradation on failures

---

## Service Integration

### 1. Assistant Service Integration

#### Integration with HA Voice Assistant
```yaml
# homeassistant/voice/assist_pipeline.py modification
class AssistPipeline:
    def __init__(self):
        # Existing components...
        # New MCP client integration
        self.mcp_client = MCPManager()

    async def process_query(self, query, context):
        # Existing processing...

        # MCP Tool invocation
        enhanced_query = await self._enhance_with_mcp_tools(query, context)

        # Existing processing...

    async def _enhance_with_mcp_tools(self, query, context):
        """Enhance query with MCP server capabilities"""
        # Query MCP tools
        tools = await self.mcp_client.list_tools()

        # Call relevant tools
        tool_results = []
        for tool in tools:
            if tool.match(query):
                result = await self.mcp_client.call_tool(
                    tool.name,
                    arguments=self._extract_arguments(query, tool)
                )
                tool_results.append(result)

        return self._integrate_tool_results(tool_results, query)
```

### 2. Entity Actions Integration

#### Entity Trigger System
```yaml
# New component for entity-based MCP tool triggers
mcp_entity_actions:
  enabled: true
  triggers:
    - entity: "switch.my_device"
      tool: "example_tool"
      parameters:
        action: "toggle"
    - event: "state_changed"
      conditions: "{{ entity_attr.state == 'on' }}"
      tool: "notification_service"
```

### 3. Automation Integration

#### MCP Tool Triggers in Automations
```yaml
automation:
  - alias: "Call MCP tool on motion"
    trigger:
      - platform: state
        entity_id: "binary_sensor.motion_detected"
        to: "on"
    condition: []
    action:
      - service: mcp_client.call_tool
        data:
          server_id: "security_system"
          tool_name: "trigger_security_check"
          parameters:
            location_id: "entrance"
            sensitivity: "high"
```

---

## Error Handling & Resilience

### 1. Connection Management

#### Reconnection Strategy
- **Immediate retry**: Short delays for transient failures
- **Exponential backoff**: Progressive delays for persistent issues
- **Max retries**: Hard limit to prevent infinite loops
- **Failed state threshold**: Stop trying after multiple failures

#### Health Monitoring
```python
class MCPHealthMonitor:
    async def health_check(self, server_id, interval):
        while True:
            try:
                status = await self.ping_server(server_id)
                if not status.is_healthy:
                    logger.error(f"MCP server {server_id} unhealthy")
                    # Trigger alert
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                # Start reconnection

            await asyncio.sleep(interval)
```

### 2. Error Categories & Response

#### Error Handling Hierarchy
```python
# Critical errors
- Server unreachable
- Authentication failed
- Invalid configuration

# Non-critical errors
- Tool execution timeout
- Rate limiting from server
- Transient network issues
- Partial tool results

# Recovery actions
1. Log error with context
2. Mark server as degraded
3. Retry operation
4. Alert administrator if persistent
5. Fallback to HA native behavior
```

### 3. Timeout Management

#### Timeout Configuration
- **Connection timeout**: 30 seconds
- **Tool execution timeout**: 120 seconds
- **Resource retrieval timeout**: 60 seconds
- **Readiness check timeout**: 10 seconds

#### Timeout Categories
```python
class TimeoutConfig:
    # Connection timeouts
    CONN_TIMEOUT = 30  # seconds
    SOCKET_TIMEOUT = 20

    # Operation timeouts
    TOOL_EXECUTION = 120
    PROMPT_RETRIEVAL = 60
    RESOURCE_ACCESS = 60

    # Health check timeouts
    HEALTH_CHECK = 10
    HEARTBEAT = 30
```

---

## Logging & Monitoring

### 1. Logging Strategy

#### Log Levels
- **DEBUG**: Detailed connection and protocol messages
- **INFO**: Server lifecycle events, tool invocations
- **WARNING**: Reconnection attempts, degraded states
- **ERROR**: Connection failures, tool execution errors
- **CRITICAL**: Complete server failures, security issues

#### Structured Logging
```python
logger.info(
    "mcp_tool_invoked",
    server_id=server_id,
    tool_name=tool_name,
    duration_ms=duration,
    success=True,
    error=None
)

logger.warning(
    "mcp_server_reconnecting",
    server_id=server_id,
    attempts=attempt,
    max_attempts=max_attempts
)
```

### 2. Metrics Collection

#### Key Metrics
- **MCP Server Health**: Uptime, availability
- **Tool Usage**: Count, latency, success rate
- **Connection Metrics**: Connection count, active connections
- **Error Rates**: Connection errors, tool errors
- **Performance**: Latency distributions

#### Prometheus Metrics Export
```python
# Metric definitions
mcp_server_connections_total = Gauge(
    "mcp_server_connections_total",
    "Total number of MCP server connections"
)

mcp_tool_invocations_total = Counter(
    "mcp_tool_invocations_total",
    "Total number of MCP tool invocations",
    ["server_id", "tool_name"]
)

mcp_tool_latency_seconds = Histogram(
    "mcp_tool_latency_seconds",
    "Time taken to execute MCP tools",
    ["server_id", "tool_name"]
)
```

---

## Testing Strategy

### 1. Unit Testing

#### Test Coverage Areas
- Transport protocol implementations
- Configuration validation
- Error handling scenarios
- Security validation

#### Test Frameworks
- pytest for core logic
- pytest-asyncio for async tests
- unittest.mock for dependency mocking

### 2. Integration Testing

#### Test Scenarios
- Multiple server configurations
- Transport protocol interoperability
- HA component integration
- Security authentication

#### Test Environment
- Local test MCP servers
- Mock servers for HTTP/WebSocket
- Environment variables for configuration testing

### 3. Security Testing

#### Security Audits
- Credential validation
- Input sanitization
- Transport security verification
- Authentication flow testing

---

## Performance Considerations

### 1. Scalability

#### Concurrent Connections
- Limit concurrent MCP server connections (configurable threshold)
- Connection pooling for frequent operations
- Async processing to avoid blocking HA

#### Resource Management
- Memory limits per MCP server
- CPU time limits for tool execution
- Process termination for runaway servers

### 2. Optimization

#### Load Balancing
- Strategic request routing between MCP servers
- Failover routing on server failures
- Request batching for I/O operations

#### Caching
- Cache tool results for identical queries
- Resource caching with TTL
- Prompt result caching

---

## Implementation Phases

### Phase 1: Core MCP Client ([MVP])
**Goal**: Basic MCP client functionality

**Tasks**:
- [ ] Implement transport base class and stdio transport
- [ ] Basic MCP client with connection management
- [ ] Tool listing and calling
- [ ] Configuration flow for MCP servers
- [ ] Unit tests for core functionality

### Phase 2: Service Integration
**Goal**: Integrate with HA services

**Tasks**:
- [ ] Assist pipeline integration
- [ ] Voice assistant query enhancement
- [ ] Automation trigger system
- [ ] Logging and monitoring setup

### Phase 3: Security Enhancement
**Goal**: Implement security best practices

**Tasks**:
- [ ] Credential management system
- [ ] Authentication flow implementation
- [ ] Security validation
- [ ] Penetration testing

### Phase 4: Advanced Features
**Goal**: Complete feature set

**Tasks**:
- [ ] SSE and WebSocket transports
- [ ] Health monitoring and auto-recovery
- [ ] Prometheus metrics
- [ ] Admin dashboard for MCP servers

---

## Security Checklist

### Configuration Security
- [ ] No sensitive data in configuration files
- [ ] Use HA secrets manager for tokens
- [ ] Validate all configuration inputs
- [ ] Harden configuration permissions

### Transport Security
- [ ] Force HTTPS for remote connections
- [ ] Implement TLS certificate validation
- [ ] Configure CORS properly
- [ ] Validate WebSocket protocol

### Implementation Security
- [ ] Validate all MCP server inputs
- [ ] Sanitize tool parameters
- [ ] Rate limit tool calls
- [ ] Implement circuit breakers
- [ ] Timeout all operations

### Operational Security
- [ ] Secure credential storage
- [ ] Audit MCP tool invocations
- [ ] Monitor for unusual activity
- [ ] Regular security updates
- [ ] Security training for administrators

---

## Maintenance & Updates

### Version Compatibility
- Support MCP SDK version upgrades
- Maintain backward compatibility with MCP v1.x
- Document breaking changes clearly

### Documentation Requirements
- Installation and configuration guide
- Security best practices documentation
- Troubleshooting guide
- API reference for customizations

### Community Engagement
- Open issue tracking
- Pull request review process
- Version release schedule
- Security advisory notifications

---

## Dependencies

### Required Dependencies
- `mcp>=1.0.0` - MCP protocol implementation
- `aiohttp>=3.9` - HTTP client (SSE transport)
- `websockets>=12` - WebSocket client
- `pydantic>=2.0` - Configuration validation

### Optional Dependencies
- `docker>=7.0` - Container integration
- `prometheus_client>=0.20` - Metrics collection
- `jinja2>=3.1` - Template rendering (notifications)
- `python-dotenv>=1.0` - Environment variable management

---

## Conclusion

This architecture provides a comprehensive foundation for integrating MCP servers with Home Assistant, with a strong emphasis on security, reliability, and performance. The modular design allows for incremental development while maintaining clean separation of concerns.

The implementation should follow Home Assistant's existing coding standards, architectural patterns, and security practices to ensure seamless integration and maintainability.