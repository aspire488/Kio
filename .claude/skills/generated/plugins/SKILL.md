---
name: plugins
description: "Skill for the Plugins area of Kio. 12 symbols across 4 files."
---

# Plugins

12 symbols | 4 files | Cohesion: 95%

## When to Use

- Working with code in `src/`
- Understanding how dist, is_fist, open_camera work
- Modifying plugins-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/plugins/gesture_activation.py` | dist, is_fist, open_camera, start_gesture_check, init_on_startup (+3) |
| `src/core/event_bus.py` | publish, subscribe |
| `src/core/ui_core.py` | start_ui_thread |
| `src/core/plugin_loader.py` | load_plugins |

## Entry Points

Start here when exploring this area:

- **`dist`** (Function) — `src/plugins/gesture_activation.py:11`
- **`is_fist`** (Function) — `src/plugins/gesture_activation.py:15`
- **`open_camera`** (Function) — `src/plugins/gesture_activation.py:27`
- **`start_gesture_check`** (Function) — `src/plugins/gesture_activation.py:41`
- **`init_on_startup`** (Function) — `src/plugins/gesture_activation.py:127`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `dist` | Function | `src/plugins/gesture_activation.py` | 11 |
| `is_fist` | Function | `src/plugins/gesture_activation.py` | 15 |
| `open_camera` | Function | `src/plugins/gesture_activation.py` | 27 |
| `start_gesture_check` | Function | `src/plugins/gesture_activation.py` | 41 |
| `init_on_startup` | Function | `src/plugins/gesture_activation.py` | 127 |
| `start_gesture_listener` | Function | `src/plugins/gesture_activation.py` | 133 |
| `listen_loop` | Function | `src/plugins/gesture_activation.py` | 153 |
| `publish` | Function | `src/core/event_bus.py` | 13 |
| `register_plugin` | Function | `src/plugins/gesture_activation.py` | 201 |
| `start_ui_thread` | Function | `src/core/ui_core.py` | 72 |
| `load_plugins` | Function | `src/core/plugin_loader.py` | 10 |
| `subscribe` | Function | `src/core/event_bus.py` | 7 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Init_on_startup → Dist` | intra_community | 4 |
| `Listen_loop → Dist` | intra_community | 3 |
| `Init_on_startup → Publish` | intra_community | 3 |
| `Init_on_startup → Open_camera` | intra_community | 3 |

## How to Explore

1. `gitnexus_context({name: "dist"})` — see callers and callees
2. `gitnexus_query({query: "plugins"})` — find related execution flows
3. Read key files listed above for implementation details
