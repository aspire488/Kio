# Gate 1 — Activation-Path Preparation Audit

## Scope
Prepare runtime-owned activation governance for future fist-based camera activation. **No** gesture recognition, camera capture, OpenCV, or autonomous loops in this phase.

References: KIO Architecture v1.1, `GATE0_ENGINEERING_AUDIT.md`, `GATE1_EXECUTION_PLAN.md`, `RUNTIME_ARCHITECTURE_SNAPSHOT.md`, Telegram stabilization audit.

Offline validation: `gate1_activation_validation.py` — **7/7 PASS**.

---

## 1. Activation-Path Architecture Audit

### Current state (before this phase)
| Capability | Status |
|------------|--------|
| Observer registry (manual enable/health) | Gate 0 complete |
| Channel dispatch (Telegram) | Gate 1 complete |
| Activation lifecycle | **Missing** |
| Activation gating | **Missing** |
| Camera observer surface | **Missing** |

### After groundwork
| Capability | Status |
|------------|--------|
| Activation state machine (`activation_idle` / `activation_active`) | **Added** |
| Runtime-owned signal API | **Added** |
| Observer kind discrimination (`general` vs `activation`) | **Added** |
| Camera observer stub (disabled, no hardware) | **Added** |
| Bootstrap preparation hook | **Added** |

### Orthogonal state planes

```text
PROCESS LIFECYCLE (runtime.state)     ACTIVATION (runtime.activation_state)
init → ready → idle/running → stopped   activation_idle ⇄ activation_active
```

Telegram channel `running` and activation `idle` may coexist. Activation does not replace or bypass process lifecycle.

---

## 2. Proposed Activation Lifecycle Model

```text
activation_idle
  │  observer emits signal (never transitions directly)
  ▼
runtime.submit_activation_signal()
  │  gating: runtime up, observer enabled+ready, state idle
  ▼
activation_active  (interaction session)
  │  release_activation() / future idle timeout
  ▼
activation_idle
```

**Future (not implemented):** `gesture_candidate` signal from camera observer after vision phase; session idle timeout using `_ACTIVATION_SESSION_TIMEOUT_S` (300s constant defined, not enforced).

---

## 3. Idle / Active Transition Semantics

| Transition | Trigger | Owner |
|------------|---------|-------|
| `idle → active` | `submit_activation_signal()` after gating pass | runtime |
| `active → idle` | `release_activation(reason)` | runtime |
| Invalid transition | Raises + `activation_invalid_transition` trace + integrity record | runtime |

**Rejected signals** (no state change): runtime stopped, observer disabled, wrong kind, already active, unknown signal type.

**Signal types (preparation):** `manual`, `test`, `gesture_candidate` (reserved for future camera path).

---

## 4. Observer Ownership / Governance Structure

```text
┌─────────────────────────────────────────────────────────┐
│ RUNTIME                                                  │
│  observers{} · activation_state · gating · traces        │
└───────────────────────────┬─────────────────────────────┘
                            │ register (disabled default)
┌───────────────────────────▼─────────────────────────────┐
│ ACTIVATION OBSERVER (e.g. camera_activation)             │
│  kind=activation · observer_type=camera                  │
│  enabled=false · health=inactive                         │
│  NO capture loop · NO lifecycle ownership                │
└───────────────────────────┬─────────────────────────────┘
                            │ future: submit_activation_signal only
                            ▼
                      activation.py (governance)
```

| Rule | Enforcement |
|------|-------------|
| Observers bounded | `_RUNTIME_OBSERVER_LIMIT` (8) |
| No auto-start | `enabled=False` at registration |
| No direct activation | Only `submit_activation_signal` mutates activation state |
| Isolated by kind | `kind=activation` required for signals |
| Manual enable | `set_runtime_observer_enabled(name, True)` |

---

## 5. Lightweight Camera-Observer Preparation Plan

**Now (this phase):**
- `mini_kio/observers/camera_activation_observer.py` — registration stub only
- Registered at bootstrap via `prepare_activation_groundwork()`
- `describe_prepared_capabilities()` documents future contract

**Next phase (camera integration, not now):**
1. Manual enable camera observer via runtime API or config flag
2. Single-shot or bounded sampling (no always-on loop without explicit enable)
3. Emit `gesture_candidate` signal to `submit_activation_signal` — never call operators
4. On activation active, hand off to existing channel/execution paths
5. `release_activation` on idle timeout or manual exit

**Explicitly forbidden until architecture review:**
- OpenCV / MediaPipe import at bootstrap
- Background threads without runtime governance
- Observer-owned lifecycle transitions

---

## 6. Activation Gating Strategy

`can_accept_activation_signal(observer, signal_type)` checks:

1. Runtime initialized
2. Not `shutdown_requested` / not `stopped`
3. `activation_state == activation_idle`
4. Signal type in allowed set
5. Observer registered with `kind=activation`
6. Observer `enabled=True` and `health=ready`

Double-activation blocked while session active.

---

## 7. Runtime-Safety Constraints

| Constraint | Status |
|------------|--------|
| Runtime owns activation state | Yes |
| Observers cannot bypass execution boundary | Yes (no execution in activation module) |
| No framework / event bus | Yes |
| No autonomous loops | Yes |
| Traces for signal/transition/reject | Yes |
| Integrity on invalid activation transition | Yes (`invalid_activation_transition`) |
| RAM: no heavy deps loaded | Yes (validated: no cv imports in stub) |
| Bootstrap order: runtime ready → prepare observers | Yes |

---

## 8. Files Requiring Edits (Completed)

| File | Role |
|------|------|
| `mini_kio/core/activation.py` | **NEW** — governance API |
| `mini_kio/observers/camera_activation_observer.py` | **NEW** — preparation stub |
| `mini_kio/observers/__init__.py` | **NEW** — package marker |
| `mini_kio/core/runtime.py` | Activation fields, observer `kind`/`observer_type`, bootstrap hook, snapshot |
| `snapshots/gate1_activation_preparation/gate1_activation_validation.py` | Offline harness |

**Not modified:** `execution_boundary.py`, `kio_bot.py`, operators, LLM, legacy `src/plugins/gesture_activation.py`.

---

## 9. Implementation Diff Plan (Completed)

1. Add `activation_state`, session fields on `KioRuntime`
2. Extend `register_runtime_observer(..., kind, observer_type)`
3. Implement `activation.py` state machine + gating + signal/release APIs
4. Add camera observer stub (registration only)
5. Call `prepare_activation_groundwork()` at end of `bootstrap_runtime()`
6. Extend `get_runtime_snapshot()` with activation fields
7. Add offline validation harness (7 tests)

---

## 10. Expected Runtime Behavior After Groundwork

1. `bootstrap_runtime()` → `ready` + camera observer registered **disabled**
2. `get_activation_snapshot()` → `activation_idle`
3. `submit_activation_signal("camera_activation", "manual")` → **rejected** (observer disabled)
4. `set_runtime_observer_enabled("camera_activation", True)` → observer ready
5. `submit_activation_signal(..., "manual")` → **active** session, trace `activation_state_transition`
6. `release_activation()` → **idle**
7. Telegram and execution paths unchanged; activation orthogonal to channel routing
8. No camera hardware or vision libraries loaded

---

## Remaining Risks / Next Steps

| Item | Phase |
|------|-------|
| Session idle timeout enforcement | Future activation integration |
| Camera open/capture | Future (explicit enable + bounded capture) |
| Gesture detection | Future (separate module, signal-only handoff) |
| Integration with Telegram “session started” UX | Future |
| `invalid_activation_transition` integrity threshold | Optional tuning |

**Bottom line:** Activation-path **architecture and governance** are in place. Safe to proceed to controlled camera integration when approved — not in this phase.
