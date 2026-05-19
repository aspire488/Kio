---
name: cluster-35
description: "Skill for the Cluster_35 area of Kio. 6 symbols across 1 files."
---

# Cluster_35

6 symbols | 1 files | Cohesion: 91%

## When to Use

- Working with code in `kio_final/`
- Understanding how run work
- Modifying cluster_35-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `kio_final/mini_kio/core/kio_diagnostics.py` | _is_process_running, _is_process_running_tasklist, run, _verify_process_launch, _success (+1) |

## Entry Points

Start here when exploring this area:

- **`run`** (Method) — `kio_final/mini_kio/core/kio_diagnostics.py:101`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `run` | Method | `kio_final/mini_kio/core/kio_diagnostics.py` | 101 |
| `_is_process_running` | Function | `kio_final/mini_kio/core/kio_diagnostics.py` | 50 |
| `_is_process_running_tasklist` | Function | `kio_final/mini_kio/core/kio_diagnostics.py` | 69 |
| `_verify_process_launch` | Method | `kio_final/mini_kio/core/kio_diagnostics.py` | 137 |
| `_success` | Method | `kio_final/mini_kio/core/kio_diagnostics.py` | 146 |
| `_fail` | Method | `kio_final/mini_kio/core/kio_diagnostics.py` | 157 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run → _is_process_running_tasklist` | intra_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Kio_final | 1 calls |

## How to Explore

1. `gitnexus_context({name: "run"})` — see callers and callees
2. `gitnexus_query({query: "cluster_35"})` — find related execution flows
3. Read key files listed above for implementation details
