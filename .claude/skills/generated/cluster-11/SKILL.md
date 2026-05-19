---
name: cluster-11
description: "Skill for the Cluster_11 area of Kio. 23 symbols across 2 files."
---

# Cluster_11

23 symbols | 2 files | Cohesion: 88%

## When to Use

- Working with code in `src/`
- Understanding how close_application, open_file, edit_file work
- Modifying cluster_11-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/system_skills.py` | close_application, open_file, edit_file, calculate, _eval (+17) |
| `src/core/automation_test.py` | _run_system_status |

## Entry Points

Start here when exploring this area:

- **`close_application`** (Function) — `src/core/system_skills.py:132`
- **`open_file`** (Function) — `src/core/system_skills.py:286`
- **`edit_file`** (Function) — `src/core/system_skills.py:302`
- **`calculate`** (Function) — `src/core/system_skills.py:321`
- **`play_youtube`** (Function) — `src/core/system_skills.py:355`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `close_application` | Function | `src/core/system_skills.py` | 132 |
| `open_file` | Function | `src/core/system_skills.py` | 286 |
| `edit_file` | Function | `src/core/system_skills.py` | 302 |
| `calculate` | Function | `src/core/system_skills.py` | 321 |
| `play_youtube` | Function | `src/core/system_skills.py` | 355 |
| `search_google` | Function | `src/core/system_skills.py` | 370 |
| `perform_app_task` | Function | `src/core/system_skills.py` | 382 |
| `take_screenshot` | Function | `src/core/system_skills.py` | 652 |
| `read_cpu` | Function | `src/core/system_skills.py` | 704 |
| `ft_int` | Function | `src/core/system_skills.py` | 736 |
| `get_cpu_usage_message` | Function | `src/core/system_skills.py` | 761 |
| `get_memory_usage_message` | Function | `src/core/system_skills.py` | 818 |
| `get_disk_usage_message` | Function | `src/core/system_skills.py` | 825 |
| `get_ip_address_message` | Function | `src/core/system_skills.py` | 836 |
| `get_system_info` | Function | `src/core/system_skills.py` | 849 |
| `_eval` | Function | `src/core/system_skills.py` | 334 |
| `_log_automation` | Function | `src/core/system_skills.py` | 401 |
| `_ok` | Function | `src/core/system_skills.py` | 407 |
| `_fail` | Function | `src/core/system_skills.py` | 411 |
| `_screenshot_windows_powershell` | Function | `src/core/system_skills.py` | 617 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `_context_tick_loop → _log_automation` | cross_community | 5 |
| `Perform_app_task → _ps_escape` | cross_community | 4 |
| `Perform_app_task → _log_automation` | cross_community | 4 |
| `Get_cpu_usage_message → Read_cpu` | intra_community | 3 |
| `Get_cpu_usage_message → Ft_int` | intra_community | 3 |
| `Run_voice_loop → _log_automation` | cross_community | 3 |
| `Perform_app_task → _normalize_open_name` | cross_community | 3 |
| `Perform_app_task → _fail` | cross_community | 3 |
| `Perform_app_task → _ok` | cross_community | 3 |
| `Perform_app_task → _eval` | intra_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_10 | 2 calls |
| Cluster_4 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "close_application"})` — see callers and callees
2. `gitnexus_query({query: "cluster_11"})` — find related execution flows
3. Read key files listed above for implementation details
