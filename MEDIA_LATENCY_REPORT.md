# MEDIA LATENCY REPORT

## Date: 2026-08-25

---

## Transport Command Latency (Estimated)

### Before Remediation
| Operation | Estimated Latency | Notes |
|-----------|------------------|-------|
| Resume | ~12-15s | Full play script (10s readiness wait) + retry |
| Pause | ~1-2s | Direct video.pause() |
| Stop | ~1-2s | Direct video.pause() + seek |
| Next Track | ~3-5s | Button click + URL verification |

### After Remediation
| Operation | Estimated Latency | Notes |
|-----------|------------------|-------|
| Resume | ~0.5-2s | Dedicated resume script (500ms observation) |
| Pause | ~1-2s | Unchanged |
| Stop | ~1-2s | Unchanged |
| Next Track | ~3-5s | Unchanged |

### Latency Breakdown: Resume
```
T0: User sends "resume" via Telegram
T1: KIO receives update (~100ms)
T2: Intent classified as media_transport/resume (~50ms)
T3: Registry lookup for active session (~1ms)
T4: Provider.resume() called (~1ms)
T5: Extension execute_script("resume") sent (~50ms)
T6: playVideo() API call + 500ms observation (~500ms)
T7: State verified as PLAYING (~10ms)
T8: Telegram response sent (~100ms)
Total: ~800ms - 2s (vs ~12-15s before)
```

### Transport Commands: No Fresh Search
Per the specification, transport commands (pause/resume/stop/next/previous) do
NOT perform a fresh YouTube search. They operate on the existing session tab
via the browser connector extension scripts.

---

## Direct Play Latency (Estimated)

### Before/After (No Change)
| Phase | Latency | Notes |
|-------|---------|-------|
| T0→T1 | ~100ms | Telegram → KIO |
| T1→T2 | ~50ms | Intent classification |
| T2→T3 | ~200ms | YouTube API candidate search |
| T3→T4 | ~500ms | Tab open + page load |
| T4→T5 | ~1-3s | Candidate selection + click |
| T5→T6 | ~1-3s | Playback verification |
| T6→T7 | ~100ms | Response sent |
| **Total** | **~3-7s** | Unchanged — verification preserved |

---

## Native YouTube App Latency (New)
When native YouTube desktop app is used:
| Phase | Latency | Notes |
|-------|---------|-------|
| T0→T1 | ~100ms | Telegram → KIO |
| T1→T2 | ~50ms | Intent classification |
| T2→T3 | ~100ms | Native app detection (cached) |
| T3→T4 | ~500ms-2s | App launch + URL open |
| T4→T5 | ~100ms | Response sent |
| **Total** | **~1-3s** | Faster than browser, but unverified |

---

## Verification Contract
- Transport commands: State verified via extension scripts
- Direct play: Full candidate verification preserved
- Native app: Honest "Opened in YouTube app" (no false PLAYING claim)
- All operations: State consistency maintained
