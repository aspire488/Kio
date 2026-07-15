# Gate 1 — Lightweight Camera Integration Audit

## Scope
Runtime-safe camera ownership and lifecycle for future fist activation. **No** gesture recognition, MediaPipe, heavy pipelines, or autonomous loops.

References: Architecture v1.1, Gate 0/1 plans, activation-path audit, Telegram stabilization audit.

Offline validation: `gate1_camera_validation.py` — **7/7 PASS**.

---

## 1. Camera Ownership Model

| Asset | Owner |
|-------|--------|
| Camera state machine | `camera_runtime.py` via `KioRuntime` fields |
| Capture handle | Module-private `_CAMERA_HANDLE` (single device, runtime process) |
| Open / release / poll | `camera_runtime` API only |
| Observer registration | `camera_activation_observer.py` |
| Activation session | `activation.py` (unchanged ownership) |

**Rule:** Observers call runtime camera APIs; they never hold `VideoCapture` directly.

---

## 2. Camera Lifecycle / State Model

```text
camera_off
  │  open_camera() [gated]
  ▼
camera_opening
  │  success / failure
  ▼
camera_open  ⇄  camera_error
  │  release_camera() / shutdown / activation_release
  ▼
camera_off
```

Orthogonal to:
- Process lifecycle (`runtime.state`)
- Activation session (`activation_idle` / `activation_active`)

---

## 3. Acquisition / Release Strategy

**Acquire (`open_camera`):**
1. Runtime not stopped
2. Camera state `off` or `error`
3. Camera observer **enabled** and **ready**
4. Lazy `import cv2` inside open only
5. `VideoCapture(device_index)` — default from `CAMERA_DEVICE_INDEX` env
6. Transition `opening → open` or `error` on failure

**Release (`release_camera` / `release_camera_if_open`):**
- Always `capture.release()` in `finally`
- Reset `camera_frames_polled`
- Transition to `camera_off`
- Called on: explicit close, `request_shutdown`, `mark_stopped`, `release_activation`, `disable_camera_observer`

---

## 4. Bounded Frame-Access Strategy

| Limit | Value | Purpose |
|-------|-------|---------|
| Frames per `poll_frame()` call | `CAMERA_MAX_FRAMES_PER_POLL` (1–3, default 1) | No burst ingestion |
| Frames per open session | 64 (`_CAMERA_MAX_SESSION_FRAMES`) | RAM/CPU discipline |
| Retained buffers | **None** | Metadata only (`width`, `height`, counts) |

`poll_frame()` deletes frame array immediately after reading dimensions.

**Not implemented:** continuous polling loop, gesture inference, frame queues.

---

## 5. Idle / Off Behavior

| Condition | Camera behavior |
|-----------|-----------------|
| Bootstrap | `camera_off`, no `cv2` import |
| Observer registered | Disabled by default |
| Observer enabled, camera not opened | `camera_off`, zero idle capture CPU |
| Telegram running | No automatic camera start |
| Activation idle | Camera may be off or open (manual session) |
| Activation released | `release_camera_if_open` |

---

## 6. Failure-Isolation Strategy

| Failure | Behavior | Runtime impact |
|---------|----------|----------------|
| `cv2` missing | `camera_error`, message returned | No crash |
| Device open fails | `camera_error`, integrity `camera_failure` | Observer health → degraded (via observer wrapper) |
| Poll fails | Handle released, `camera_error` | No leak |
| Shutdown with open camera | `release_camera_if_open` | Clean off |
| Invalid state transition | Trace + integrity warning | Exception to caller |

Message-level failures do not stop Telegram or process lifecycle.

---

## 7. Files Edited

| File | Change |
|------|--------|
| `mini_kio/core/camera_runtime.py` | **NEW** — lifecycle, open/release/poll |
| `mini_kio/core/config.py` | `CAMERA_DEVICE_INDEX`, `CAMERA_MAX_FRAMES_PER_POLL` |
| `mini_kio/core/runtime.py` | Camera fields, snapshot, shutdown release |
| `mini_kio/core/activation.py` | `prepare_camera_groundwork`, release on activation end |
| `mini_kio/observers/camera_activation_observer.py` | Session wrappers, enable/disable |
| `snapshots/gate1_camera_groundwork/gate1_camera_validation.py` | Harness |

---

## 8. Implementation Diff Plan (Completed)

1. Add `CameraState` and transition guards
2. Add `KioRuntime` camera fields + snapshot exposure
3. Implement lazy open, explicit release, bounded poll
4. Wire shutdown and activation-release cleanup
5. Extend observer with `open_camera_session` / `close_camera_session` / `poll_camera_frame`
6. Config env knobs for device index and poll bound
7. Offline validation harness

---

## 9. Expected Runtime Behavior After Groundwork

1. Boot → `camera_off`, observer registered disabled, no OpenCV loaded
2. `enable_camera_observer()` → observer ready, camera still off
3. `open_camera_session()` → lazy cv2, open device (or safe error if unavailable)
4. `poll_camera_frame()` → metadata only, bounded counts
5. `close_camera_session()` → hardware released, `camera_off`
6. `disable_camera_observer()` → release + disable
7. Future: `gesture_candidate` signal after poll analysis — **not in this phase**

---

## Controlled Flow (Manual)

```text
enable_camera_observer()
  → open_camera_session()
  → poll_camera_frame()   # repeat manually; no loop
  → close_camera_session()
  → disable_camera_observer()
```

Future fist path:

```text
poll → [future gesture check] → submit_activation_signal("gesture_candidate")
  → activation_active → interaction → release_activation → camera off
```

---

## Remaining Risks / Next Phase

| Item | Notes |
|------|-------|
| No automatic idle timeout on open camera | Add in gesture phase |
| Single global handle | One camera per process (correct for KIO desktop) |
| Windows-specific capture quirks | Test on target hardware |
| Gesture / fist detection | Explicitly next phase |

**Bottom line:** Camera is runtime-owned, lazy, bounded, and cleanly released. Safe to add fist recognition behind `poll_camera_frame` when approved.
