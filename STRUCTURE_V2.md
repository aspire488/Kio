# KIO Architecture – V2 Structure Overview

This document reconciles the current codebase with the architectural description required by **Gate C‑6 (Documentation)**.

## Layers

1. **Runtime Authority** – `mini_kio/core/runtime.py`
   * Single source of truth for process‑wide state.
   * Manages channels, safety state, integrity, resource guard, and imports of sub‑runtimes (browser, MCP).
2. **Provider Registry** – `mini_kio/core/provider_registry.py`
   * Singleton mapping of capability names → `ExecutionProvider` instances.
   * Supports `resolve`, legacy `get_provider`, and bulk capability queries.
3. **Background Task Registry** *(new)* – part of `KioRuntime` in `runtime.py`
   * Stores `asyncio.Task` objects keyed by UUID.
   * API: `register_background_task`, `cancel_background_task`, `task_status`.
   * Enables long‑running async work (e.g., CUA sandbox actions, MCP jobs) to be tracked, cancelled, and queried without polluting the global runtime.
4. **Observation Bus** – `runtime/observation_bus.py`
   * Publishes `Observation` objects to registered `Subscriber`s.
   * Used for telemetry, AURA observations, and internal event streams.
5. **Sub‑Runtimes** – BrowserRuntime, MCPRuntime, etc.
   * Imported and attached by the bootstrap process.

## Interaction Flow

- Commands arrive via a channel → `dispatch_channel_input` (runtime).
- Capability lookup goes through `ProviderRegistry.resolve` (or `get_provider` for legacy callers).
- If a capability launches a long‑running async operation, the provider can create an `asyncio.Task` and register it via `runtime.register_background_task`.
- The task can later be cancelled or its status inspected using the task ID.

## Consistency Guarantees

- The runtime remains the authoritative holder of **state** and **tasks**.
- Background tasks are automatically removed from the registry when completed (via `Task.add_done_callback`).
- No other module writes directly to `_background_tasks`; all access is through the provided methods.

---

*Document updated to reflect the newly added background task registry (Gate C‑6).*
