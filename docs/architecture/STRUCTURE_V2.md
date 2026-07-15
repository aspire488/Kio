# Structure V2

## Directory Tree

```
.
├─ aura/
├─ adapters/
├─ browser/
├─ runtime/
├─ execution/
├─ workspace/
├─ providers/
├─ communication/
├─ governance/
├─ distributed/
├─ voice/
└─ avatar/
```

## Purpose of Each Directory

- **aura/** – Observation processing, memory, reasoning, planning, and learning.
- **adapters/** – Integration points for external repositories; thin façade adapters.
- **browser/** – BrowserFacade implementation and browser‑runtime contracts.
- **runtime/** – Core agent runtime, supervision, and lifecycle management.
- **execution/** – Execution fabric that orchestrates tasks across runtimes.
- **workspace/** – State persistence and workspace management.
- **providers/** – Provider system for routing to external services.
- **communication/** – Messaging and inter‑component communication layer.
- **governance/** – Policy, compliance, and governance enforcement.
- **distributed/** – Distributed coordination and clustering utilities.
- **voice/** – Voice interaction runtime and routing.
- **avatar/** – Avatar rendering and interaction subsystem.

## Ownership

- **KIO** owns: aura, runtime, execution, workspace, providers, communication, governance, distributed, voice, avatar.
- **AURA** owns: aura (its internal components).
- **External** – adapters only expose external repos.

## Layer Boundaries

```
[External Repos] → adapters → providers → runtime → execution → aura
```

Each arrow represents a unidirectional dependency; lower layers must not depend on higher ones.

## Dependency Direction

All imports flow **inward** toward core KIO layers; no upper layer may import a lower‑level implementation detail.

## Future Migration Targets

- Consolidate `adapters/` into a dedicated `adapter_registry` under `runtime`.
- Split `runtime/` into `agent_runtime/` and `workflow_engine/` when scaling.
- Introduce `public_api/` package for stable external contracts.

---

*ponytail: skipped detailed design diagrams – add when architecture reviews demand visual assets.*