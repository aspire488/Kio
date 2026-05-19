---
name: cluster-30
description: "Skill for the Cluster_30 area of Kio. 8 symbols across 3 files."
---

# Cluster_30

8 symbols | 3 files | Cohesion: 88%

## When to Use

- Working with code in `kio_final/`
- Understanding how run_task, execute_steps, parse_command work
- Modifying cluster_30-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `kio_final/mini_kio/core/command_parser.py` | _apply_aliases, parse_command, _parse_single_step, is_multi_step |
| `kio_final/mini_kio/core/task_engine.py` | run_task, execute_steps |
| `kio_final/mini_kio/core/kio_selftest.py` | _test_command_parsing, _test_multi_step_parsing |

## Entry Points

Start here when exploring this area:

- **`run_task`** (Function) — `kio_final/mini_kio/core/task_engine.py:25`
- **`execute_steps`** (Function) — `kio_final/mini_kio/core/task_engine.py:56`
- **`parse_command`** (Function) — `kio_final/mini_kio/core/command_parser.py:49`
- **`is_multi_step`** (Function) — `kio_final/mini_kio/core/command_parser.py:154`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `run_task` | Function | `kio_final/mini_kio/core/task_engine.py` | 25 |
| `execute_steps` | Function | `kio_final/mini_kio/core/task_engine.py` | 56 |
| `parse_command` | Function | `kio_final/mini_kio/core/command_parser.py` | 49 |
| `is_multi_step` | Function | `kio_final/mini_kio/core/command_parser.py` | 154 |
| `_test_command_parsing` | Function | `kio_final/mini_kio/core/kio_selftest.py` | 83 |
| `_test_multi_step_parsing` | Function | `kio_final/mini_kio/core/kio_selftest.py` | 105 |
| `_apply_aliases` | Function | `kio_final/mini_kio/core/command_parser.py` | 42 |
| `_parse_single_step` | Function | `kio_final/mini_kio/core/command_parser.py` | 90 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_task → _expand` | cross_community | 7 |
| `Run_task → _creation_flags` | cross_community | 6 |
| `Run_task → _open_url` | cross_community | 5 |
| `Run_task → _find_in_registry` | cross_community | 5 |
| `Run_task → _pkill` | cross_community | 5 |
| `Run_task → _open_path` | cross_community | 5 |
| `Run_task → Search_web` | cross_community | 4 |
| `Run_diagnostics → _apply_aliases` | cross_community | 4 |
| `Run_diagnostics → Is_multi_step` | cross_community | 4 |
| `Run_diagnostics → _parse_single_step` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_31 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "run_task"})` — see callers and callees
2. `gitnexus_query({query: "cluster_30"})` — find related execution flows
3. Read key files listed above for implementation details
