---
name: cluster-31
description: "Skill for the Cluster_31 area of Kio. 9 symbols across 5 files."
---

# Cluster_31

9 symbols | 5 files | Cohesion: 84%

## When to Use

- Working with code in `kio_final/`
- Understanding how open_folder, search_youtube, play_youtube work
- Modifying cluster_31-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `kio_final/mini_kio/core/kio_selftest.py` | _test_folder_alias_detection, _test_app_operator_structure, _test_youtube_play |
| `kio_final/mini_kio/core/file_operator.py` | open_folder, _open_path |
| `kio_final/mini_kio/core/browser_operator.py` | search_youtube, play_youtube |
| `kio_final/mini_kio/core/task_engine.py` | _execute_step |
| `kio_final/mini_kio/core/app_operator.py` | search_web |

## Entry Points

Start here when exploring this area:

- **`open_folder`** (Function) — `kio_final/mini_kio/core/file_operator.py:42`
- **`search_youtube`** (Function) — `kio_final/mini_kio/core/browser_operator.py:51`
- **`play_youtube`** (Function) — `kio_final/mini_kio/core/browser_operator.py:64`
- **`search_web`** (Function) — `kio_final/mini_kio/core/app_operator.py:266`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `open_folder` | Function | `kio_final/mini_kio/core/file_operator.py` | 42 |
| `search_youtube` | Function | `kio_final/mini_kio/core/browser_operator.py` | 51 |
| `play_youtube` | Function | `kio_final/mini_kio/core/browser_operator.py` | 64 |
| `search_web` | Function | `kio_final/mini_kio/core/app_operator.py` | 266 |
| `_execute_step` | Function | `kio_final/mini_kio/core/task_engine.py` | 113 |
| `_test_folder_alias_detection` | Function | `kio_final/mini_kio/core/kio_selftest.py` | 178 |
| `_test_app_operator_structure` | Function | `kio_final/mini_kio/core/kio_selftest.py` | 235 |
| `_test_youtube_play` | Function | `kio_final/mini_kio/core/kio_selftest.py` | 274 |
| `_open_path` | Function | `kio_final/mini_kio/core/file_operator.py` | 81 |

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

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_37 | 1 calls |
| Cluster_34 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "open_folder"})` — see callers and callees
2. `gitnexus_query({query: "cluster_31"})` — find related execution flows
3. Read key files listed above for implementation details
