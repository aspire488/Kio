# LEGACY_REACHABILITY_AUDIT.md
# Legacy and Dead Code Reachability
# =================================

## METHODOLOGY
For each suspected dead/legacy code location, trace whether it is reachable
from any active execution path.

---

## FINDINGS

### L-001: _reply_greeting() method
**File:** `mini_kio/core/pipeline/__init__.py:7815-7830`
**Status:** DEAD CODE — not called from any active path
**Evidence:**
- `_exec_conversation()` greeting template calls `render_social_reply()` first
- If that fails, falls through to `_chat_converse()` (LLM)
- If that fails, falls through to hardcoded "Hey! KIO here"
- `_reply_greeting()` is defined but never called
**Reachability:** UNREACHABLE — no call path reaches it
**Recommendation:** Remove in Phase 6

### L-002: Old entity detection patterns in topic_classifier.py
**File:** `mini_kio/media/intelligence/topic_classifier.py`
**Status:** FUNCTIONAL BUT LARGE
**Evidence:**
- 9 keyword banks with 200+ keywords
- Still used by media intelligence for topic classification
- Could be replaced with semantic classification
**Reachability:** REACHABLE — called from media intelligence pipeline
**Recommendation:** Phase 2 semanticization (not removal)

### L-003: _CORRECTION_PREFIX_RE2 (duplicate correction stripping)
**File:** `mini_kio/core/pipeline/__init__.py:~1470`
**Status:** REDUNDANT — _CORRECTION_PREFIX_RE already handles comma-separated corrections
**Evidence:**
- _CORRECTION_PREFIX_RE matches "no, open it in chrome"
- _CORRECTION_PREFIX_RE2 matches "no open it in chrome" (no comma)
- Both do the same thing with slightly different regex
**Reachability:** REACHABLE — fallback when comma version doesn't match
**Recommendation:** KEEP — handles both comma and no-comma corrections legitimately

### L-004: Legacy KIO runtime initialization
**File:** Various bootstrap files
**Status:** FUNCTIONAL — current architecture
**Reachability:** REACHABLE — startup path
**Recommendation:** KEEP — this IS the current architecture

### L-005: Old media fallback patterns in media_manager.py
**File:** `mini_kio/media/media_manager.py`
**Status:** FUNCTIONAL — fallback when context intelligence fails
**Evidence:**
- MediaContextIntelligence wraps the discovery flow
- Old fallback patterns run when intelligence raises exception
**Reachability:** REACHABLE — exception fallback path
**Recommendation:** KEEP — legitimate fallback, but could be simplified

---

## LEGACY CODE SUMMARY

| Item | Status | Reachable? | Action |
|------|--------|------------|--------|
| _reply_greeting() | DEAD | No | Remove (Phase 6) |
| topic_classifier keywords | FUNCTIONAL | Yes | Semanticize (Phase 2) |
| _CORRECTION_PREFIX_RE2 | REDUNDANT | Yes | Keep (legitimate fallback) |
| Old media fallback | FUNCTIONAL | Yes | Keep (exception fallback) |

**Dead/unreachable code found:** 1 item (_reply_greeting)
**Legacy but reachable:** 3 items (functional fallbacks)
**False positives:** 0
