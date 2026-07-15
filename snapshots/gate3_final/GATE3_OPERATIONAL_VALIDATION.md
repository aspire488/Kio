# Gate 3 Operational Validation: AI Integration & Containment

## 1. Operational Readiness Checklist
Before beginning manual validation, ensure the following checkpoints are verified:
- [ ] **Runtime Startup:** System initializes to `READY` state with active Resource Guards.
- [ ] **Degraded State:** Provider Manager correctly handles simulated outages and cooldowns.
- [ ] **Conversational Isolation:** Raw LLM outputs are confined to the advisory conversation layer.
- [ ] **Confirmation Gating:** Destructive or low-confidence intents trigger the `AWAITING_CONFIRMATION` state.
- [ ] **Runtime Veto:** `LOCKDOWN` or `EMERGENCY` states correctly block validated executable handoffs.
- [ ] **Context Boundaries:** Context retrieval is strictly read-only and sanitizes inputs.
- [ ] **Audit Integrity:** All handoff attempts generate deterministic `ExecutionAuditMetadata`.
- [ ] **Stability:** System maintains state through multi-turn dialogue without context leakage.

## 2. Operational Safety Assertions
The system MUST adhere to these safety properties during validation:
- **No Shortcuts:** LLM providers cannot bypass the Validator or Orchestrator.
- **No Implicit Authority:** Generic confirmations (e.g., "yes") only execute if a pending action is active.
- **No Stale Execution:** Confirmed actions must be dispatched immediately; expired states must be cleared.
- **No Authority Leakage:** The `ContextManager` must never have access to `execute_action`.
- **Closed-Failure:** Any malformed orchestration payload must result in a `MALFORMED_PAYLOAD` rejection.

## 3. Manual Validation Stages

### Stage 1: Static & Runtime Startup
- **Goal:** Verify system bootstrap and isolation.
- **Tests:** Verify `READY` state, check registered providers, verify zero-authority context layer.

### Stage 2: Conversational Validation
- **Goal:** Verify safe dialogue and informational routing.
- **Tests:** Send standard greetings, ask informational questions, verify `CONVERSATIONAL_ONLY` audit classification.

### Stage 3: Executable Validation
- **Goal:** Verify the safe intent extraction and handoff chain.
- **Tests:** Request "open notepad", verify confirmation gating (destructive), verify `EXECUTABLE_READY` state, verify final runtime dispatch.

### Stage 4: Degraded-State Validation
- **Goal:** Verify survivability during provider outages.
- **Tests:** Simulate provider timeout storm, verify circuit breaker activation, verify fallback to `DEGRADED_BLOCK` and conversational fallback.

### Stage 5: Long-Session Observation
- **Goal:** Verify resource guarding and stability.
- **Tests:** Conduct 20+ turn conversation, verify RAM usage remains within bounds, verify context eviction (FIFO).

## 4. Operational Trace Guidance
Monitor the `runtime_trace.log` for the following events:
- `runtime_handoff_result`: Final audit classification of an interaction.
- `provider_cooldown_entered`: Circuit breaker activation.
- `exec_blocked`: Runtime-level veto of an AI intent.
- `context_eviction`: FIFO memory management.

## 5. Readiness Summary
- **Architecture:** Gate 3A through 3F implementation is complete.
- **Containment Chain:** Verified through mocked integration tests.
- **Remaining Risks:** Latent linguistic ambiguity in intent extraction (UX risk).
- **Blockers for Gate 4:** None. Operational validation is the final Gate 3 requirement.
