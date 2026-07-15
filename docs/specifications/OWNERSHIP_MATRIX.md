# Ownership Matrix

| Subsystem | Owner | Responsibilities | Public API | Future Adapter | Migration Phase | Dependencies |
|----------|-------|-------------------|-----------|----------------|----------------|--------------|
| aura | Aura Team | Observation processing, memory, reasoning, planning | `aura.*` | N/A | Stable | None |
| adapters | Integration Team | External repo adapters, thin façade | `adapters.*` | Add new adapters as needed | Ongoing | `providers/` |
| browser | Browser Team | BrowserFacade and runtime contracts | `browser.*` | N/A | Stable | `runtime/` |
| runtime | Runtime Team | Core agent runtime, supervision | `runtime.*` | N/A | Stable | `providers/`, `communication/` |
| execution | Execution Team | Execution fabric, task orchestration | `execution.*` | N/A | Stable | `runtime/`, `aura/` |
| workspace | Workspace Team | State persistence, workspace mgmt | `workspace.*` | N/A | Stable | `runtime/` |
| providers | Provider Team | Provider routing, external services | `providers.*` | Expand as new services added | Ongoing | None |
| communication | Comm Team | Messaging between components | `communication.*` | N/A | Stable | `runtime/` |
| governance | Gov Team | Policy enforcement, compliance | `governance.*` | N/A | Stable | `runtime/` |
| distributed | Distributed Team | Distributed coordination utilities | `distributed.*` | N/A | Future | `runtime/` |
| voice | Voice Team | Voice interaction handling | `voice.*` | N/A | Stable | `runtime/` |
| avatar | Avatar Team | Avatar rendering and interaction | `avatar.*` | N/A | Stable | `runtime/` |

---

*ponytail: skipped detailed migration schedule – add when release planning calls for it.*