# OpenWork Integration

**Architecture**
```
ExecutionEngine
  ↓
ProviderRegistry
  ↓
AdapterRegistry
  ↓
OpenWorkAdapter (adapters/openwork_adapter.py)
  ↓
OpenWork (adapters/openwork/...) 
```

**Runtime flow**
1. `AdapterRegistry.discover()` loads the OpenWork adapter metadata.
2. When the adapter is needed, `AdapterRegistry.load('openwork')` imports `adapters/openwork/adapter.py`.
3. The adapter's `Adapter` class exposes `health` and delegates to the internal modules:
   * `runtime.start/stop/status`
   * `workspace` for item management
   * `session` for session handling
   * `configuration` for key/value config
   * `tool_registry` for tool registration
   * `mcp.MCP` orchestrates the above.
4. `BrowserFacade` can request OpenWork functionality via the adapter registry – it never imports OpenWork directly.

**Implemented features**
- In‑memory runtime start/stop with status.
- Workspace CRUD (list, add, get).
- Session lifecycle (create, get, close).
- Simple configuration store with `get_config`/`set_config`.
- Tool registry (`register_tool`, `get_tool`, `list_tools`).
- MCP class exposing coordinated control.
- `provider.yaml` describing the adapter for discovery tools.

**Remaining TODOs**
- Persistence of runtime/workspace/config across process restarts.
- Integration tests exercising the full adapter through `AdapterRegistry`.
- Real OpenWork library binding when it becomes available.
- Security/validation for tool registration and config values.

**Known limitations**
- All state is stored in module‑level globals; not thread‑safe.
- No error handling beyond basic `None` returns.
- `MCP.status` currently returns an empty config snapshot.
