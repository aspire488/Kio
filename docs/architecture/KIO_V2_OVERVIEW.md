# KIO V2 Overview

KIO V2 introduces a modular architecture where **core components** never import external adapters directly. Instead, all adapters are discovered and managed by the **Adapter Registry** (see `ADAPTER_REGISTRY.md`).

## Key Changes
- Central `adapters/` package with discovery, loading, health aggregation.
- Core modules obtain adapters via:
  ```python
  from adapters.registry import AdapterRegistry
  adapter = AdapterRegistry.instance().load("openwork")
  ```
- Lifecycle hooks (`shutdown`, `reload`) allow graceful restarts.
- Version and capability metadata enable runtime decision making.

The registry is the only entry point for external functionality such as OpenWork, Scrapling, Agency Swarm, Shepherd, etc.
