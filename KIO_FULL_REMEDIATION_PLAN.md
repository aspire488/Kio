# KIO FULL REMEDIATION PLAN

**Date:** August 24, 2026
**Based on:** KIO_FULL_CAPABILITY_AUDIT.md
**Status:** PLAN ONLY — No implementation yet

---

## TABLE OF CONTENTS

1. P0 — Correctness / False-Success / Broken Execution
2. P1 — Major Capability Gaps
3. P2 — Latency and Reliability
4. P3 — Architecture Cleanup
5. P4 — Optimization / Polish

---

## P0 — CORRECTNESS / FALSE-SUCCESS / BROKEN EXECUTION

### P0-1: Research Grounding Silent Degradation

**Problem:** When research providers fail, artifacts are generated from LLM training data with NO user warning. The user gets a document that APPEARS researched but isn't.

**Current behavior:** `pipeline/__init__.py:7489-7490` catches all exceptions at debug level. `facts = ""` → LLM receives `(no retrieved facts — make the deck qualitative)` → document generated without research.

**Desired behavior:** User receives a clear indication when research grounding failed.

**Implementation approach:**
1. In `_generate_content()` (line ~7610), when `facts` is empty or providers failed, append a footer/note to the generated content or include a flag in the response metadata.
2. In `_exec_create_document()` (line ~6299), check if research was attempted and failed. If so, include a note in the response message: "(Note: Web research was unavailable for this document. Content is based on general knowledge.)"
3. Do NOT block artifact creation — still generate the document, but be truthful about grounding.

**File:** `mini_kio/core/pipeline/__init__.py`
**Functions:** `_generate_content()` (line 7493), `_research_facts()` (line 7451), `_exec_create_document()` (line 6160)
**Dependencies:** None
**Regression risk:** LOW — additive change to response text only
**Test required:** Verify message includes note when providers fail; verify no note when providers succeed
**Acceptance criterion:** User can distinguish research-grounded from non-grounded artifacts

---

### P0-2: Memory Raw Key Exposure

**Problem:** MemoryResolver renders internal fact keys to users. "Your my preferred language is Python" instead of natural response.

**Current behavior:** `memory_resolver.py:128-129` — raw fact key rendered as user-facing text.

**Desired behavior:** Natural language response using the fact value, not the key.

**Implementation approach:**
1. In `memory_resolver.py:128-129`, when rendering facts, parse the key format (`preference_language`, `favorite_color`, etc.) into natural language.
2. Apply a key→label mapping: `preference_*` → "Your preference for X", `favorite_*` → "Your favorite X", `user_name` → "Your name".
3. For unknown key formats, use a generic template: "You told me: {value}".

**File:** `mini_kio/resolvers/memory_resolver.py`
**Function:** Fact rendering around line 128-129
**Dependencies:** None
**Regression risk:** LOW — isolated to one rendering path
**Test required:** "Remember my preferred language is Python" → "What is my preferred language?" → natural response without raw key
**Acceptance criterion:** No internal keys visible to users in any recall path

---

### P0-3: ContinuityResolver Singleton Session Corruption

**Problem:** ContinuityResolver uses class-level singletons (`_state`, `_provider`, `_session_state`). Two concurrent Telegram sessions corrupt each other's continuity state.

**Current behavior:** `continuity_resolver.py:102-105` — class-level attributes shared across all instances.

**Desired behavior:** Per-session state isolation.

**Implementation approach:**
1. Convert class-level `_state`, `_provider`, `_session_state` to instance-level attributes.
2. ContinuityResolver instances should be created per-session or per-request.
3. Ensure `set_session_state()` updates instance state, not class state.
4. Verify that the media pipeline creates fresh ContinuityResolver instances per request.

**File:** `mini_kio/core/continuity_resolver.py`
**Class:** ContinuityResolver (line 101)
**Dependencies:** Must verify all callers create or access instances correctly
**Regression risk:** MEDIUM — must ensure no code depends on class-level state sharing
**Test required:** Two concurrent "Play X" → "Pause" sessions must not interfere
**Acceptance criterion:** Each session has independent continuity state

---

## P1 — MAJOR CAPABILITY GAPS

### P1-1: Research Provider Under-Utilization

**Problem:** For most user queries ("What is X?", "Latest news about Y?"), only DuckDuckGo + Wikipedia are called. Exa, Tavily, OpenAlex, arXiv are reachable only through niche research brief command.

**Current behavior:** `knowledge/retrieval_router.py:234` — `KnowledgeRouter.route()` only tries DDG then Wikipedia.

**Desired behavior:** Intelligent provider selection based on query type.

**Implementation approach:**
1. In `KnowledgeRouter.route()`, add provider selection logic:
   - Factual/entity queries → DDG + Wikipedia (current behavior, good)
   - Current news/events → DDG (freshness) + Exa (if key available)
   - Academic/technical → arXiv + OpenAlex + Wikipedia
   - Broad web search → Exa + DDG + Wikipedia
2. Add query-type detection (regex-based, not LLM) to choose provider subset.
3. Preserve fallback: if selected providers fail, fall through to DDG+Wikipedia.

**File:** `mini_kio/knowledge/retrieval_router.py`
**Function:** `route()` (line ~234), add `route_for_topic()` integration
**Dependencies:** Exa API key already configured
**Regression risk:** MEDIUM — changes default research behavior
**Test required:** "Latest AI news" → verify Exa or DDG with freshness; "Research quantum computing" → verify arXiv or OpenAlex called
**Acceptance criterion:** At least 3 providers attempted for information queries when keys available

---

### P1-2: RetrievalSynthesizer Dead Code Cleanup

**Problem:** `RetrievalSynthesizer` has Exa/Tavily/Jina methods that exist but `synthesize()` never calls them.

**Current behavior:** `retrieval_synthesizer.py:75-94` — synthesize() only calls _try_duckduckgo then _try_wikipedia.

**Desired behavior:** Either use all providers or remove dead code.

**Implementation approach:**
1. **Option A (preferred):** Wire Exa/Tavily into synthesize() — add them as Provider 0 and Provider 1 before DDG.
2. **Option B:** Remove dead methods (_try_exa, _try_tavily, _try_jina) to reduce confusion.
3. Choose based on whether synthesizer is actually used in hot paths.

**File:** `mini_kio/intelligence/retrieval_synthesizer.py`
**Function:** `synthesize()` (line 75)
**Dependencies:** None
**Regression risk:** LOW — additive or subtractive, not behavioral change
**Test required:** Verify synthesize() calls Exa/Tavily if Option A; verify no import errors if Option B
**Acceptance criterion:** No dead provider methods, or all methods actually called

---

### P1-3: Context System Consolidation Plan

**Problem:** 6 overlapping context systems with unclear ownership.

**Current state:**
- ContextManager: intended canonical, NOT yet default
- SessionState: currently default, all resolvers depend on it
- ConversationContext: legacy, embedded in SessionState
- ContinuityResolver: media pipeline entry
- ContinuityContextProvider: pending media actions
- MediaContext: media subsystem state

**Implementation approach (PHASED — not a single PR):**

**Phase 1 (safe):** Document canonical ownership
- Add docstrings to each system stating its role and whether it's canonical
- Mark legacy systems with deprecation warnings

**Phase 2 (moderate):** Wire ContextManager as default
- In Pipeline.run(), create ContextManager instead of SessionState
- Route all resolvers through ContextManager
- Preserve SessionState as thin wrapper around ContextManager for backward compatibility

**Phase 3 (risky):** Remove legacy systems
- Remove ConversationContext (absorbed by ContextManager)
- Remove duplicate PendingAction class
- Remove duplicate domain detection keywords

**File:** Multiple files (see audit Section 10)
**Dependencies:** All resolvers, media pipeline, memory system
**Regression risk:** HIGH — must preserve all cross-turn behaviors
**Test required:** All continuity examples from audit must pass
**Acceptance criterion:** Single canonical context source, no duplicate state

---

### P1-4: _GLOBAL_MEMORY_STORE Divergence

**Problem:** In-memory dict `_GLOBAL_MEMORY_STORE` can diverge from SQLite source of truth.

**Current behavior:** `memory_store.py:24` — in-memory dict accumulates unboundedly while `get_history()` reads from SQLite repo.

**Desired behavior:** Single source of truth (SQLite).

**Implementation approach:**
1. Remove `_GLOBAL_MEMORY_STORE` in-memory dict.
2. Route all reads through `MemoryRepository` (SQLite).
3. If in-memory cache is needed for performance, implement TTL-based cache with explicit invalidation on write.

**File:** `mini_kio/memory/memory_store.py`
**Variable:** `_GLOBAL_MEMORY_STORE` (line 24)
**Function:** `append()` (line 103-106), `get_history()` (line 112-114)
**Dependencies:** All memory consumers
**Regression risk:** MEDIUM — may affect read performance
**Test required:** Write → read consistency under concurrent access
**Acceptance criterion:** All memory reads return SQLite-sourced data

---

## P2 — LATENCY AND RELIABILITY

### P2-1: Remove Diagnostic Instrumentation Probes

**Problem:** 2 of 3 pre-play `get_page_info` calls are purely diagnostic — add Chrome extension round-trips with no decision value.

**Current behavior:**
- `youtube_provider.py:670-678` — pre-bootstrap probe (logged, not used)
- `youtube_provider.py:781-788` — pre-play probe (logged, not used)
- `youtube_provider.py:740-750` — post-bootstrap probe (USED for identity gate)

**Desired behavior:** Only keep probes that feed decision logic.

**Implementation approach:**
1. Remove lines 670-678 (pre-bootstrap probe) — return value not consumed.
2. Remove lines 781-788 (pre-play probe) — return value not consumed.
3. Keep lines 740-750 (post-bootstrap probe) — feeds identity gate.

**File:** `mini_kio/media/providers/youtube_provider.py`
**Lines:** 670-678, 781-788
**Dependencies:** None
**Regression risk:** LOW — removing dead diagnostic code
**Test required:** Media playback still works end-to-end
**Acceptance criterion:** 2 fewer Chrome extension round-trips per play

---

### P2-2: Replace Hard-Coded Sleeps with Polling

**Problem:** Multiple hard-coded `time.sleep()` calls add artificial latency.

**Current sleeps:**
| Location | Delay | Purpose |
|----------|-------|---------|
| `youtube_provider.py:667` | 0.3s | Page render wait |
| `youtube_provider.py:538` | 0.8s × 3 | Scrape retry |
| `youtube_provider.py:735` | 1.0s | Bootstrap retry |
| `youtube_provider.py:779` | 0.7s × 3 | Play attempt interval |
| `youtube_provider.py:1272` | 1.0s | Search results load |
| `youtube_provider.py:1112` | 1.5s | Post-navigation render |

**Implementation approach:**
1. Replace `sleep(0.3)` at line 667 with poll: `get_page_info` until `hasVideo==True` or timeout 2s.
2. Replace `sleep(0.8)` at line 538 with shorter poll: check for results presence.
3. Replace `sleep(1.0)` at line 735 with poll: check if video element exists.
4. Replace `sleep(0.7)` at line 779 with poll: `get_player_state` with shorter backoff.
5. Replace `sleep(1.0)` at line 1272 with poll: check for search results DOM.
6. Replace `sleep(1.5)` at line 1112 with poll: check page readiness.

**File:** `mini_kio/media/providers/youtube_provider.py`
**Dependencies:** Chrome Extension scripts must support polling
**Regression risk:** MEDIUM — polling must have timeout guards
**Test required:** Media playback still works; worst-case latency not increased
**Acceptance criterion:** Typical media latency reduced by ~3-4 seconds

---

### P2-3: Parallelize API Search and Browser Scrape

**Problem:** API search and browser scrape currently run serially. They can safely run in parallel.

**Current behavior:** `youtube_provider.py:529-538` — API search, then browser scrape.

**Desired behavior:** Both run concurrently, results merged.

**Implementation approach:**
1. Use `asyncio.gather()` or `concurrent.futures.ThreadPoolExecutor` to run API search and browser scrape simultaneously.
2. Merge results after both complete.
3. Add timeout to prevent one blocking the other.

**File:** `mini_kio/media/providers/youtube_provider.py`
**Lines:** 529-538
**Dependencies:** Both functions must be thread-safe (they are — pure reads)
**Regression risk:** LOW — additive parallelism
**Test required:** Media search still returns correct candidates
**Acceptance criterion:** ~500ms saved on typical path

---

## P3 — ARCHITECTURE CLEANUP

### P3-1: Document Context System Ownership

**Problem:** Unclear which context system owns what.

**Implementation approach:**
1. Add module-level docstrings to each context file stating:
   - Purpose
   - Whether canonical or legacy
   - Expected lifetime
   - Readers and writers
2. Add `# DEPRECATED` comments to ConversationContext.
3. Add `# INTENDED CANONICAL` comment to ContextManager.

**Files:** All 6 context files
**Dependencies:** None
**Regression risk:** NONE — documentation only
**Test required:** None
**Acceptance criterion:** Each context system has clear ownership documentation

---

### P3-2: Remove Dead RetrievalSynthesizer Methods

**Problem:** Exa/Tavily/Jina methods in RetrievalSynthesizer are never called.

**Implementation approach:**
1. Remove `_try_exa()` (lines 102-124)
2. Remove `_try_tavily()` (lines 126-143)
3. Remove `_try_jina()` (lines 159-189)
4. Update `synthesize()` docstring to reflect actual provider chain.

**File:** `mini_kio/intelligence/retrieval_synthesizer.py`
**Dependencies:** None
**Regression risk:** LOW — removing dead code
**Test required:** Import still works, no references to removed methods
**Acceptance criterion:** No dead provider methods in synthesizer

---

### P3-3: Remove MediaKnowledgeRouter Dead Code

**Problem:** `MediaKnowledgeRouter.is_media_query()` is hardcoded to return False — entire media knowledge routing is disabled.

**Implementation approach:**
1. Remove or comment out `MediaKnowledgeRouter` class if not used elsewhere.
2. Or implement the intended media knowledge routing if needed.

**File:** `mini_kio/knowledge/media_knowledge_router.py`
**Dependencies:** Check all references before removing
**Regression risk:** LOW — currently disabled anyway
**Test required:** No import errors
**Acceptance criterion:** No dead media knowledge routing code

---

### P3-4: Consolidate Duplicate PendingAction Classes

**Problem:** Two separate `PendingAction` classes in `conversation_context.py:22` and `context_manager.py:148`.

**Implementation approach:**
1. Keep the ContextManager version (canonical).
2. Update ConversationContext to import from ContextManager.
3. Or remove ConversationContext's version and use ContextManager's.

**Files:** `mini_kio/llm/conversation_context.py`, `mini_kio/core/context_manager.py`
**Dependencies:** All PendingAction consumers
**Regression risk:** LOW — type compatibility check needed
**Test required:** Pending action creation/resolution still works
**Acceptance criterion:** Single PendingAction class

---

## P4 — OPTIMIZATION / POLISH

### P4-1: URL Change Probe Timeout Guard

**Problem:** `_probe_url_changed()` at `youtube_provider.py:1086-1101` has 4-iteration loop with no timeout guard.

**Current behavior:** 4 × 0.75s = 3s maximum, but no overall timeout.

**Implementation approach:**
1. Add `start_time = time.time()` before loop.
2. Add `if time.time() - start_time > 4.0: break` inside loop.
3. Log timeout as warning.

**File:** `mini_kio/media/providers/youtube_provider.py`
**Function:** `_probe_url_changed()` (line 1086)
**Dependencies:** None
**Regression risk:** LOW — adds safety guard
**Test required:** Next/previous track still works
**Acceptance criterion:** Probe cannot hang beyond 4 seconds

---

### P4-2: Scraping Retry Sleep Reduction

**Problem:** 0.8s sleep between scrape retries is conservative.

**Current behavior:** `youtube_provider.py:538` — `time.sleep(0.8)` between each of 3 retries.

**Implementation approach:**
1. Reduce to 0.3s between retries.
2. Or replace with poll-based check for results DOM presence.

**File:** `mini_kio/media/providers/youtube_provider.py`
**Line:** 538
**Dependencies:** None
**Regression risk:** LOW — shorter delay
**Test required:** Media search still finds candidates
**Acceptance criterion:** ~1.5s saved on retry path

---

### P4-3: KnowledgeRouter Provider Expansion

**Problem:** Default KnowledgeRouter route only uses DDG + Wikipedia.

**Implementation approach:**
1. Add Exa as first-choice provider when `EXA_ENABLED=True`.
2. Add fallback: Exa → DDG → Wikipedia.
3. Preserve existing behavior when Exa is unavailable.

**File:** `mini_kio/knowledge/retrieval_router.py`
**Function:** `route()` (line 234)
**Dependencies:** Exa API key (already configured)
**Regression risk:** LOW — additive fallback
**Test required:** Knowledge queries still return results; Exa results improve quality
**Acceptance criterion:** 3 providers attempted for knowledge queries

---

## IMPLEMENTATION ORDER

### Phase 1: Quick Wins (Low Risk, High Impact)
1. P0-2: Memory raw key fix (isolated, ~10 lines)
2. P2-1: Remove diagnostic probes (remove dead code, ~20 lines)
3. P4-1: URL probe timeout guard (add 2 lines)
4. P4-2: Scrape retry sleep reduction (change 1 number)

### Phase 2: Correctness (Medium Risk, High Impact)
5. P0-1: Research grounding warning (add user message, ~30 lines)
6. P1-2: RetrievalSynthesizer dead code cleanup (remove ~80 lines)
7. P3-2: Dead code removal (remove ~60 lines)
8. P3-3: MediaKnowledgeRouter cleanup (remove ~20 lines)

### Phase 3: Reliability (Medium Risk, Medium Impact)
9. P0-3: ContinuityResolver singleton fix (refactor ~50 lines)
10. P2-2: Replace sleeps with polling (refactor ~100 lines)
11. P2-3: Parallelize API/scrape (add ~30 lines)
12. P1-1: Research provider expansion (add ~50 lines)

### Phase 4: Architecture (High Risk, High Impact)
13. P1-3: Context system consolidation (multi-file, ~500 lines)
14. P1-4: _GLOBAL_MEMORY_STORE removal (multi-file, ~100 lines)
15. P3-1: Documentation (documentation only)
16. P3-4: PendingAction consolidation (multi-file, ~30 lines)

---

## REGRESSION RISK MATRIX

| Change | Risk | Files Changed | Test Coverage Needed |
|--------|------|---------------|---------------------|
| P0-1: Research warning | LOW | 1 | Manual verification |
| P0-2: Memory key fix | LOW | 1 | Manual verification |
| P0-3: Singleton fix | MEDIUM | 1-2 | Concurrent session test |
| P1-1: Provider expansion | MEDIUM | 1 | Provider chain test |
| P1-2: Dead code cleanup | LOW | 1 | Import test |
| P1-3: Context consolidation | HIGH | 6+ | All continuity scenarios |
| P1-4: Memory store fix | MEDIUM | 1-2 | Read/write consistency |
| P2-1: Probe removal | LOW | 1 | Media playback test |
| P2-2: Sleep replacement | MEDIUM | 1 | Media latency test |
| P2-3: Parallel search | LOW | 1 | Media search test |
| P3-1: Documentation | NONE | 6 | None |
| P3-2: Dead code removal | LOW | 1 | Import test |
| P3-3: Router cleanup | LOW | 1 | Import test |
| P3-4: PendingAction fix | LOW | 2 | Type compatibility |
| P4-1: Timeout guard | LOW | 1 | Next/previous test |
| P4-2: Sleep reduction | LOW | 1 | Media search test |
| P4-3: Provider expansion | LOW | 1 | Knowledge query test |

---

## ACCEPTANCE TESTS

### Media Tests
```bash
# Test 1: Basic playback
Send: "Play Space Song by Beach House"
Verify: playerState==1, correct video identity

# Test 2: Pause/Resume
Send: "Play Space Song" → "Pause" → "Resume"
Verify: paused state confirmed → playing state confirmed

# Test 3: Play again
Send: "Play Space Song" → "Play it again"
Verify: same video re-played

# Test 4: Identity gate
Send: "Play Interstellar trailer"
Verify: actual trailer, not random video

# Test 5: No connector fallback
Disconnect Chrome Extension → "Play X"
Verify: graceful error, not crash
```

### Desktop Tests
```bash
# Test 1: Known app
Send: "Open Notepad"
Verify: notepad.exe process running, PID verified

# Test 2: Unknown app
Send: "Open WinRAR"
Verify: discovered via registry/Start Menu, launched

# Test 3: Website
Send: "Open ChatGPT"
Verify: browser tab opened, chatgpt.com loaded

# Test 4: Close
Send: "Open Notepad" → "Close Notepad"
Verify: process terminated

# Test 5: Reuse
Send: "Open ChatGPT" → "Open ChatGPT"
Verify: existing tab focused, not new tab
```

### Research Tests
```bash
# Test 1: Basic knowledge
Send: "What is quantum computing?"
Verify: DDG+Wikipedia results returned

# Test 2: Current events
Send: "Latest AI news"
Verify: DDG with freshness results

# Test 3: Research command
Send: "Research quantum computing"
Verify: Multiple providers invoked (Exa, Tavily, etc.)

# Test 4: Provider failure
Mock Exa timeout → "Research X"
Verify: Fallback to DDG+Wikipedia, no crash

# Test 5: All providers fail
Mock all providers → "What is X?"
Verify: LLM generates from training data WITH warning note
```

### Artifact Tests
```bash
# Test 1: Word document
Send: "Create a Word document about AI"
Verify: .docx file exists, valid binary, content present

# Test 2: Spreadsheet
Send: "Make a budget spreadsheet"
Verify: .xlsx file exists, tabular content

# Test 3: Presentation
Send: "Create a PowerPoint about robotics"
Verify: .pptx file exists, slides present

# Test 4: Research grounding
Send: "Create a report about latest AI developments"
Verify: Research attempted; if failed, warning included

# Test 5: File opening
Verify: File opens in target application after creation
```

### Memory Tests
```bash
# Test 1: Store
Send: "Remember my favorite color is blue"
Verify: Stored in SQLite

# Test 2: Recall
Send: "What is my favorite color?"
Verify: "Blue" (natural response, no raw key)

# Test 3: Forget
Send: "Forget my favorite color"
Verify: Removed from store

# Test 4: Post-forget recall
Send: "What is my favorite color?"
Verify: No result / "I don't have that stored"

# Test 5: Concurrent sessions
Two sessions simultaneously → different memories
Verify: No cross-session contamination
```

### Continuity Tests
```bash
# Test 1: Media continuity
"Play Believer" → "Pause" → "Resume" → "Play it again"
Verify: All operations work with correct context

# Test 2: Cross-turn reference
"Tell me about quantum computing" → "Tell me more about that"
Verify: "that" resolves to quantum computing

# Test 3: Topic transition
"Play Believer" → "Something calmer"
Verify: New search triggered, not "play Believer again"

# Test 4: Concurrent sessions
Two sessions with different media
Verify: Each session's continuity is independent
```

---

*End of KIO Full Remediation Plan*
