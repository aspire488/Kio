---
name: cluster-7
description: "Skill for the Cluster_7 area of Kio. 15 symbols across 2 files."
---

# Cluster_7

15 symbols | 2 files | Cohesion: 88%

## When to Use

- Working with code in `src/`
- Understanding how format_status_message, count_ideas, save_idea work
- Modifying cluster_7-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/memory_core.py` | _connect, count_ideas, save_idea, list_ideas, delete_idea (+9) |
| `src/core/telegram_bot.py` | format_status_message |

## Entry Points

Start here when exploring this area:

- **`format_status_message`** (Function) — `src/core/telegram_bot.py:44`
- **`count_ideas`** (Function) — `src/core/memory_core.py:66`
- **`save_idea`** (Function) — `src/core/memory_core.py:73`
- **`list_ideas`** (Function) — `src/core/memory_core.py:97`
- **`delete_idea`** (Function) — `src/core/memory_core.py:108`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `format_status_message` | Function | `src/core/telegram_bot.py` | 44 |
| `count_ideas` | Function | `src/core/memory_core.py` | 66 |
| `save_idea` | Function | `src/core/memory_core.py` | 73 |
| `list_ideas` | Function | `src/core/memory_core.py` | 97 |
| `delete_idea` | Function | `src/core/memory_core.py` | 108 |
| `add_task` | Function | `src/core/memory_core.py` | 114 |
| `list_tasks` | Function | `src/core/memory_core.py` | 121 |
| `complete_task` | Function | `src/core/memory_core.py` | 131 |
| `delete_task` | Function | `src/core/memory_core.py` | 137 |
| `kv_set` | Function | `src/core/memory_core.py` | 143 |
| `kv_list` | Function | `src/core/memory_core.py` | 165 |
| `set_session_timer` | Function | `src/core/memory_core.py` | 171 |
| `save_message` | Function | `src/core/memory_core.py` | 215 |
| `get_history` | Function | `src/core/memory_core.py` | 231 |
| `_connect` | Function | `src/core/memory_core.py` | 27 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `_context_tick_loop → _connect` | cross_community | 7 |
| `Cmd_status → _connect` | cross_community | 4 |
| `Set_session_timer → _connect` | intra_community | 3 |

## How to Explore

1. `gitnexus_context({name: "format_status_message"})` — see callers and callees
2. `gitnexus_query({query: "cluster_7"})` — find related execution flows
3. Read key files listed above for implementation details
