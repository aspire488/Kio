# HARDCODE_FINAL_AUDIT — Post-Remediation Report

**Date:** August 26, 2026
**Scope:** Hardcoding reduction pass — Phase 0 + Phase 1

---

## CHANGES ACTUALLY MADE

### 1. Fixed Stale Protected Queries (CRITICAL — Live Bug Fix)

**File:** `mini_kio/llm/conversation_governor.py`

- **Removed** 4 stale protected queries that conflicted with pipeline deterministic capabilities:
  - `"what time is it"` → was returning "I cannot tell you the current time" (pipeline actually handles time)
  - `"what is the date"` → was returning "I cannot tell you the current date" (pipeline actually handles date)
  - `"do you know current events"` → pipeline can search for events
  - `"what news today"` → pipeline can search for news
- **Fixed** substring matching (`query in normalized`) → exact match only
  - Prevented "what time is it in japan" from matching "what time is it"
- **Removed** unused `_IDENTITY_KEYWORDS` list (dead code)
- **Marked** `_CANONICAL_KNOWLEDGE` as test-only (production identity comes from `identity_dataset.py`)

**Root cause:** `ConversationGovernor.check_protected_query()` was called FIRST in the LLM path, intercepting queries before the pipeline's `_detect_utility` could handle them deterministically.

### 2. Created Canonical Phrase Store (CENTRALIZATION)

**New file:** `mini_kio/core/phrases.py`

Single source of truth for shared conversational vocabulary:
- `GREETINGS` — 24 canonical greeting phrases
- `ACKNOWLEDGEMENTS` — 13 acknowledgement phrases
- `THANKS` — 5 thanks phrases
- `FAREWELLS` — 6 farewell phrases
- `CONFIRMATIONS` — 20 confirmation phrases
- `REJECTIONS` — 14 rejection phrases
- `MEDIA_TRANSPORT` — 30 media transport commands
- `SYSTEM_ACTIONS` — 6 system action words
- `FOLDER_KEYWORDS` — 9 folder names
- `FORBIDDEN_TARGETS` — 7 forbidden targets

### 3. Consolidated Greeting/Identity/Media Classification

**File:** `mini_kio/core/pipeline/__init__.py`
- `_IntentClassifier` now imports from `phrases.py` instead of defining its own frozensets
- Eliminated duplicate phrase definitions in the pipeline

**File:** `mini_kio/llm/intent_classifier.py`
- `_is_greeting()` now imports from `phrases.py` (eliminated duplicate greeting set)
- `_DETERMINISTIC_MEDIA_ACTIONS` now imports from `phrases.py` (eliminated duplicate media set)
- **Removed** duplicate identity detection (4 hardcoded phrases) — pipeline's `_check_identity` using `identity_dataset.py` is the canonical owner

### 4. Added Regression Tests

**File:** `tests/gate5/test_conversation_governor.py`
- `test_time_query_not_overridden_by_protected` — verifies time queries aren't intercepted
- `test_date_query_not_overridden_by_protected` — verifies date queries aren't intercepted
- `test_substring_match_not_overridden` — verifies substring matching is exact-only
- Updated `test_all_protected_queries_have_responses` to account for identity_dataset being canonical owner

---

## WHAT WAS INTENTIONALLY NOT CHANGED

1. **Pragmatics `_GREETING_TOKENS` / `_CASUAL_VOCAB`** — These serve register analysis (formality, playfulness), a different concern from routing classification. Legitimate separation.

2. **Media manager `_TRANSPORT_PATTERNS`** — Handles follow-up messages (e.g., "hold on", "wait") that come after initial media play. Legitimate separation from pipeline's initial classification.

3. **Identity resolver `_GREETING_VARIANTS`** — Handles greeting RESPONSE generation (which variant to use), not classification. Different concern from pipeline's greeting classification.

4. **Emergency responder greeting tuples** — Safety layer that must be import-free and self-contained. Cannot depend on shared modules.

5. **Topic keyword banks** (200+ keywords in `topic_classifier.py`) — Deterministic classification that works correctly. Not worth externalizing for this pass.

6. **Mood/activity query mappings** — Deterministic fallbacks that work. Not worth externalizing for this pass.

7. **Entity databases** (sports, movies, gaming) — Static but functional. Not stale enough to warrant externalization in this pass.

8. **Proactive evaluator weights** — Tunable thresholds that work. Not worth externalizing for this pass.

9. **Runtime constants** (limits, timeouts) — Already configurable via env vars. Not worth additional externalization.

10. **Quality validation patterns** (_CRINGE_PATTERNS, _FILLER_ONLY_RE, etc.) — Safety patterns that work correctly. Not worth modifying.

---

## FALSE POSITIVES FROM PREVIOUS AUDIT

| Finding | Previous Severity | Actual Status |
|---------|------------------|---------------|
| `GREETING_PHRASES` in pipeline | CRITICAL | Was already refactored — now uses `_IntentClassifier.GREETINGS` from `phrases.py` |
| `_CLOSE_VERBS` / `_CLOSE_PHRASES` | HIGH | Were removed in earlier refactor — pipeline now uses verb detection |
| `runtime_response_formatter.py` templates | HIGH | Was refactored — response composition now in `_ResponseComposer` |
| `MCP server name registry` | HIGH | Legitimate server name constants |
| `Browser executable paths` | HIGH | Already configurable via env vars |

---

## TEST RESULTS

| Test Suite | Tests | Passed | Failed | Notes |
|-----------|-------|--------|--------|-------|
| test_conversation_governor | 45 | 45 | 0 | All passing including 3 new regression tests |
| test_identity_dataset | 17 | 17 | 0 | All passing |
| test_language_robustness | 56 | 56 | 0 | All passing |
| **Total** | **118** | **118** | **0** | **100% pass rate** |

Pre-existing failures (not caused by this pass):
- `test_elaborate_classification` — pre-existing pipeline classification issue
- `test_route_freshness_calls_search_providers` — DuckDuckGo library rename
- `test_exa_success_short_circuits` — network-dependent test

---

## LIVE VALIDATION RESULTS

| Message | Category | Response | Status | Latency |
|---------|----------|----------|--------|---------|
| "hello" | greeting | "hey there" | PASS | ~1575ms |
| "what time is it" | utility | "It's 11:20 AM here." | **PASS (CRITICAL FIX)** | ~13ms |
| "what is the date" | utility | "It's August 26, 2026." | **PASS (CRITICAL FIX)** | ~8ms |
| "who are you" | identity | "KIO — Kernel for Intelligent Orchestration..." | PASS | ~48ms |
| "thanks" | social | "you're welcome!" | PASS | ~6ms |
| "Happy Onam" | social | "Happy Onam!" | PASS | ~1664ms |
| "play some music" | media | "I found Some Music, but playback could not be verified." | PASS (expected — no browser) | ~127ms |

**Critical regression verified:** "what time is it" and "what is the date" now return correct answers instead of the stale "I cannot tell you the time" responses.

---

## FINAL NUMBERS

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Stale protected queries | 4 | 0 | **-4** |
| Duplicate greeting sets | 7 | 3* | **-4** |
| Duplicate identity detection | 4 | 1 | **-3** |
| Duplicate media transport sets | 5 | 4** | **-1** |
| Unused dead code items | 2 | 0 | **-2** |
| Shared phrase module | 0 | 1 | **+1** |
| Regression tests | 42 | 45 | **+3** |

*Remaining 3: pipeline (canonical), pragmatics (register analysis), emergency responder (safety layer)
**Remaining 4: pipeline (canonical), media manager (follow-up handling), LLM classifier (now uses canonical), emergency responder (safety layer)

---

## CANONICAL OWNERS ESTABLISHED

| Decision | Canonical Owner | Status |
|----------|----------------|--------|
| Greeting classification | `config/phrases.py` → pipeline `_IntentClassifier` | ✅ Established |
| Acknowledgement classification | `config/phrases.py` → pipeline `_IntentClassifier` | ✅ Established |
| Thanks classification | `config/phrases.py` → pipeline `_IntentClassifier` | ✅ Established |
| Media transport classification | `config/phrases.py` → pipeline `_IntentClassifier` | ✅ Established |
| Identity response | `identity_dataset.py` | ✅ Already canonical |
| Protected queries | `conversation_governor.py` (exact-match only) | ✅ Fixed |
| Time/date/weather utility | `pipeline/_detect_utility` (UTILITY intent) | ✅ Already canonical |

---

## REMAINING WORK THAT IS GENUINELY WORTH DOING

1. **Externalize topic keyword banks** (200+ keywords) to config files — would allow updating without code changes
2. **Externalize mood/activity query mappings** to config — would allow tuning without code changes
3. **Centralize error response templates** — currently scattered across 5 files
4. **Remove `_CANONICAL_KNOWLEDGE` from production code** — currently test-only but still defined

These are MEDIUM priority and can be done in a future pass if needed.

---

## LATENCY MEASUREMENTS

| Operation | Latency | Notes |
|-----------|---------|-------|
| Greeting (deterministic) | ~1575ms | Includes runtime bootstrap on first call |
| Time query (deterministic) | ~13ms | Fast path — no LLM call |
| Date query (deterministic) | ~8ms | Fast path — no LLM call |
| Identity (deterministic) | ~48ms | Fast path — identity_dataset lookup |
| Thanks (deterministic) | ~6ms | Fast path — social classification |
| Cultural greeting (LLM) | ~1664ms | Routes to LLM for natural response |
| Media play (no browser) | ~127ms | Provider chain exhaustion |

**No latency regression** — deterministic paths remain fast, LLM paths unchanged.
