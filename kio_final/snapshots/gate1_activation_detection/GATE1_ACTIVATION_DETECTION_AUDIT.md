# Gate 1 — Minimal Activation Detection Audit

## Scope
First lightweight activation-candidate pipeline for future fist activation. **No** ML, MediaPipe, frame queues, or background workers.

References: Architecture v1.1, camera integration audit, activation-path audit, Gate 1 plan.

Offline validation: `gate1_activation_detection_validation.py` — **6/6 PASS**.

---

## 1. Lightweight Heuristic Strategy

**Heuristic:** `center_darkness` (non-ML proxy for fist/hand near lens)

| Step | Operation |
|------|-----------|
| 1 | Convert frame to grayscale |
| 2 | Compare mean brightness: center ROI (30–70%) vs full frame |
| 3 | Require `outer_mean - center_mean >= 12` and `center_std >= 4` |
| 4 | Produce `score` in [0, 1] from delta |

**Not claimed:** fist recognition, pose estimation, or reliable gesture ID.

**Optional:** `emit_signal=False` for dry-run analysis without activation.

---

## 2. Bounded Polling / Detection Flow

```text
[manual] poll_activation_candidate()
  → capture_and_analyze(analyze_frame_heuristic)   # one frame, then discard
  → if not candidate: return
  → if cooldown active: return (candidate true, signal suppressed)
  → submit_activation_signal(observer, "gesture_candidate", detail=analysis)
  → runtime gating → activation_active (if allowed)
```

**Limits preserved:**
- `CAMERA_MAX_FRAMES_PER_POLL` / session frame cap unchanged
- 2s cooldown between emitted signals (`activation_last_candidate_emitted_ms`)
- No background loop

---

## 3. Activation-Candidate Emission Flow

```text
camera_open (manual)
  → enable_camera_observer()
  → open_camera_session()
  → poll_activation_candidate()        # explicit only
       → gesture_candidate + detail
       → activation.submit_activation_signal()
       → activation_idle → activation_active
  → [interaction]
  → release_activation() → camera release (existing)
```

Observers **never** call `submit_activation_signal` directly — only `activation_detection.poll_activation_candidate`.

---

## 4. Runtime Gating Behavior

`submit_activation_signal` existing gates still apply:

- Runtime not stopped
- Activation state idle
- Observer enabled + ready + kind=activation
- Valid signal type (`gesture_candidate` already registered)

Detection adds **cooldown** before signal emission to prevent poll spam.

---

## 5. Failure-Isolation Strategy

| Failure | Behavior |
|---------|----------|
| Camera not open | Poll returns failure; no signal |
| Capture fail | Camera → error, handle released |
| Analysis exception | Camera error trace; no activation |
| Signal rejected (gates) | `signal_emitted=false`, runtime unchanged |
| Heuristic false negative/positive | Acceptable at this phase |

Telegram and process lifecycle unaffected.

---

## 6. Files Edited

| File | Change |
|------|--------|
| `mini_kio/core/activation_detection.py` | **NEW** — heuristic + poll pipeline |
| `mini_kio/core/camera_runtime.py` | `capture_and_analyze()` |
| `mini_kio/core/runtime.py` | `activation_last_candidate_emitted_ms` |
| `mini_kio/observers/camera_activation_observer.py` | `poll_activation_candidate()` |
| `snapshots/gate1_activation_detection/gate1_activation_detection_validation.py` | Harness |

---

## 7. Implementation Diff Plan (Completed)

1. Add `analyze_frame_heuristic()` — center-darkness, no ML
2. Add `capture_and_analyze()` — single frame, immediate discard
3. Add `poll_activation_candidate()` — poll + optional signal + cooldown
4. Wire observer wrapper `poll_activation_candidate()`
5. Trace events: `activation_candidate_polled`, `activation_candidate_signal`, `camera_frame_analyzed`
6. Offline tests with synthetic frames + mocked capture

---

## 8. Expected Runtime Behavior

1. Boot unchanged — no auto detection
2. Manual: enable → open camera → `poll_activation_candidate()`
3. Uniform scene → `candidate: false`
4. Dark-center scene → `candidate: true` → `gesture_candidate` → `activation_active` (if gates pass)
5. Second immediate poll → candidate may be true but `signal_emitted: false` (cooldown)
6. `poll_activation_candidate(emit_signal=False)` → analysis only

---

## Manual Flow

```python
from mini_kio.core.runtime import bootstrap_runtime
from mini_kio.observers.camera_activation_observer import (
    enable_camera_observer, open_camera_session,
    poll_activation_candidate, close_camera_session,
)
from mini_kio.core.activation import release_activation

bootstrap_runtime()
enable_camera_observer()
open_camera_session()
poll_activation_candidate()   # fist near lens may trigger activation
release_activation()
close_camera_session()
```

---

## Remaining / Future

| Item | Phase |
|------|-------|
| Tune heuristic thresholds on real camera | Calibration pass |
| True fist/gesture model | Later (if needed) |
| Auto idle timeout on activation session | Activation stabilization |
| Telegram notify on activation | Channel integration |

**Bottom line:** First controlled candidate → signal → activation path is live, bounded, and runtime-governed without ML infrastructure.
