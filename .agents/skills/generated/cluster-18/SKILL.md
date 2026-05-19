---
name: cluster-18
description: "Skill for the Cluster_18 area of Kio. 7 symbols across 2 files."
---

# Cluster_18

7 symbols | 2 files | Cohesion: 88%

## When to Use

- Working with code in `src/`
- Understanding how launch_app work
- Modifying cluster_18-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/app_operator.py` | launch_app, _open_web_url, _resolve_app_path, _launch_app_internal, _discover_and_launch (+1) |
| `src/core/kio_selftest.py` | _test_generic_app_launcher |

## Entry Points

Start here when exploring this area:

- **`launch_app`** (Function) — `src/core/app_operator.py:150`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `launch_app` | Function | `src/core/app_operator.py` | 150 |
| `_test_generic_app_launcher` | Function | `src/core/kio_selftest.py` | 220 |
| `_open_web_url` | Function | `src/core/app_operator.py` | 262 |
| `_resolve_app_path` | Function | `src/core/app_operator.py` | 273 |
| `_launch_app_internal` | Function | `src/core/app_operator.py` | 320 |
| `_discover_and_launch` | Function | `src/core/app_operator.py` | 351 |
| `_creation_flags` | Function | `src/core/app_operator.py` | 410 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_task → _resolve_app_path` | cross_community | 6 |
| `Run_task → _creation_flags` | cross_community | 6 |
| `Run_task → _open_web_url` | cross_community | 5 |
| `Run_task → _find_app_in_registry` | cross_community | 5 |
| `_test_generic_app_launcher → _resolve_app_path` | intra_community | 4 |
| `_test_generic_app_launcher → _creation_flags` | intra_community | 4 |
| `_test_generic_app_launcher → _open_web_url` | intra_community | 3 |
| `_test_generic_app_launcher → _find_app_in_registry` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_19 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "launch_app"})` — see callers and callees
2. `gitnexus_query({query: "cluster_18"})` — find related execution flows
3. Read key files listed above for implementation details
