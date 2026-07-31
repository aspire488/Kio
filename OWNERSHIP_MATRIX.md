# Ownership Matrix

The matrix links high‑level system responsibilities to the concrete modules that implement them.

| Responsibility | Module(s) |
|----------------|-----------|
| Runtime state & lifecycle | `mini_kio/core/runtime.py` |
| Provider registration & capability lookup | `mini_kio/core/provider_registry.py` |
| Background async task tracking | `mini_kio/core/runtime.py` (background task methods) |
| Observation publishing | `runtime/observation_bus.py` |
| Desktop action orchestration | `mini_kio/core/desktop_intelligence.py` |
| Execution contracts | `mini_kio/core/provider_contract.py` |

*All entries are current as of Gate C‑6 documentation reconciliation.*
