---
name: cluster-6
description: "Skill for the Cluster_6 area of Kio. 12 symbols across 1 files."
---

# Cluster_6

12 symbols | 1 files | Cohesion: 96%

## When to Use

- Working with code in `src/`
- Understanding how cmd_start, cmd_help, cmd_ideas work
- Modifying cluster_6-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/telegram_bot.py` | _log, _rate_allow, _is_allowed, _safe_message_log_summary, _send (+7) |

## Entry Points

Start here when exploring this area:

- **`cmd_start`** (Function) — `src/core/telegram_bot.py:142`
- **`cmd_help`** (Function) — `src/core/telegram_bot.py:161`
- **`cmd_ideas`** (Function) — `src/core/telegram_bot.py:175`
- **`cmd_status`** (Function) — `src/core/telegram_bot.py:189`
- **`handle_message`** (Function) — `src/core/telegram_bot.py:221`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `cmd_start` | Function | `src/core/telegram_bot.py` | 142 |
| `cmd_help` | Function | `src/core/telegram_bot.py` | 161 |
| `cmd_ideas` | Function | `src/core/telegram_bot.py` | 175 |
| `cmd_status` | Function | `src/core/telegram_bot.py` | 189 |
| `handle_message` | Function | `src/core/telegram_bot.py` | 221 |
| `run_bot` | Function | `src/core/telegram_bot.py` | 270 |
| `_log` | Function | `src/core/telegram_bot.py` | 38 |
| `_rate_allow` | Function | `src/core/telegram_bot.py` | 86 |
| `_is_allowed` | Function | `src/core/telegram_bot.py` | 98 |
| `_safe_message_log_summary` | Function | `src/core/telegram_bot.py` | 114 |
| `_send` | Function | `src/core/telegram_bot.py` | 126 |
| `_route_and_send` | Function | `src/core/telegram_bot.py` | 135 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Cmd_status → _connect` | cross_community | 4 |
| `Cmd_status → _log` | intra_community | 3 |
| `Handle_message → _log` | intra_community | 3 |
| `Cmd_help → _log` | intra_community | 3 |
| `Cmd_help → _send` | intra_community | 3 |
| `Cmd_ideas → _log` | intra_community | 3 |
| `Cmd_ideas → _send` | intra_community | 3 |
| `Cmd_start → _log` | intra_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_7 | 1 calls |
| Cluster_11 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "cmd_start"})` — see callers and callees
2. `gitnexus_query({query: "cluster_6"})` — find related execution flows
3. Read key files listed above for implementation details
