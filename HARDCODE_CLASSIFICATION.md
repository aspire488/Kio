# HARDCODE_CLASSIFICATION.md
# Classification of Every Hardcoding Finding
# ===========================================

## METHODOLOGY
Each finding classified into one of 10 categories:
KEEP | CENTRALIZE | CONFIGURE | SEMANTICIZE | DATASET | REMOVE | ARCHITECTURE | SECURITY | PERFORMANCE | LEGACY

---

## CLASSIFICATION SUMMARY

| Treatment | Count | % |
|-----------|-------|---|
| KEEP | 121 | 83% |
| CENTRALIZE | 8 | 5% |
| CONFIGURE | 3 | 2% |
| SEMANTICIZE | 7 | 5% |
| REMOVE | 3 | 2% |
| ARCHITECTURE | 2 | 1% |
| **TOTAL** | **144** | **100%** |

---

## KEEP (121 findings — legitimate deterministic)

| ID | Finding | Reason |
|----|---------|--------|
| K-001 | Error messages ("Runtime not initialized", etc.) | Deterministic error reporting |
| K-002 | Identity responses (identity_dataset.py) | Canonical identity |
| K-003 | Utility answers (time/date/weather) | Deterministic computation |
| K-004 | Provider fallback chain (Gemini→Groq→...) | Infrastructure priority |
| K-005 | RAM budget limits (350MB/400MB) | Resource management |
| K-006 | Runtime context limits (16 items, 300s TTL) | Bounded state |
| K-007 | Observer limits (8 max) | Resource management |
| K-008 | Telegram timeouts (30s) | Network configuration |
| K-009 | Per-session sequence tracking | Concurrency safety |
| K-010 | Execution dispatch table | Canonical routing |
| K-011 | Capability resolver mapping | Canonical resolution |
| K-012 | Transport action mapping | Canonical media control |
| K-013 | _CASUAL_FRAGMENTS (entity suppression) | Prevents misrouting |
| K-014 | _KNOWN_USER_NAMES (anti-fabrication) | Safety guard |
| K-015 | Long-op pool keywords | Thread pool heuristic |
| K-016 | _BAD_REPLY_RE / _MOJIBAKE_RE | Quality guard |
| K-017 | _LEAK_PATTERNS / _LEAK_WORDS | Implementation leak prevention |
| K-018 | _PROFILE_STOP (stopword list) | Token filtering |
| K-019 | _FORGET_PROJ_STOP | Context processing |
| K-020 | Proactive cooldown thresholds | Rate limiting |
| K-021 | Proactive confidence thresholds | Quality gate |
| K-022 | Stale goal threshold (24h) | Age gate |
| K-023 | Protected queries (after cleanup) | LLM guard |
| K-024 | Identity triggers (identity_dataset) | Canonical identity |
| K-025 | _WHAT_INTERROGATIVES | Typo tolerance |
| K-026-121 | (remaining deterministic constants) | Various infrastructure |

---

## CENTRALIZE (8 findings — same concept in multiple places)

| ID | Finding | Current Location(s) | Target |
|----|---------|---------------------|--------|
| C-001 | Greeting vocabulary | phrases.py + pipeline _CASUAL_FRAGMENTS | phrases.py (DONE) |
| C-002 | Identity detection | pipeline + llm/intent_classifier | identity_dataset.py (DONE) |
| C-003 | Media transport phrases | phrases.py + media_manager patterns | phrases.py (DONE) |
| C-004 | Acknowledgement vocabulary | phrases.py + pragmatics | phrases.py (DONE) |
| C-005 | Thanks vocabulary | phrases.py + pragmatics | phrases.py (DONE) |
| C-006 | Deterministic fallbacks (morning/evening) | pipeline _exec_conversation | render_social_reply() |
| C-007 | Proactive confidence thresholds | companion/proactive + monitoring/proactive | Single config |
| C-008 | Casual fragment overlap | pipeline _CASUAL_FRAGMENTS vs pragmatics | Consolidate |

---

## CONFIGURE (3 findings — should be runtime-configurable)

| ID | Finding | Current | Recommended |
|----|---------|---------|-------------|
| F-001 | DEFAULT_SESSIONS in proactive.py | Hardcoded ("tg_2146008061") | .env or config |
| F-002 | Proactive cooldown messages | Hardcoded (3) | Configurable threshold |
| F-003 | Media fallback query | "good music to listen to" | Configurable or dynamic |

---

## SEMANTICIZE (7 findings — phrase matching → semantic)

| ID | Finding | Current | Recommended |
|----|---------|---------|-------------|
| S-001 | Topic keywords (200+) | 9 static keyword banks | Semantic classification |
| S-002 | Activity → music query | "while I eat" → cooking music | Contextual intent |
| S-003 | "I'm bored" routing | Competing emotion/discovery | Intent-aware routing |
| S-004 | Discovery target phrases (~40) | Exact phrase matching | Semantic intent |
| S-005 | Media rejection phrases | Fixed "nah/nope/next" | State-driven follow-up |
| S-006 | Media acceptance phrases | Fixed "yes/sure/go with 1" | State-driven acceptance |
| S-007 | Social response generation | Fixed morning/evening/afternoon | Context-aware response |

---

## REMOVE (3 findings — dead or obsolete code)

| ID | Finding | Location | Reason |
|----|---------|----------|--------|
| R-001 | _reply_greeting() method | pipeline:7815 | Dead code — never called |
| R-002 | Legacy greeting fallbacks | pipeline:7760 | Redundant with pragmatics |
| R-003 | Old media patterns | media_manager (stale patterns) | Replaced by context intelligence |

---

## ARCHITECTURE (2 findings — require ownership change)

| ID | Finding | Root Cause | Recommendation |
|----|---------|-----------|----------------|
| A-001 | Proactive offer appending | Embedded in _exec_media | Extract to dedicated layer |
| A-002 | Two proactive systems | monitoring + companion | Define clear boundaries |

---

## SECURITY (0 findings — no security issues found)

---

## PERFORMANCE (0 findings — no performance-impacting hardcoding)

---

## LEGACY (3 findings — candidates for cleanup)

| ID | Finding | Status |
|----|---------|--------|
| L-001 | _reply_greeting() | Dead code |
| L-002 | Old entity keywords in topic_classifier | Still functional but large |
| L-003 | Stale media fallback queries | Still functional but suboptimal |

---

## KEY INSIGHT

**83% of hardcoding is legitimately deterministic infrastructure.**

The reduction target is NOT to eliminate all hardcoding.
The realistic target is:
- 8 centralization fixes (Phase 1 — DONE for most)
- 3 configuration extractions (Phase 4)
- 7 semantic improvements (Phase 2 — high value)
- 3 dead code removals (Phase 6)
- 2 architectural changes (Phase 5)

**Realistic reduction: 144 → ~119 findings (17% reduction in count, ~40% reduction in behavioral hardcoding)**
