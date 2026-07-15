# MODULE OWNERSHIP

## mini_kio/core/ — CORE RUNTIME (LOCKED)

| File | Responsibility | Status |
|------|---------------|--------|
| runtime.py | Centralized runtime authority, dispatch | LOCKED |
| command_router.py | Deterministic command routing, multi-step | LOCKED |
| execution_boundary.py | Process lifecycle, action dispatch | LOCKED |
| app_operator.py | Application launch/close (Windows) | LOCKED |
| file_operator.py | File/folder operations | LOCKED |
| browser_operator.py | Browser operations (YouTube, URL open) | LOCKED |
| system_operator.py | System commands (shutdown, lock) | LOCKED |
| task_engine.py | Multi-step task execution | LOCKED |
| config.py | Configuration management | LOCKED |

## mini_kio/llm/ — LLM CONTAINMENT (Gate 4A active)

| File | Responsibility | Status |
|------|---------------|--------|
| llm_gateway.py | Provider gateway, retry, timeout, circuit breaker | Gate 3 normalized |
| provider_manager.py | Provider lifecycle, health tracking, failover | Gate 4A entrypoint |
| provider_base.py | Abstract provider contract | Gate 4A review |
| mock_provider.py | Mock provider for testing | Stable |
| models.py | LLMStatus, LLMResponse, enums | Stable |
| intent_classifier.py | Heuristic intent extraction | Gate 3 pipeline |
| intent_validator.py | Safety/structural validation | Gate 3 pipeline |
| conversation_orchestrator.py | Confirmation gating state machine | Gate 3 pipeline |
| conversation_responder.py | Safe text-only response layer | Gate 3 pipeline |

## mini_kio/runtime/ — RUNTIME INTERFACE (LOCKED)

| File | Responsibility | Status |
|------|---------------|--------|
| runtime_contracts.py | ExecutionClassification, handoff types | LOCKED |
| runtime_handoff.py | Veto checks, execution dispatch, audit | LOCKED |

## mini_kio/context/ — MEMORY LAYER (Gate 4C)

| File | Responsibility | Status |
|------|---------------|--------|
| context_manager.py | Bounded context storage and retrieval | Gate 4C |
| context_models.py | ContextEntry, memory models | Gate 4C |
| context_sanitizer.py | Injection sanitization | Gate 4C |

## mini_kio/observers/ — OBSERVERS (LOCKED)

| File | Responsibility | Status |
|------|---------------|--------|
| camera_activation_observer.py | Camera safety monitoring | LOCKED |

## tests/gate3/ — GATE 3 REGRESSION SUITE

| File | Tests | Status |
|------|-------|--------|
| test_llm_gateway.py | LLM gateway (6) | Stable |
| test_provider_reliability.py | Provider reliability (6) | Stable |
| test_intent_extraction.py | Intent classification (8) | Stable |
| test_conversation_orchestration.py | Orchestration state machine (8) | Stable |
| test_conversation_responses.py | Responder tests (16) | Stable |
| test_context_layer.py | Context layer (6) | Stable |
| test_runtime_wiring.py | Pipeline integration (20) | Stable |
| test_integration_boundaries.py | End-to-end integration (6) | Stable |
| test_operational_readiness.py | Operational readiness (6) | Stable |

## OWNERSHIP RULES

- **LOCKED** files: no changes without ARCHITECTURE_LOCK review and
  explicit Gate signoff
- **Gate 4A** active: provider_manager.py, provider_base.py only
- **Gate 4C** scope: context/* — not yet touched
- Tests must accompany every change — no exception
