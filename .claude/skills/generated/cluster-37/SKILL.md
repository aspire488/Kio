---
name: cluster-37
description: "Skill for the Cluster_37 area of Kio. 7 symbols across 1 files."
---

# Cluster_37

7 symbols | 1 files | Cohesion: 88%

## When to Use

- Working with code in `kio_final/`
- Understanding how launch_app work
- Modifying cluster_37-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `kio_final/mini_kio/core/app_operator.py` | _expand, launch_app, _open_url, _resolve_path, _launch_from_info (+2) |

## Entry Points

Start here when exploring this area:

- **`launch_app`** (Function) — `kio_final/mini_kio/core/app_operator.py:221`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `launch_app` | Function | `kio_final/mini_kio/core/app_operator.py` | 221 |
| `_expand` | Function | `kio_final/mini_kio/core/app_operator.py` | 37 |
| `_open_url` | Function | `kio_final/mini_kio/core/app_operator.py` | 293 |
| `_resolve_path` | Function | `kio_final/mini_kio/core/app_operator.py` | 301 |
| `_launch_from_info` | Function | `kio_final/mini_kio/core/app_operator.py` | 342 |
| `_discover_and_launch` | Function | `kio_final/mini_kio/core/app_operator.py` | 365 |
| `_creation_flags` | Function | `kio_final/mini_kio/core/app_operator.py` | 405 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_task → _expand` | cross_community | 7 |
| `Run_task → _creation_flags` | cross_community | 6 |
| `Run_task → _open_url` | cross_community | 5 |
| `Run_task → _find_in_registry` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_34 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "launch_app"})` — see callers and callees
2. `gitnexus_query({query: "cluster_37"})` — find related execution flows
3. Read key files listed above for implementation details
