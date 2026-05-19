---
name: cluster-24
description: "Skill for the Cluster_24 area of Kio. 6 symbols across 1 files."
---

# Cluster_24

6 symbols | 1 files | Cohesion: 83%

## When to Use

- Working with code in `src/`
- Understanding how automation_full_test, run_test work
- Modifying cluster_24-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/automation_test.py` | _write_log, _run_simple_command, _run_search_command, _run_gui_automation, automation_full_test (+1) |

## Entry Points

Start here when exploring this area:

- **`automation_full_test`** (Function) — `src/core/automation_test.py:71`
- **`run_test`** (Function) — `src/core/automation_test.py:218`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `automation_full_test` | Function | `src/core/automation_test.py` | 71 |
| `run_test` | Function | `src/core/automation_test.py` | 218 |
| `_write_log` | Function | `src/core/automation_test.py` | 17 |
| `_run_simple_command` | Function | `src/core/automation_test.py` | 27 |
| `_run_search_command` | Function | `src/core/automation_test.py` | 38 |
| `_run_gui_automation` | Function | `src/core/automation_test.py` | 60 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_10 | 1 calls |
| Cluster_11 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "automation_full_test"})` — see callers and callees
2. `gitnexus_query({query: "cluster_24"})` — find related execution flows
3. Read key files listed above for implementation details
