---
name: cluster-4
description: "Skill for the Cluster_4 area of Kio. 11 symbols across 3 files."
---

# Cluster_4

11 symbols | 3 files | Cohesion: 81%

## When to Use

- Working with code in `src/`
- Understanding how get_rms, run_voice_loop, test_clap_detection work
- Modifying cluster_4-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/system_skills.py` | _ps_escape, send_notification, _active_window_windows, _active_window_linux, get_active_window |
| `src/core/voice.py` | get_rms, run_voice_loop, test_clap_detection |
| `src/core/main.py` | check_timers_only, check_context, _context_tick_loop |

## Entry Points

Start here when exploring this area:

- **`get_rms`** (Function) — `src/core/voice.py:25`
- **`run_voice_loop`** (Function) — `src/core/voice.py:52`
- **`test_clap_detection`** (Function) — `src/core/voice.py:220`
- **`send_notification`** (Function) — `src/core/system_skills.py:420`
- **`get_active_window`** (Function) — `src/core/system_skills.py:575`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `get_rms` | Function | `src/core/voice.py` | 25 |
| `run_voice_loop` | Function | `src/core/voice.py` | 52 |
| `test_clap_detection` | Function | `src/core/voice.py` | 220 |
| `send_notification` | Function | `src/core/system_skills.py` | 420 |
| `get_active_window` | Function | `src/core/system_skills.py` | 575 |
| `check_timers_only` | Function | `src/core/main.py` | 71 |
| `check_context` | Function | `src/core/main.py` | 83 |
| `_ps_escape` | Function | `src/core/system_skills.py` | 415 |
| `_active_window_windows` | Function | `src/core/system_skills.py` | 505 |
| `_active_window_linux` | Function | `src/core/system_skills.py` | 539 |
| `_context_tick_loop` | Function | `src/core/main.py` | 194 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `_context_tick_loop → _connect` | cross_community | 7 |
| `_context_tick_loop → _ps_escape` | intra_community | 5 |
| `_context_tick_loop → _log_automation` | cross_community | 5 |
| `Run_voice_loop → _is_multi_step` | cross_community | 4 |
| `Run_voice_loop → _log_route` | cross_community | 4 |
| `Run_voice_loop → _lazy_import` | cross_community | 4 |
| `Run_voice_loop → _show_help` | cross_community | 4 |
| `Perform_app_task → _ps_escape` | cross_community | 4 |
| `Perform_app_task → _log_automation` | cross_community | 4 |
| `_context_tick_loop → _active_window_windows` | intra_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_16 | 1 calls |
| Cluster_11 | 1 calls |
| Cluster_14 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "get_rms"})` — see callers and callees
2. `gitnexus_query({query: "cluster_4"})` — find related execution flows
3. Read key files listed above for implementation details
