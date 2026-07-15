# Adapter Registry Specification

The **Adapter Registry** is the single source of truth for all external adapters used by KIO.

## Public API

- `AdapterRegistry.instance()` – singleton access.
- `discover()` – scan the `adapters/` directory and register metadata.
- `register(info)` / `unregister(id)` – manual control.
- `load(id)` – lazy import and instantiate the adapter.
- `reload(id)`, `shutdown(id)`, `shutdown_all()` – lifecycle.
- Query helpers: `get(id)`, `list()`, `capabilities()`, `versions()`, `health()`, `validate()`.

## Types

- `AdapterInfo` – id, version, capabilities, state, module.
- `AdapterHealth` – id, status, optional details.
- `AdapterState` – REGISTERED, LOADED, UNLOADED, SHUTDOWN.

## Exceptions

- `AdapterError` base.
- `AdapterLoadError`, `AdapterRegistrationError`, `AdapterValidationError`, `AdapterHealthError`.

## Design Rationale

- **Stdlib only** – uses `importlib`, `pathlib`, `enum`, `dataclasses`.
- **Lazy loading** – adapters are imported only when needed.
- **Singleton** – global access via `AdapterRegistry.instance()`.
- **Health aggregation** – normalises boolean or dict results.

## Extending

Add a new adapter module under `adapters/` with:
```python
__adapter_id__ = "my_adapter"
__version__ = "1.0.0"
CAPABILITIES = ["foo", "bar"]

class Adapter:
    def __init__(self):
        ...
    def health(self):
        return {"status": True}
```
The registry will discover and load it automatically.
