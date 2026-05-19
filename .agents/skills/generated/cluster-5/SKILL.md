---
name: cluster-5
description: "Skill for the Cluster_5 area of Kio. 12 symbols across 7 files."
---

# Cluster_5

12 symbols | 7 files | Cohesion: 88%

## When to Use

- Working with code in `src/`
- Understanding how voice_hardware_available, start_voice_daemon, format_greeting work
- Modifying cluster_5-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/core/main.py` | check_config, start_background_context_tick, start_background_voice, _watchdog_loop, main |
| `src/core/voice.py` | voice_hardware_available, start_voice_daemon |
| `src/core/personality_engine.py` | format_greeting |
| `src/core/memory_core.py` | init_db |
| `src/core/logger.py` | setup_logging |
| `src/core/context_engine.py` | start_context_monitoring |
| `src/core/behavior_scheduler.py` | start_scheduler |

## Entry Points

Start here when exploring this area:

- **`voice_hardware_available`** (Function) — `src/core/voice.py:43`
- **`start_voice_daemon`** (Function) — `src/core/voice.py:201`
- **`format_greeting`** (Function) — `src/core/personality_engine.py:54`
- **`init_db`** (Function) — `src/core/memory_core.py:33`
- **`check_config`** (Function) — `src/core/main.py:44`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `voice_hardware_available` | Function | `src/core/voice.py` | 43 |
| `start_voice_daemon` | Function | `src/core/voice.py` | 201 |
| `format_greeting` | Function | `src/core/personality_engine.py` | 54 |
| `init_db` | Function | `src/core/memory_core.py` | 33 |
| `check_config` | Function | `src/core/main.py` | 44 |
| `start_background_context_tick` | Function | `src/core/main.py` | 211 |
| `start_background_voice` | Function | `src/core/main.py` | 224 |
| `main` | Function | `src/core/main.py` | 251 |
| `setup_logging` | Function | `src/core/logger.py` | 18 |
| `start_context_monitoring` | Function | `src/core/context_engine.py` | 41 |
| `start_scheduler` | Function | `src/core/behavior_scheduler.py` | 16 |
| `_watchdog_loop` | Function | `src/core/main.py` | 235 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Get_rms` | cross_community | 3 |
| `Start_background_voice → Voice_hardware_available` | intra_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_7 | 1 calls |
| Cluster_4 | 1 calls |
| Plugins | 1 calls |

## How to Explore

1. `gitnexus_context({name: "voice_hardware_available"})` — see callers and callees
2. `gitnexus_query({query: "cluster_5"})` — find related execution flows
3. Read key files listed above for implementation details
