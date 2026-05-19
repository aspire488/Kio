---
name: cluster-9
description: "Skill for the Cluster_9 area of Kio. 10 symbols across 5 files."
---

# Cluster_9

10 symbols | 5 files | Cohesion: 82%

## When to Use

- Working with code in `src/`
- Understanding how open_folder, search_google, search_youtube work
- Modifying cluster_9-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/kio_selftest.py` | _test_folder_alias_detection, _test_youtube_play, _test_browser_operations |
| `src/core/browser_operator.py` | search_google, search_youtube, play_youtube |
| `src/core/file_operator.py` | open_folder, _open_path |
| `src/core/task_engine.py` | _execute_step |
| `src/core/app_operator.py` | search_web |

## Entry Points

Start here when exploring this area:

- **`open_folder`** (Function) — `src/core/file_operator.py:42`
- **`search_google`** (Function) — `src/core/browser_operator.py:39`
- **`search_youtube`** (Function) — `src/core/browser_operator.py:63`
- **`play_youtube`** (Function) — `src/core/browser_operator.py:87`
- **`search_web`** (Function) — `src/core/app_operator.py:218`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `open_folder` | Function | `src/core/file_operator.py` | 42 |
| `search_google` | Function | `src/core/browser_operator.py` | 39 |
| `search_youtube` | Function | `src/core/browser_operator.py` | 63 |
| `play_youtube` | Function | `src/core/browser_operator.py` | 87 |
| `search_web` | Function | `src/core/app_operator.py` | 218 |
| `_execute_step` | Function | `src/core/task_engine.py` | 113 |
| `_test_folder_alias_detection` | Function | `src/core/kio_selftest.py` | 123 |
| `_test_youtube_play` | Function | `src/core/kio_selftest.py` | 258 |
| `_test_browser_operations` | Function | `src/core/kio_selftest.py` | 279 |
| `_open_path` | Function | `src/core/file_operator.py` | 81 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_task → _resolve_app_path` | cross_community | 6 |
| `Run_task → _creation_flags` | cross_community | 6 |
| `Run_task → _open_web_url` | cross_community | 5 |
| `Run_task → _find_app_in_registry` | cross_community | 5 |
| `Run_task → _close_app_unix` | cross_community | 5 |
| `Run_task → _open_path` | cross_community | 5 |
| `Run_task → Search_web` | cross_community | 4 |
| `_test_youtube_play → _is_multi_step` | cross_community | 3 |
| `_test_youtube_play → _log_route` | cross_community | 3 |
| `_test_youtube_play → _lazy_import` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_18 | 1 calls |
| Cluster_19 | 1 calls |
| Cluster_16 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "open_folder"})` — see callers and callees
2. `gitnexus_query({query: "cluster_9"})` — find related execution flows
3. Read key files listed above for implementation details
