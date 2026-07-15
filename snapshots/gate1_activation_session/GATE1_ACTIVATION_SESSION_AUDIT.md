# Gate 1 — Activation Session Stabilization Audit

## Scope
Stabilize runtime-owned activation-session lifecycle after candidate detection. No voice, UI, planners, or background loops.

References: Activation detection audit, camera integration audit, Gate 1 plan.

Offline validation: `gate1_activation_session_validation.py` — **6/6 PASS**.

---

## 1. Session Lifecycle Model

```text
activation_idle
  │  submit_activation_signal (gated)
  ▼
activation_active
  │  manual_release | session_timeout | runtime_shutdown
  ▼
activation_releasing
  │  cleanup (camera release, context trace)
  ▼
activation_idle
```

**Implemented states:** `activation_idle`, `activation_active`, `activation_releasing`.

---

## 2. Timeout / Release Strategy

| Mechanism | Implementation |
|-----------|----------------|
| Timeout | Lazy check via `touch_activation_session()` — **no timer thread** |
| Default timeout | `ACTIVATION_SESSION_TIMEOUT_S` (env, default 300, min 5) |
| Per-runtime override | `runtime.activation_session_timeout_s` set at bootstrap |
| Expiry action | `release_activation("session_timeout")` full releasing path |
| Manual release | `release_activation(reason)` |
| Shutdown | `force_release_activation()` from `request_shutdown` / `mark_stopped` |

**Touchpoints (timeout check):**
- `get_activation_snapshot()`
- `can_accept_activation_signal()` / `submit_activation_signal()`
- `dispatch_channel_input()`
- `poll_activation_candidate()` (via detection module)

---

## 3. Active-Session Semantics

While `activation_active`:
- `session_id` monotonic per session
- `started_at_ms`, `elapsed_ms`, `remaining_ms` in snapshot
- New signals rejected (`Activation not idle`)
- Camera cleanup on release (not held indefinitely)

While `activation_releasing`:
- Short-lived transitional state
- Cleanup runs before return to idle
- Stuck releasing completed by second `release_activation` call

---

## 4. Runtime Gating (Unchanged + Session)

Existing gates preserved:
- Runtime not stopped
- Observer enabled + ready
- Valid signal types

Session gates added:
- Only `activation_idle` accepts new signals
- Active session expired on touch if `elapsed >= timeout`

---

## 5. Deterministic Idle Return

`release_activation()` always ends in `activation_idle`:

1. `activation_session_releasing` trace
2. Transition → `activation_releasing`
3. `_perform_activation_cleanup()` — `release_camera_if_open`
4. Transition → `activation_idle`

Idempotent: release while idle → success, no-op.

---

## 6. Failure-Isolation Strategy

| Event | Behavior |
|-------|----------|
| Cleanup exception | Logged; state still advances to idle |
| Timeout during Telegram use | Session ends; channel may still run |
| Shutdown mid-session | `force_release_activation` + camera release |
| Double release | Safe / idempotent |

---

## 7. Files Edited

| File | Change |
|------|--------|
| `mini_kio/core/activation.py` | RELEASING state, timeout, releasing path, force_release |
| `mini_kio/core/config.py` | `ACTIVATION_SESSION_TIMEOUT_S` |
| `mini_kio/core/runtime.py` | timeout field, touch on dispatch, shutdown release |
| `mini_kio/core/activation_detection.py` | touch before poll |
| `snapshots/gate1_activation_session/gate1_activation_session_validation.py` | Harness |

---

## 8. Expected Runtime Behavior

1. Session starts → `active` with `remaining_ms` visible in snapshot
2. After timeout (lazy check) → `releasing` → `idle`, camera released
3. `release_activation("manual")` → same path
4. Ctrl+C / shutdown → `force_release_activation` → idle
5. No background CPU while idle (touch-only timeout)

---

## Env

```env
ACTIVATION_SESSION_TIMEOUT_S=300
```

---

## Bottom Line

Activation sessions are bounded, explicitly released, and return deterministically to idle without autonomous timer threads. Ready for live tuning of timeout and future interaction features — not in this phase.
