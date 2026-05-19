---
name: cluster-22
description: "Skill for the Cluster_22 area of Kio. 6 symbols across 2 files."
---

# Cluster_22

6 symbols | 2 files | Cohesion: 100%

## When to Use

- Working with code in `src/`
- Understanding how get_idle_time, is_user_idle, get_context_summary work
- Modifying cluster_22-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/context_engine.py` | get_idle_time, is_user_idle, _context_loop, get_context_summary |
| `src/core/behavior_scheduler.py` | _scheduler_loop, _run_periodic_tasks |

## Entry Points

Start here when exploring this area:

- **`get_idle_time`** (Function) — `src/core/context_engine.py:17`
- **`is_user_idle`** (Function) — `src/core/context_engine.py:22`
- **`get_context_summary`** (Function) — `src/core/context_engine.py:85`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `get_idle_time` | Function | `src/core/context_engine.py` | 17 |
| `is_user_idle` | Function | `src/core/context_engine.py` | 22 |
| `get_context_summary` | Function | `src/core/context_engine.py` | 85 |
| `_context_loop` | Function | `src/core/context_engine.py` | 54 |
| `_scheduler_loop` | Function | `src/core/behavior_scheduler.py` | 32 |
| `_run_periodic_tasks` | Function | `src/core/behavior_scheduler.py` | 45 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `_scheduler_loop → Get_idle_time` | intra_community | 5 |

## How to Explore

1. `gitnexus_context({name: "get_idle_time"})` — see callers and callees
2. `gitnexus_query({query: "cluster_22"})` — find related execution flows
3. Read key files listed above for implementation details
