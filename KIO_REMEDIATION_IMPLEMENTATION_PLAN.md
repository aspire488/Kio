# KIO_REMEDIATION_IMPLEMENTATION_PLAN.md
# Concrete Implementation Plan
# ============================

## EXECUTIVE SUMMARY

Based on the complete system investigation:
- **146 hardcoding findings** total
- **121 legitimately deterministic** (83%)
- **25 actionable** (17%)
- **28 decision-makers** identified (26 canonical, 2 risk)
- **Root causes** of multi-response: proactive offer appending + proactive daemon timing

The implementation plan addresses **5 root causes** in **4 phases**.
Estimated scope: ~15 files changed, ~2 files created, ~5 files cleaned.

---

## PHASE 0: CRITICAL CORRECTNESS (COMPLETED)

### Status: ✅ DONE

| Change | File | Impact |
|--------|------|--------|
| Remove stale protected queries | conversation_governor.py | FIXED: time/date queries no longer intercepted |
| Fix exact-match protection | conversation_governor.py | FIXED: substring matching removed |
| Remove dead _IDENTITY_KEYWORDS | conversation_governor.py | CLEANED |
| Import canonical phrases | intent_classifier.py | DONE: circular dependency eliminated |
| Remove duplicate identity detection | intent_classifier.py | DONE: identity_dataset is canonical |
| Create shared phrases.py | phrases.py | DONE: single source of truth |
| Add regression tests | test_conversation_governor.py | 3 new tests passing |

**Test results:** 118/118 passing

---

## PHASE 1: CANONICAL OWNERSHIP (COMPLETED)

### Status: ✅ DONE

| Change | File | Impact |
|--------|------|--------|
| Extract canonical phrase sets | phrases.py | GREETINGS, ACKNOWLEDGEMENTS, THANKS, MEDIA_TRANSPORT centralized |
| Pipeline imports from phrases.py | pipeline/__init__.py | Single source of truth for phrase vocabulary |
| LLM intent classifier imports from phrases.py | intent_classifier.py | Circular dependency eliminated |
| Identity dataset is canonical owner | identity_dataset.py | Single canonical identity source |
| Utility detection is canonical owner | utilities.py | Single canonical utility owner |

**Remaining gap:** 1 duplicate owner (proactive systems)

---

## PHASE 2: HIGH-VALUE SEMANTICIZATION (RECOMMENDED)

### Priority: HIGH
### Estimated scope: ~8 files, ~3 days

#### 2.1 Extract Proactive Offer Layer
**Problem:** `_maybe_proactive_offer()` is embedded in `_exec_media()`, appending media offers to information_query results
**Root cause:** Information queries about media-rich topics get a media offer appended to the answer
**Fix:**
- Extract `_maybe_proactive_offer()` to `mini_kio/media/proactive_offer.py`
- Call it AFTER `_exec_media()` returns, not INSIDE it
- Add guard: suppress offer when base response is social/conversational
- Files: `pipeline/__init__.py`, new `media/proactive_offer.py`

#### 2.2 Consolidate Proactive Systems
**Problem:** Two independent proactive systems (monitoring/proactive + companion/proactive) with different triggers
**Root cause:** monitoring sends daemon messages; companion returns inline suggestions
**Fix:**
- Define clear boundaries: monitoring = stale goal notifications (daemon), companion = contextual initiative (inline)
- Add interaction-aware suppression to monitoring: suppress when user message received in last 30s
- Files: `monitoring/proactive.py`, `companion/proactive.py`

#### 2.3 Remove Dead Code
**Problem:** `_reply_greeting()` method is defined but never called
**Fix:** Delete `_reply_greeting()` from pipeline/__init__.py
**Files:** `pipeline/__init__.py`

#### 2.4 Externalize Proactive Session List
**Problem:** `DEFAULT_SESSIONS = ("tg_2146008061",)` is hardcoded in monitoring/proactive.py
**Fix:** Move to .env or config file
**Files:** `monitoring/proactive.py`, `.env`

#### 2.5 Generalize Social/Wish Responses
**Problem:** Deterministic fallbacks for "Good morning!" / "Good evening!" are hardcoded in `_exec_conversation`
**Root cause:** When pragmatics + LLM fail, hardcoded fallbacks fire
**Fix:** These are legitimate emergency fallbacks — keep but ensure they only fire when LLM is unavailable
**Files:** No change needed (already correct behavior)

---

## PHASE 3: ARCHITECTURE CLEANUP (RECOMMENDED)

### Priority: MEDIUM
### Estimated scope: ~5 files, ~2 days

#### 3.1 Media Fallback Query Externalization
**Problem:** "good music to listen to" is a hardcoded fallback query in media_manager.py
**Fix:** Make configurable or derive from conversation context
**Files:** `media_manager.py`

#### 3.2 Topic Keyword Review
**Problem:** 200+ static keywords in topic_classifier.py
**Fix:** Review and consolidate (DO NOT delete — they work correctly)
**Files:** `topic_classifier.py` (review only)

---

## PHASE 4: TESTING & VALIDATION (RECOMMENDED)

### Priority: HIGH
### Estimated scope: ~3 days

#### 4.1 Regression Test Suite
- Verify greeting classification (all cultural greetings)
- Verify media transport (pause/resume/stop/next)
- Verify confirmation/rejection (yes/nah/next/go with 1)
- Verify utility queries (time/date/weather)
- Verify identity queries
- Verify proactive offer suppression

#### 4.2 Live Telegram Validation
- Test all categories from the test matrix
- Verify no dual responses
- Verify media playback
- Verify browser operations
- Measure latency

---

## FILES AFFECTED (FINAL)

### Modified (Phase 0-1 — COMPLETED)
| File | Change |
|------|--------|
| `mini_kio/core/phrases.py` | CREATED — canonical phrase store |
| `mini_kio/core/pipeline/__init__.py` | Import phrases from shared module |
| `mini_kio/llm/conversation_governor.py` | Remove stale queries, fix matching |
| `mini_kio/llm/intent_classifier.py` | Import from phrases.py, remove duplicates |
| `tests/gate5/test_conversation_governor.py` | Add regression tests |

### Modified (Phase 2 — RECOMMENDED)
| File | Change |
|------|--------|
| `mini_kio/core/pipeline/__init__.py` | Extract _maybe_proactive_offer, remove _reply_greeting |
| `mini_kio/media/proactive_offer.py` | CREATED — extracted proactive offer layer |
| `mini_kio/monitoring/proactive.py` | Add interaction-aware suppression, externalize session list |
| `mini_kio/companion/proactive.py` | Define boundary with monitoring |

### Modified (Phase 3 — RECOMMENDED)
| File | Change |
|------|--------|
| `mini_kio/media/media_manager.py` | Externalize fallback query |
| `.env` | Add proactive session config |

### NOT Modified
| File | Reason |
|------|--------|
| `mini_kio/core/pragmatics.py` | Already canonical, works correctly |
| `mini_kio/llm/identity_dataset.py` | Already canonical, works correctly |
| `mini_kio/core/utilities.py` | Already canonical, works correctly |
| `mini_kio/media/media_manager.py` | Core media logic works correctly |
| `mini_kio/browser_connector/` | Browser automation works correctly |
| `mini_kio/runtime/browser_runtime/` | Browser runtime works correctly |
| `kio_bot.py` | Telegram transport works correctly |
| `mini_kio/core/runtime.py` | Runtime lifecycle works correctly |
| `mini_kio/core/execution_boundary.py` | Safety boundaries work correctly |

---

## EXPECTED OUTCOMES

### Before
- 146 hardcoding findings
- 1 proactive system embedded in media exec
- 2 independent proactive systems
- 1 dead code method (_reply_greeting)
- 1 hardcoded proactive session list

### After
- ~138 hardcoding findings (5% reduction in count, but more important: better architecture)
- Proactive offer extracted to dedicated layer
- Proactive systems with clear boundaries and interaction suppression
- Dead code removed
- Proactive session list configurable

### Quality Metrics
| Metric | Before | After |
|--------|--------|-------|
| Duplicate owners | 1 (proactive) | 0 |
| Dead code methods | 1 (_reply_greeting) | 0 |
| Embedded proactive logic | 1 (_maybe_proactive_offer) | 0 |
| Hardcoded config values | 1 (DEFAULT_SESSIONS) | 0 |
| Test coverage | 118/118 | 125+/125+ |

---

## RISKS

| Risk | Severity | Mitigation |
|------|----------|------------|
| Proactive offer extraction breaks existing behavior | MEDIUM | Extract carefully, preserve exact semantics |
| Monitoring proactive suppression too aggressive | LOW | Conservative 30s window, log suppressed messages |
| _reply_greeting removal causes greeting regression | LOW | Already unreachable, no impact |
| Externalizing config breaks startup | LOW | Fallback to current value |

---

## STOP CONDITION

After Phases 0-4:
- All critical bugs fixed ✅
- Canonical ownership established ✅
- Proactive systems have clear boundaries
- Dead code removed
- Tests pass
- Live Telegram validation confirms behavior

**STOP. Do not start another remediation cycle unless a concrete production defect is discovered.**
