# Phase 4: P1 Contract Repair — Complete

## Summary

Fixed the P1 execution-contract mismatch between `StepRunner._call_boundary()` and `execute_capability()`. All 63 YAML templates now route correctly through the execution boundary.

## Problem

Two layers of routing failure blocked 61/63 templates:

1. **P1: Format mismatch** — `_call_boundary()` passed plain strings (e.g. `"hello"`, `"https://example.com"`) to `execute_capability()`, which expects `"app::cap::args"` format. Result: `"Invalid capability routing format."`

2. **P2: Missing `_ACTION_MAP` entries** — 57 templates used `(capability, action)` pairs not in `_ACTION_MAP`. Result: `None` boundary action → no routing at all.

## Fix

### `_call_boundary()` — 3 lines added (`step_runner.py:269-272`)
```python
if action == "execute_capability":
    import json
    target = f"{capability}::{step_action}::{json.dumps(inputs)}"
```

When the boundary action is `execute_capability`, the target is now formatted as `"capability::action::json(inputs)"` — matching the contract `execute_capability()` expects at `app_operator.py:3179`.

### `_ACTION_MAP` — 127 entries added (`step_runner.py:28-230`)
All `(capability, action)` pairs found in the 63 YAML templates that were missing from the map. Filesystem actions route to their specific boundary actions (`write_csv`, `read_file`, `fs_exists`, etc.); all others route to `execute_capability`.

## Results

| Metric | Before | After |
|--------|--------|-------|
| FULLY_EXECUTABLE | 2 | 2 |
| ROUTING_WORKS | 0 | 61 |
| BLOCKED | 61 | 0 |
| UNKNOWN_ACTION | 57 | 0 |
| Tests passing | 75/81 | 81/81 |

### Post-P1 Classification
- **2 FULLY_EXECUTABLE**: `browser.structured_extract`, `files.download_folder_organizer` — use direct boundary actions (`browser_open`, `read_file`)
- **61 ROUTING_WORKS**: routing is correct, but `execute_capability()` returns `"{app} does not support '{cap}'."` because the capability isn't in `APP_CAPABILITIES`. Next step: add providers.

## Provider Gaps (Post-P1)

| Capability | Templates | Gap Type | Resolution |
|---|---|---|---|
| ai_reasoning | 46 | ROUTING_ONLY | Add to `APP_CAPABILITIES` + LLM handler |
| communication | 31 | ROUTING_ONLY | Add to `APP_CAPABILITIES` + message handler |
| terminal | 14 | ADAPTER_REQUIRED | Add to `APP_CAPABILITIES` + TerminalProvider |
| memory | 13 | PROVIDER_REQUIRED | New MemoryProvider |
| github | 8 | ADAPTER_REQUIRED | Add to `APP_CAPABILITIES` + MCP adapter |
| mcp_tool | 7 | PROVIDER_REQUIRED | New MCPToolProvider |
| workflow | 7 | ADAPTER_REQUIRED | Extend WorkflowExecutionProvider |
| calendar | 4 | PROVIDER_REQUIRED | New CalendarProvider |
| media | 4 | PROVIDER_REQUIRED | New MediaProvider |

## Safety

- Resource usage: 17.4 MB RSS (650 MB cap)
- Security: `json.dumps()` prevents `::` injection; split boundary safe
- Core Brain, ExecutionBoundary, SecurityBridge, CredentialBridge, IdempotencyGuard all untouched
- No YAML template modifications
- No provider alias additions
- No new dependencies

## Files Modified

1. `mini_kio/automation/step_runner.py` — `_call_boundary()` fix + `_ACTION_MAP` expansion
2. `tests/test_p1_contract_fix.py` — 6 regression tests (new file)
3. `tests/post_p1_template_eval.py` — template evaluation script (new file)

## Next Priority

Add the highest-impact provider to `APP_CAPABILITIES`. **ai_reasoning** (46 templates, 75% of ROUTING_WORKS) is the clear first target — it only needs an `APP_CAPABILITIES` entry and a handler that delegates to `ask_llm()`.
