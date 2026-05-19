---
name: cluster-10
description: "Skill for the Cluster_10 area of Kio. 8 symbols across 1 files."
---

# Cluster_10

8 symbols | 1 files | Cohesion: 70%

## When to Use

- Working with code in `src/`
- Understanding how discover_application, launch_application, open_youtube work
- Modifying cluster_10-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/system_skills.py` | _normalize_open_name, _popen_detached, _vscode_argv, discover_application, _linux_folder_path (+3) |

## Entry Points

Start here when exploring this area:

- **`discover_application`** (Function) — `src/core/system_skills.py:95`
- **`launch_application`** (Function) — `src/core/system_skills.py:162`
- **`open_youtube`** (Function) — `src/core/system_skills.py:607`
- **`open_vscode`** (Function) — `src/core/system_skills.py:612`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `discover_application` | Function | `src/core/system_skills.py` | 95 |
| `launch_application` | Function | `src/core/system_skills.py` | 162 |
| `open_youtube` | Function | `src/core/system_skills.py` | 607 |
| `open_vscode` | Function | `src/core/system_skills.py` | 612 |
| `_normalize_open_name` | Function | `src/core/system_skills.py` | 63 |
| `_popen_detached` | Function | `src/core/system_skills.py` | 68 |
| `_vscode_argv` | Function | `src/core/system_skills.py` | 86 |
| `_linux_folder_path` | Function | `src/core/system_skills.py` | 149 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Perform_app_task → _normalize_open_name` | cross_community | 3 |
| `Perform_app_task → _fail` | cross_community | 3 |
| `Perform_app_task → _ok` | cross_community | 3 |
| `Open_youtube → _normalize_open_name` | intra_community | 3 |
| `Open_youtube → _log_automation` | cross_community | 3 |
| `Open_youtube → _fail` | cross_community | 3 |
| `Open_youtube → _ok` | cross_community | 3 |
| `Open_vscode → _normalize_open_name` | intra_community | 3 |
| `Open_vscode → _log_automation` | cross_community | 3 |
| `Open_vscode → _fail` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_11 | 3 calls |

## How to Explore

1. `gitnexus_context({name: "discover_application"})` — see callers and callees
2. `gitnexus_query({query: "cluster_10"})` — find related execution flows
3. Read key files listed above for implementation details
