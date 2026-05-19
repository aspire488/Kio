---
name: cluster-21
description: "Skill for the Cluster_21 area of Kio. 5 symbols across 1 files."
---

# Cluster_21

5 symbols | 1 files | Cohesion: 89%

## When to Use

- Working with code in `src/`
- Understanding how run_diagnostics work
- Modifying cluster_21-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/kio_diagnostics.py` | _test_imports, _test_url_encoding, _test_command_parsing, run_diagnostics, _write_results_log |

## Entry Points

Start here when exploring this area:

- **`run_diagnostics`** (Function) — `src/core/kio_diagnostics.py:262`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `run_diagnostics` | Function | `src/core/kio_diagnostics.py` | 262 |
| `_test_imports` | Function | `src/core/kio_diagnostics.py` | 171 |
| `_test_url_encoding` | Function | `src/core/kio_diagnostics.py` | 206 |
| `_test_command_parsing` | Function | `src/core/kio_diagnostics.py` | 232 |
| `_write_results_log` | Function | `src/core/kio_diagnostics.py` | 332 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_diagnostics → _apply_aliases` | cross_community | 4 |
| `Run_diagnostics → Is_multi_step` | cross_community | 4 |
| `Run_diagnostics → _parse_single_step` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_8 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "run_diagnostics"})` — see callers and callees
2. `gitnexus_query({query: "cluster_21"})` — find related execution flows
3. Read key files listed above for implementation details
