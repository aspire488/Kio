# Module Ownership Map (KIO)

| Module | Primary Owner | Responsibility |
|--------|----------------|-----------------|
| `mini_kio/core/runtime.py` | Runtime Team | Global process state, channel lifecycle, shutdown handling, background task registry.
| `mini_kio/core/provider_registry.py` | Provider Team | Registration and lookup of `ExecutionProvider` capabilities.
| `mini_kio/core/observation_bus.py` | Observability Team | Publishing and subscription of `Observation` events.
| `mini_kio/core/provider_contract.py` | Provider Team | Abstract contracts for providers (`ExecutionProvider`, `ProviderCapability`).
| `mini_kio/core/desktop_intelligence.py` | Desktop Team | High‑level orchestration of desktop actions via providers.\n*Ownership reflects current implementation after Gate C‑5 and the new background task registry introduced in Gate C‑6.*
