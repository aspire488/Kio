# Gate 3 Final Operational Wiring

## Architecture

### Ingress Flow (before)

```
Telegram input → route() → dispatch_channel_input() → handle_command()
                                                          └→ _ai_fallback() → "I don't know"
```

### Ingress Flow (after)

```
Telegram input → route() → dispatch_channel_input()
                              │
                              ├─ Deterministic fast-path: handle_command()
                              │   (open, close, search, play, multi-step, etc.)
                              │
                              └─ Gate 3 orchestration pipeline (when _gate3_eligible):
                                   intent_classifier.classify(text)
                                       → intent_validator.validate(classification)
                                       → conversation_orchestrator.orchestrate(validated)
                                       → runtime_handoff.handle_handoff(orchestration)
                                           └→ execute_action() or CONVERSATIONAL_ONLY
```

## Modified Files

### `mini_kio/core/runtime.py`
- **New function `_route_via_orchestration(text)`** — Runs the full Gate 3 pipeline:
  1. `IntentClassifier.classify(text)` — heuristic/JSON-based intent extraction
  2. `IntentValidator.validate(classification)` — safety and structural validation
  3. `ConversationOrchestrator.orchestrate(validated)` — confirmation gating, state machine
  4. `RuntimeHandoff.handle_handoff(orchestration)` — veto checks, execution dispatch
- Pipeline instances are lazy-initialized and stored on the runtime singleton as `_gate3_pipeline`
- Orchestrator state persists across invocations (confirmation lifecycle)
- **Modified `dispatch_channel_input()`**:
  - Emits `orchestration_entry` trace event before any dispatch
  - Calls `handle_command()` as deterministic fast-path
  - If result has `_gate3_eligible: True`, falls through to `_route_via_orchestration()`
  - Context tracking preserved for both paths

### `mini_kio/core/command_router.py`
- **Modified `_ai_fallback()`** — Sets `_gate3_eligible: True` on the final "I don't understand" return dict, signaling to `dispatch_channel_input` that the Gate 3 pipeline should handle it.

## New Runtime Trace Events

| Event | Emitted By | Fields |
|-------|-----------|--------|
| `orchestration_entry` | `dispatch_channel_input` | channel, user_id, text_len, runtime |
| `intent_classification` | `_route_via_orchestration` | text_len |
| `validator_result` | `_route_via_orchestration` | is_safe, intent_type |
| `orchestration_state` | `_route_via_orchestration` | state |
| `handoff_result` | `_route_via_orchestration` | state, has_pending |

## Preserved Guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| Runtime veto authority | `RuntimeHandoff` checks `SafetyState.LOCKDOWN/EMERGENCY` before dispatch |
| Restricted-target blocking | `IntentValidator` rejects forbidden targets/actions; `execution_boundary` has additional checks |
| Degraded-state blocking | `RuntimeHandoff` blocks executable handoff when provider degraded |
| Fail-closed behavior | All pipeline errors return `success=False`; orchestrator resets state on exception |
| Confirmation enforcement | Orchestrator state machine requires explicit confirmation for low-confidence or destructive actions |
| Conversational isolation | `RuntimeHandoff` returns `CONVERSATIONAL_ONLY` for conversational intents; never reaches execution |
| Validation-before-execution | Pipeline: classify → validate → orchestrate → handoff → execute |
| Runtime authority supremacy | `get_runtime()` is called at handoff time, not cached |
| Deterministic command preservation | Known commands (open, close, search, play, system, utility) still route through `handle_command` fast-path |

## Confirmation Lifecycle

Inputs `yes`, `no`, `do it` only function during active `AWAITING_CONFIRMATION` state:

- **Inside AWAITING_CONFIRMATION**: `yes`/`do it` → confirmed (EXECUTABLE_READY); `no` → refused (REFUSED)
- **Outside AWAITING_CONFIRMATION**: treated as normal conversational input (CONVERSATIONAL_ONLY)

## Conversational Fallthrough Prevention

Inputs like "Tell me about KIO" and "How does runtime authority work" no longer produce parser failure responses:

1. `handle_command` → `_ai_fallback` → no knowledge/LLM match → returns `{success: False, _gate3_eligible: True}`
2. `dispatch_channel_input` detects `_gate3_eligible` flag → routes to `_route_via_orchestration`
3. Pipeline classifies as INFORMATIONAL/CONVERSATIONAL → `RuntimeHandoff` returns `CONVERSATIONAL_ONLY` with the original text

## Regression Tests

**File**: `tests/gate3/test_runtime_wiring.py` (20 tests total)

### TestRuntimeWiring (7 tests — existing, preserved)
- test_validated_handoff_success
- test_veto_in_emergency_mode
- test_confirmation_enforcement
- test_unvalidated_intent_rejection
- test_conversational_isolation
- test_malformed_payload_rejection
- test_audit_metadata_generation

### TestGate3PipelineIntegration (13 tests — new)
| Test | Scenario | Coverage |
|------|----------|----------|
| test_conversational_prompt_does_not_fall_through | "Tell me about KIO" | Conversational fallthrough |
| test_conversational_routing | "Hello, how are you?" | Conversational isolation |
| test_informational_prompt_routes_safely | "How does runtime authority work" | Informational fallthrough |
| test_executable_prompt_classification | "open notepad" | Executable classification |
| test_executable_prompt_requires_confirmation | "open something_unknown" | Low-confidence gating |
| test_yes_confirms_outside_state_is_conversational | "yes" alone | Confirmation isolation |
| test_do_it_confirms_outside_state_is_conversational | "do it" alone | Confirmation isolation |
| test_no_outside_confirmation_is_conversational | "no" alone | Confirmation isolation |
| test_confirmation_lifecycle_full | executable → await → yes → execute | Full lifecycle |
| test_confirmation_rejection | executable → await → no → refuse | Rejection |
| test_restricted_target_rejected | "open explorer.exe" | Validator safety |
| test_ai_fallback_unknown_returns_gate3_eligible | Unknown input | Gate3 flag contract |

### TestDispatchChannelInputIntegration (1 test — new)
| Test | Scenario | Coverage |
|------|----------|----------|
| test_gate3_eligible_routes_to_orchestration | Mock handle_command returns `_gate3_eligible` | End-to-end routing |

## Compile Results

```
ALL FILES COMPILE SUCCESSFULLY
```

Files: runtime.py, command_router.py, execution_boundary.py, app_operator.py, file_operator.py
Gate 3 modules: intent_models.py, intent_classifier.py, intent_validator.py, conversation_models.py, conversation_orchestrator.py, runtime_contracts.py, runtime_handoff.py

## Remaining Operational Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Orchestrator confirmation state persists across conversations | Low | Only AWAITING_CONFIRMATION state has any gating effect; all non-trigger inputs reset to CONVERSATIONAL |
| Pipeline instances stored on runtime as dict | Low | No serialization issues; recreated on runtime restart |
| Heuristic classifier has max confidence 0.7 | Low | All executable prompts gate through confirmation (requires 0.8+ for auto-approval); users must confirm |
| No LLM integration in pipeline yet | Medium | Pipeline handles CONVERSATIONAL/INFORMATIONAL gracefully (echoes input); LLM integration is Gate 4 scope |
