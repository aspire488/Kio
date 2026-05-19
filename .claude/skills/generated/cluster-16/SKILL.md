---
name: cluster-16
description: "Skill for the Cluster_16 area of Kio. 12 symbols across 2 files."
---

# Cluster_16

12 symbols | 2 files | Cohesion: 89%

## When to Use

- Working with code in `src/`
- Understanding how handle_command, route work
- Modifying cluster_16-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/command_router.py` | _lazy_import, _log_route, _is_multi_step, handle_command, route (+2) |
| `src/core/kio_selftest.py` | _test_router_dispatch, _test_structured_responses, _test_telegram_handler_simulation, _test_conversation_fallback, _test_expanded_knowledge |

## Entry Points

Start here when exploring this area:

- **`handle_command`** (Function) — `src/core/command_router.py:121`
- **`route`** (Function) — `src/core/command_router.py:276`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `handle_command` | Function | `src/core/command_router.py` | 121 |
| `route` | Function | `src/core/command_router.py` | 276 |
| `_test_router_dispatch` | Function | `src/core/kio_selftest.py` | 97 |
| `_test_structured_responses` | Function | `src/core/kio_selftest.py` | 112 |
| `_test_telegram_handler_simulation` | Function | `src/core/kio_selftest.py` | 150 |
| `_test_conversation_fallback` | Function | `src/core/kio_selftest.py` | 195 |
| `_test_expanded_knowledge` | Function | `src/core/kio_selftest.py` | 299 |
| `_lazy_import` | Function | `src/core/command_router.py` | 32 |
| `_log_route` | Function | `src/core/command_router.py` | 86 |
| `_is_multi_step` | Function | `src/core/command_router.py` | 106 |
| `_ai_fallback` | Function | `src/core/command_router.py` | 306 |
| `_show_help` | Function | `src/core/command_router.py` | 360 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_voice_loop → _is_multi_step` | cross_community | 4 |
| `Run_voice_loop → _log_route` | cross_community | 4 |
| `Run_voice_loop → _lazy_import` | cross_community | 4 |
| `Run_voice_loop → _show_help` | cross_community | 4 |
| `_test_telegram_handler_simulation → _is_multi_step` | intra_community | 4 |
| `_test_telegram_handler_simulation → _log_route` | intra_community | 4 |
| `_test_telegram_handler_simulation → _lazy_import` | intra_community | 4 |
| `_test_telegram_handler_simulation → _show_help` | intra_community | 4 |
| `_test_youtube_play → _is_multi_step` | cross_community | 3 |
| `_test_youtube_play → _log_route` | cross_community | 3 |

## How to Explore

1. `gitnexus_context({name: "handle_command"})` — see callers and callees
2. `gitnexus_query({query: "cluster_16"})` — find related execution flows
3. Read key files listed above for implementation details
