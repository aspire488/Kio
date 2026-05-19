---
name: kio-final
description: "Skill for the Kio_final area of Kio. 13 symbols across 4 files."
---

# Kio_final

13 symbols | 4 files | Cohesion: 96%

## When to Use

- Working with code in `kio_final/`
- Understanding how cmd_help, ask_llm, handle_command work
- Modifying kio_final-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `kio_final/mini_kio/core/command_router.py` | _lazy_import, _log_route, _is_multi_step, handle_command, route (+2) |
| `kio_final/mini_kio/core/kio_selftest.py` | _test_router_dispatch, _test_structured_responses, _test_conversation_fallback, _test_telegram_simulation |
| `kio_final/kio_bot.py` | cmd_help |
| `kio_final/mini_kio/core/llm_router.py` | ask_llm |

## Entry Points

Start here when exploring this area:

- **`cmd_help`** (Function) — `kio_final/kio_bot.py:53`
- **`ask_llm`** (Function) — `kio_final/mini_kio/core/llm_router.py:144`
- **`handle_command`** (Function) — `kio_final/mini_kio/core/command_router.py:97`
- **`route`** (Function) — `kio_final/mini_kio/core/command_router.py:201`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `cmd_help` | Function | `kio_final/kio_bot.py` | 53 |
| `ask_llm` | Function | `kio_final/mini_kio/core/llm_router.py` | 144 |
| `handle_command` | Function | `kio_final/mini_kio/core/command_router.py` | 97 |
| `route` | Function | `kio_final/mini_kio/core/command_router.py` | 201 |
| `_test_router_dispatch` | Function | `kio_final/mini_kio/core/kio_selftest.py` | 122 |
| `_test_structured_responses` | Function | `kio_final/mini_kio/core/kio_selftest.py` | 133 |
| `_test_conversation_fallback` | Function | `kio_final/mini_kio/core/kio_selftest.py` | 143 |
| `_test_telegram_simulation` | Function | `kio_final/mini_kio/core/kio_selftest.py` | 188 |
| `_lazy_import` | Function | `kio_final/mini_kio/core/command_router.py` | 30 |
| `_log_route` | Function | `kio_final/mini_kio/core/command_router.py` | 55 |
| `_is_multi_step` | Function | `kio_final/mini_kio/core/command_router.py` | 71 |
| `_ai_fallback` | Function | `kio_final/mini_kio/core/command_router.py` | 246 |
| `_show_help` | Function | `kio_final/mini_kio/core/command_router.py` | 288 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `_test_telegram_simulation → _is_multi_step` | intra_community | 4 |
| `_test_telegram_simulation → _log_route` | intra_community | 4 |
| `_test_telegram_simulation → _lazy_import` | intra_community | 4 |
| `_test_telegram_simulation → _show_help` | intra_community | 4 |

## How to Explore

1. `gitnexus_context({name: "cmd_help"})` — see callers and callees
2. `gitnexus_query({query: "kio_final"})` — find related execution flows
3. Read key files listed above for implementation details
