# KIO Runtime — Comprehensive Architectural Health Audit

**Date:** 2026-07-27  
**Mode:** Investigation only (no code changes)  
**Scope:** 454 first-party Python files (71,775 lines), 12,930 first-party files total  
**Method:** 5 parallel sub-agent audits + full global state inventory + dependency mapping

---

## 1. TOP 50 ARCHITECTURAL ISSUES (ranked by impact)

### Critical (10)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| 1 | **Playwright/BrowserRuntime has no shutdown path** — global event loop `_br_loop` runs forever; no cleanup on exit | `browser_operator.py:32-50`, `kio_bot.py:267-274` | Memory leak; zombie Playwright processes; crashes on restart |
| 2 | **Global mutable class state on ContinuityResolver** — `_state`, `_provider`, `_entity_memory`, `_session_state` are class-level, shared across all instances | `continuity_resolver.py:102-118,580-603` | Not thread-safe; parallel tests corrupt each other's state; state leaks across sessions |
| 3 | **Triple pronoun-resolution systems with different state stores** — `ContinuityEngine` (ContextStore), `MediaReferenceResolver` (MediaContext), `IntegrationAdapter._try_memory_resolve` (MediaEntityMemory) — stores get out of sync | `continuity_engine.py`, `media_reference_resolver.py`, `integration_adapter.py` | Pronoun resolution fails silently; "it" / "that" / "him" resolve differently depending on code path |
| 4 | **ALL answers are templated** — "Quick rundown", "Worth knowing", "Here's what I found", "emoji Subject: label" forced into every response; no natural LLM pass-through | `answer_composer.py`, `media_response_formatter.py`, `retrieval_synthesizer.py` | User always gets robotic, template-structured answers regardless of LLM capability |
| 5 | **Dual resolver instances** — each resolver is instantiated twice in both ConversationResponder and KIOOrchestrator (in `_resolvers` dict and as separate attributes) | `conversation_responder.py:128-141`, `kio_orchestrator.py:32-44` | Wasted memory; IdentityResolver & MemoryResolver called twice per request (dead code second call) |
| 6 | **`_normalize_public_result` duplicated** — identical function in `browser_operator.py:152-230` and `app_operator.py:471-537` | `browser_operator.py`, `app_operator.py` | Changes to one silently diverge from the other; inconsistent normalization |
| 7 | **`command_router.py:_route_builtin` is a 640-line monolith** — single function handles greetings, identity, search, open, close, media, sports, artifacts, telemetry, and everything else | `command_router.py:896-1536` | Impossible to reason about; minor changes risk breaking unrelated features |
| 8 | **`is_media_query()` is disabled** — returns `False` unconditionally; OMDb/TVMaze/Jikan/MusicBrainz/SportsDB providers inaccessible | `media_knowledge_router.py:19` | Media metadata providers cannot be reached from knowledge router path |
| 9 | **`is_knowledge_query()` patterns too narrow** — matches only explicit question forms; "Interstellar cast" / "Believer release date" bypass knowledge pipeline | `knowledge/retrieval_router.py:131-170` | Valid knowledge queries get treated as casual conversation |
| 10 | **5-layer intelligence fallback chain and media intelligence path are completely separate** — media queries have their own 2-step fallback ending with hardcoded "I couldn't find info" | `intelligence_router.py` vs `integration_adapter.py` | Media queries never reach the emergency responder; media fallback is a single string, not structured |

### High (20)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| 11 | **Missing typo normalizations** — `_TYPO_MAP` has only 42 entries; common typos like "hallo", "freind", "recieve", "definately" not normalized | `input_normalizer.py:19-60` | "hello friend" and "hallo freind" produce different classifications |
| 12 | **Action extraction checks regex SOURCE string, not matched text** — `if "open" in pattern` checks the pattern string itself, not the match | `intent_classifier.py:161-167` | New exec patterns without explicit "open"/"launch" words produce broken EXECUTABLE intents |
| 13 | **"can you open chrome" classified as INFORMATIONAL not EXECUTABLE** — exec_patterns require string to START with "open"/"launch"; "can you open X" matches informational keywords instead | `intent_classifier.py:17-25,29-45` | Action requests phrased as questions bypass execution pipeline entirely |
| 14 | **Media actions "pause"/"resume"/"stop"/"next"/"previous" can never be EXECUTABLE** — missing from exec_patterns (only "play"/"watch" present) | `intent_classifier.py:17-25,152` | Standalone media transport commands always classified as CONVERSATIONAL at 0.4 confidence |
| 15 | **Exact-match confirmation triggers** — "yes please" and "no thank you" don't match; treated as topic change, confirmation lost | `conversation_orchestrator.py:41,55,189` | Natural responses to "Shall I proceed?" are silently discarded |
| 16 | **Triple confirmation bridge** — three separate code paths route confirmations (orchestrator, dispatch_channel_input, MissionPipeline) | `conversation_orchestrator.py:186`, `runtime.py:1260-1272`, `mission.py:372-397` | Duplicate logic; subtle ordering differences can cause unexpected behavior |
| 17 | **Orchestration pipeline called TWICE** — MissionPipeline._handle_conversation calls _route_via_orchestration, then dispatch_channel_input also calls it again | `mission.py:332-354`, `runtime.py:1211-1255` | State mutations compounded; LLM called twice for same input |
| 18 | **Protected query substring matching is too broad** — "what time is it" matches inside long queries with length bound of +20 chars | `conversation_governor.py:228-231` | Wrong canned responses for vaguely similar queries |
| 19 | **Hard educational override bypasses classifier** — regex match reclassifies after full orchestration pipeline ran | `conversation_responder.py:329` | Layering violation; pipeline trusts classifier, then responder overrides it |
| 20 | **"Go back to conversation" / "close web" has no route handler** — no dedicated handler anywhere; only PID-based process killing exists | `command_router.py`, `continuity_resolver.py`, `browser_operator.py` | Users cannot naturally navigate back from browser to conversation |
| 21 | **`entity_state_engine.py` is a stub** — `determine_state()` always returns `RELEASED` unconditionally | `entity_state_engine.py:24-31` | All entities show as "Released" regardless of actual state |
| 22 | **`_answer_person` mechanism is fragile** — only set for "who [role] X?" queries; regex-based extraction on raw text | `integration_adapter.py:371-374,1140-1187` | Personal pronoun resolution ("his", "him") fails for non-standard question forms |
| 23 | **`_execution_summary` template rotation is context-blind** — rotates "Opened"/"Launched"/"Starting"/"Got it" by counter, not by action type | `conversation_responder.py:564-603` | "open firefox" might get "Launched firefox" even though the action was "open" |
| 24 | **`check_authority_override` is a dead no-op** — always returns None but still called | `input_normalizer.py:171-177`, `runtime.py:972` | Wasted function call on every request |
| 25 | **`_route_via_orchestration` defined twice** — first definition immediately overwritten by second | `runtime.py:896-898,913-1106` | Confusing dead code in version control |
| 26 | **`ConversationResponder` re-imported three times inside same function** — module-level import plus two function-body imports | `runtime.py:931,932,944` | Redundant imports; circular import workaround that could be restructured |
| 27 | **Core import contamination from gstack** — 4,716 TS files and 5,769 JS files in gstack/ mixed into same repo | `gstack/` | Bloated repo; CI/CD overhead; cognitive load |
| 28 | **10 duplicate browser stubs** — sessions.py, profiles.py, downloads.py, permissions.py, uploads.py, navigation.py (2/3 stubs), tabs.py (1/2 stubs), backend.py (dead protocol) | `browser/` | 8 files of dead or stubbed code |
| 29 | **`_RUNTIME_TRACKER` never cleaned** — module-level dict grows unboundedly over session lifetime | `context_manager.py:121` | Memory leak for long-running sessions |
| 30 | **`execute_capability()` is 140-line monolith** — deeply nested conditionals with duplicated PID refinement | `app_operator.py:1693-1833` | Hard to maintain; duplicates logic from `_launch_uri()` and `_launch_from_info()` |

### Medium (20)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| 31 | **Duplicate keyword list `_MEDIA_TYPE_KEYWORDS`** — defined twice identically at lines 110 and 145 | `media_manager.py:110,145` | Copy-paste error; edits to one not reflected in other |
| 32 | **State machine in conversation_orchestrator.py has no persistence** — restart resets all state; in-flight confirmations lost | `conversation_orchestrator.py` | Interrupted sessions lose pending actions |
| 33 | **"whore u" in identity triggers** — likely intended as "who're u", literal "whore u" is a valid trigger | `identity_dataset.py:33` | Data quality issue |
| 34 | **`"full self analysis"` in two different identity entries** — first match wins, second entry never reached | `identity_dataset.py:404,421` | Dead entry; user always gets first answer |
| 35 | **`SessionState.__init__` calls `init_db()` every time** — multiple redundant DB inits | `session_state.py:35` | Wasted I/O on every session creation |
| 36 | **`asyncio.run()` has no timeout on primary LLM path** — can block indefinitely | `llm_ops.py:45` | Hanging LLM call blocks the entire pipeline |
| 37 | **Overly broad `except BaseException`** — catches SystemExit, KeyboardInterrupt | `llm_ops.py:56,59` | Masks fatal signals |
| 38 | **Spotify/YouTube play in execute_capability bypasses browser_operator fallback chain** — uses BrowserRuntime directly | `app_operator.py:1760` | Inconsistent browser routing |
| 39 | **Triplicated extraction code in browser facade** — extract_dom, extract_tables, extract_links are nearly identical | `browser/facade.py` | Violates DRY; fixes need 3x effort |
| 40 | **`_extract_url_name()` duplicates app_operator.py known domains** — 17 WEB_URLS + 12 WEB_DOMAIN_ALIASES mirrored | `runtime_response_formatter.py:43-56`, `app_operator.py:403-432` | Dual maintenance; domains fall out of sync |
| 41 | **Outcome constants defined twice** — imported from operator_protocol then redefined at module level | `execution_boundary.py:29-43,67-73` | Shadowed imports are dead code |
| 42 | **`_ACTION_MAP` has media entries without STATIC_ACTION_TABLE handlers** — "media_play", "media_pause" etc. mapped but no handler | `execution_boundary.py:181-189` | Dead mappings waste lookup time |
| 43 | **Process registration only for "open_app"** — capabilities and browser actions not tracked for process lifecycle | `execution_boundary.py:845-863` | Cannot close capabilities or browser-launched processes |
| 44 | **`math_resolver.py` uses `eval()` on user input** — regex guard is restrictive but still `eval()` | `math_resolver.py:50-51` | Potential RCE vector (low probability, high impact) |
| 45 | **System state resolver only checks 6 hardcoded apps** — claims "Verified running applications" but only checks chrome, code, spotify, discord, telegram, notepad | `system_state_resolver.py:60-73` | Misleading diagnostics |
| 46 | **`_MEMORY_PATTERNS` substring match too broad** — `cand in fact_key` can match unexpected keys | `memory_resolver.py:88` | Wrong memory recall for similar key names |
| 47 | **Diagnostics opens real applications** — chrome, calculator, notepad launched during diagnostics run | `kio_diagnostics.py` | Contaminates user environment during testing |
| 48 | **Default volume to UP** — "volume" without direction always increases volume | `runtime_handoff.py:128-135` | Cannot query current volume level; unexpected behavior |
| 49 | **`_CONTINUITY_TRIGGERS` broad matching** — "and", "it", "that" all trigger continuity mode | `input_normalizer.py:64` | False continuation detection |
| 50 | **Content-word guard in _is_continuation_query is fragile** — complex 90-line function with overlapping conditions | `integration_adapter.py:199-289` | Hard to reason about; edge cases produce unexpected continuation behavior |

---

## 2. TOP 20 RUNTIME RISKS

| Rank | Risk | Probability | Impact | Root Cause |
|------|------|------------|--------|------------|
| 1 | **Playwright process leak on restart** | HIGH | CRITICAL | `_br_loop` never shuts down; no cleanup path in browser_operator or kio_bot |
| 2 | **State corruption from parallel sessions** | MEDIUM | CRITICAL | ContinuityResolver uses class-level mutable state; all instances share same `_state` |
| 3 | **LLM hang blocking the pipeline** | LOW | CRITICAL | `asyncio.run()` no timeout on primary LLM path |
| 4 | **eval() RCE in math resolver** | VERY LOW | CRITICAL | `math_resolver.py:50-51` uses `eval()` on user input |
| 5 | **Silent pronoun resolution failure** | HIGH | HIGH | Three pronoun systems with three state stores can diverge |
| 6 | **Confirmation silently lost** | HIGH | HIGH | Exact-match triggers reject "yes please" / "no thank you" |
| 7 | **Wrong canned response from protected query** | MEDIUM | HIGH | Substring match too broad; "what time is it" matches in unrelated queries |
| 8 | **Orchestration pipeline runs twice** | MEDIUM | HIGH | Mission + dispatch both call _route_via_orchestration |
| 9 | **Action requests phrased as questions not executed** | MEDIUM | HIGH | "can you open chrome" classified as INFORMATIONAL |
| 10 | **Knowledge queries silently ignored** | MEDIUM | HIGH | is_knowledge_query() too narrow; "Interstellar cast" falls through |
| 11 | **Battery/RAM/CPU readings from stale psutil** | LOW | MEDIUM | No freshness guard on system_state_resolver cache |
| 12 | **Media transport commands ignored** | MEDIUM | MEDIUM | "pause" / "next" not in exec_patterns |
| 13 | **Bounded prompt string heuristic fails** | LOW | MEDIUM | "Current User Input:" check is fragile if prompt changes |
| 14 | **Template rotation gives wrong verb** | MEDIUM | LOW | "Launched firefox" when user said "open firefox" |
| 15 | **Duplicated browser and app normalizers diverge** | LOW | MEDIUM | _normalize_public_result in two files |
| 16 | **FallbackManager suppresses similar responses** | MEDIUM | LOW | 3-item recency with normalization can suppress valid different responses |
| 17 | **Orphaned pending action from topic change** | MEDIUM | MEDIUM | Any conversational input with >0.5 confidence resets AWAITING_CONFIRMATION |
| 18 | **Memory leak from _RUNTIME_TRACKER** | HIGH | LOW | Unbounded dict growth over long sessions |
| 19 | **DB state not persisted on TTL expiry** | MEDIUM | MEDIUM | _clear_conversation_state doesn't persist cleared state |
| 20 | **capability registry checked 3x per request** | HIGH | LOW | In _dispatch_command, _route_builtin, and _ai_fallback |

---

## 3. HIDDEN BUGS (subtle, hard-to-find issues)

1. **`_route_via_orchestration` definition shadow** — function defined twice, first wrapper is dead code but looks like a valid entry point to readers

2. **Action extraction uses pattern string not match** — `if "open" in pattern` checks regex source, not matched text. Adding `r"^start\s+(.+)"` produces broken intent with action=None, target=user's input

3. **`_MEDIA_TYPE_KEYWORDS` duplication** — two identical dicts; edits to one are silently lost

4. **"could you", "can you" bring, "would you" all classified INFORMATIONAL** — any polite request form bypasses execution

5. **Ordinal pattern "the first" vs "first"** — inconsistent regex coverage in ContinuityEngine could miss some ordinal references

6. **`_has_different_entity()` guard in ContinuityEngine fails for lowercase queries** — no proper nouns means no guard activation; "tell me about it" treated as followup even if completely new topic

7. **`_answer_person` not reset** — once set by "who directed Interstellar", subsequent "what is his next movie" resolves to wrong person if user switches topics

8. **URL placeholder insertion changes sanitize_applied flag** — comparison of original vs text-with-placeholders is always different when URLs present

9. **"what is kio" with trailing space** — identity_dataset trigger match bound of +12 is arbitrary; works for most inputs but could fail on edge lengths

10. **`_get_contextual_offers()` always returns same 6 offers** — no dynamic artifact-based filtering despite having ArtifactMemory available

---

## 4. UNNECESSARY COMPLEXITIES (YAGNI / dead code / stubs)

| Item | Location | Complexity Cost | Action |
|------|----------|----------------|--------|
| 4 adapter sub-packages unused (agency_swarm, agent_reach, shepherd, openwork) | `adapters/` | 8 files, ~300 lines | Remove |
| browser/backend.py (protocol with no implementations) | `browser/backend.py` | 21 lines | Remove |
| browser/navigation.py (2/3 stubs) | `browser/navigation.py` | 21 lines | Remove or complete |
| browser/sessions.py (stubs) | `browser/sessions.py` | 12 lines | Remove |
| browser/profiles.py, downloads.py, permissions.py, uploads.py (all stubs) | `browser/` | ~42 lines total | Remove |
| `automation.py` duplicates facade | `browser/automation.py` | 22 lines | Merge into facade |
| `check_authority_override` dead no-op | `input_normalizer.py:171-177` | 7 lines called per request | Remove call |
| `_MEDIA_TYPE_KEYWORDS` duplicate | `media_manager.py:145` | 35 lines | Remove duplicate |
| Second identity/memory resolver call in responder | `conversation_responder.py:448-455` | 8 lines called per request | Remove dead block |
| `_route_via_orchestration` first definition | `runtime.py:896-898` | 3 lines | Remove |
| Outcome constants shadowing imports | `execution_boundary.py:67-73` | 7 lines | Use imported version |
| `_ACTION_MAP` media entries without handlers | `execution_boundary.py:181-189` | 9 entries | Remove |
| Gate 3 pipeline init duplicated in two functions | `runtime.py:925-940,1179-1194` | 15 lines each | Remove duplicate |
| `entity_state_engine.py` stub | `entity_state_engine.py` | 31 lines | Complete or remove |
| redundant `init_db()` calls in SessionState | `session_state.py:35` | Called per session | Move to bootstrap |
| 40+ documentation .md files at root | root directory | 40 files, ~10,000 lines | Archive to docs/ |

---

## 5. DUPLICATE SUBSYSTEM MATRIX

| Function | Old Location | New Location | Relationship |
|----------|-------------|-------------|-------------|
| **Retrieval Router** | `knowledge/retrieval_router.py` (`KnowledgeRouter`) | `intelligence/retrieval_router.py` (`RetrievalRouter`) | Different classes, different return types, overlapping providers |
| **Pronoun Resolution** | `media/intelligence/continuity_engine.py` (`ContinuityEngine.is_followup`) | `media/intelligence/media_reference_resolver.py` (`MediaReferenceResolver._try_pronoun`) | **Three-way**: also `integration_adapter._try_memory_resolve`, each with different state store |
| **Answer Formatting** | `media/intelligence/answer_composer.py` (`AnswerComposer`) | `media/intelligence/media_response_formatter.py` (functions) | Both produce templates; AnswerComposer doesn't use media_response_formatter |
| **State Store** | `media/media_context.py` (`MediaContext`) | `media/intelligence/context_store.py` (`ContextStore`) | Both hold entity/topic state; MediaContext is legacy |
| **Domain Classification** | `continuity_resolver.py:428-436` (`_detect_domain`) | `topic_classifier.py` and `continuity_engine.py` | Three overlapping keyword-based classifiers |
| **Follow-up Patterns** | `continuity_resolver.py` | `media_followup_engine.py` | Patterns directly merged (code comment confirms) |
| **Normalize Public Result** | `browser_operator.py:152-230` | `app_operator.py:471-537` | Nearly identical; divergent failure_class logic |
| **Capability Check** | `_dispatch_command` (command_router.py:462-464) | `_route_builtin` (command_router.py:796-807) | Redundant third check in _ai_fallback |
| **Known Domains** | `app_operator.py:403-432` | `runtime_response_formatter.py:43-56` | WEB_URLS/WEB_DOMAIN_ALIASES partially duplicated |
| **Nested kio_final/** | `./kio_final/` | (root) | Contains its own mini_kio/ copy, docs, tests, snapshots — duplicate of root structure |
| **Two retrieval_router.py files** | `knowledge/retrieval_router.py` | `intelligence/retrieval_router.py` | Same filename, different package, causes confusion |

---

## 6. OWNERSHIP MATRIX

### Core Systems

| Module | Prime Owner | Lines | Risk Level | Dependencies |
|--------|------------|-------|------------|--------------|
| `core/runtime.py` | **Core Runtime** | 1664 | **CRITICAL** | Everything |
| `core/command_router.py` | **Command Router** | 1556 | **CRITICAL** | execution_boundary, app_operator, browser_operator, media, resolvers |
| `core/app_operator.py` | **App Operator** | 1835 | **HIGH** | system_operator, file_operator, browser_operator |
| `core/execution_boundary.py` | **Execution Boundary** | 1034 | **HIGH** | operator_protocol, runtime, app/browser/file/system operators |
| `llm/conversation_responder.py` | **Conversation Responder** | 665 | **HIGH** | All resolvers, llm_ops, governance, intelligence_router |
| `media/intelligence/integration_adapter.py` | **Media Intelligence** | 2024 | **HIGH** | All media intelligence modules, retrieval_router |
| `media/media_manager.py` | **Media Manager** | 2022 | **HIGH** | All media subsystems, providers, intelligence adapter |
| `core/continuity_resolver.py` | **Continuity Resolver** | 610 | **HIGH** | continuity_context_provider, entity_memory, session_state |
| `core/browser_operator.py` | **Browser Operator** | 502 | **HIGH** | browser_runtime, routing_utils, app_operator |
| `llm/intent_classifier.py` | **Intent Classifier** | 219 | **HIGH** | intent_models |
| `llm/conversation_orchestrator.py` | **Orchestrator** | 247 | **HIGH** | intent_models, conversation_models |
| `runtime/runtime_handoff.py` | **Runtime Handoff** | 184 | **MEDIUM** | intent_models, execution_boundary |

### Supporting Systems

| Module | Prime Owner | Lines | Risk Level |
|--------|------------|-------|------------|
| `intelligence/intelligence_router.py` | **Intelligence Router** | 264 | MEDIUM |
| `intelligence/retrieval_router.py` | **Retrieval Router (new)** | 297 | MEDIUM |
| `intelligence/local_reasoner.py` | **Local Reasoner** | 410 | LOW |
| `intelligence/emergency_responder.py` | **Emergency Responder** | 190 | LOW |
| `intelligence/retrieval_synthesizer.py` | **Retrieval Synthesizer** | 303 | MEDIUM |
| `knowledge/retrieval_router.py` | **Knowledge Router (old)** | 356 | MEDIUM |
| `media/intelligence/answer_composer.py` | **Answer Composer** | 136 | MEDIUM |
| `media/intelligence/continuity_engine.py` | **Media Continuity** | 325 | MEDIUM |
| `media/intelligence/media_reference_resolver.py` | **Media Reference Resolver** | 616 | MEDIUM |
| `media/intelligence/topic_classifier.py` | **Topic Classifier** | 268 | MEDIUM |
| `media/intelligence/media_entity_memory.py` | **Media Entity Memory** | 370 | LOW |
| `llm/input_normalizer.py` | **Input Normalizer** | 188 | MEDIUM |
| `llm/conversation_governor.py` | **Conversation Governor** | 364 | MEDIUM |
| `llm/identity_dataset.py` | **Identity Dataset** | 591 | MEDIUM |
| `llm/session_state.py` | **Session State** | 280 | MEDIUM |
| `llm/fallback_manager.py` | **Fallback Manager** | 120 | LOW |
| `core/mission.py` | **Mission Pipeline** | 436 | MEDIUM |
| `core/context_manager.py` | **Context Manager** | 627 | MEDIUM |
| `core/command_parser.py` | **Command Parser** | 400 | MEDIUM |
| `resolvers/identity_resolver.py` | **Identity Resolver** | 80 | LOW |
| `resolvers/memory_resolver.py` | **Memory Resolver** | 146 | MEDIUM |
| `resolvers/knowledge_resolver.py` | **Knowledge Resolver** | 76 | LOW |
| `resolvers/system_state_resolver.py` | **System State Resolver** | 78 | LOW |
| `resolvers/math_resolver.py` | **Math Resolver** | 61 | MEDIUM |

### No Owner / Orphaned

| File | Status |
|------|--------|
| `browser/automation.py` | Unused — functionality in facade.py |
| `browser/backend.py` | Dead protocol — no implementations |
| `browser/navigation.py` | Stub — back() and forward() are pass |
| `browser/sessions.py` | Stub — no real session persistence |
| `browser/profiles.py` | Stub — empty |
| `browser/downloads.py` | Stub — empty |
| `browser/permissions.py` | Stub — empty |
| `browser/uploads.py` | Stub — empty |
| `adapters/agency_swarm/` | No active callers in core |
| `adapters/agent_reach/` | No active callers in core |
| `adapters/shepherd/` | No active callers in core |
| `adapters/openwork/` | No active callers in core |
| `adapters/avatar/` | Empty |
| `adapters/agentic_inbox/` | Empty |
| `adapters/librechat/` | Empty |
| `adapters/voice/` | Empty |
| `entity_state_engine.py` | Stub — always returns RELEASED |

---

## 7. DEPENDENCY GRAPH

```
User Input
  │
  ├─► kio_bot.py / cua_cli.py
  │     │
  │     └─► command_router.py
  │           │
  │           ├─► command_parser.py           [parsing + multi-step]
  │           ├─► context_manager.py           [domain + continuation detection]
  │           │     │
  │           │     ├─► runtime.py              [_route_via_orchestration]
  │           │     │     │
  │           │     │     ├─► mission.py         [MissionPipeline.run]
  │           │     │     │     │
  │           │     │     │     └─► command_router.py  [handle_command fast path]
  │           │     │     │
  │           │     │     └─► llm/intent_classifier.py
  │           │     │         ├─► llm/intent_validator.py
  │           │     │         ├─► llm/conversation_orchestrator.py
  │           │     │         │     └─► runtime/runtime_handoff.py
  │           │     │         │           ├─► execution_boundary.py
  │           │     │         │           │     ├─► app_operator.py
  │           │     │         │           │     ├─► browser_operator.py ←┐
  │           │     │         │           │     │                        │ [duplicate]
  │           │     │         │           │     └─► file_operator.py     │ normalize_public_result
  │           │     │         │           │                              │
  │           │     │         │           └─► runtime_response_formatter.py
  │           │     │         │                 └─► app_operator.py ─────┘
  │           │     │         │
  │           │     │         └─► llm/conversation_responder.py
  │           │     │               │
  │           │     │               ├─► resolvers/*.py                    [6 resolvers]
  │           │     │               │     └─► knowledge/knowledge_resolver.py
  │           │     │               │           ├─► knowledge/retrieval_router.py ──┐
  │           │     │               │           │    └─► knowledge/media_knowledge_router.py │ [DISABLED]
  │           │     │               │           └─► core/freshness_classifier.py    │
  │           │     │               │                                               │
  │           │     │               ├─► intel/intelligence_router.py  [5-layer]     │ [DUPLICATE]
  │           │     │               │     ├─► intel/retrieval_router.py (new) ──────┘
  │           │     │               │     ├─► intel/retrieval_synthesizer.py
  │           │     │               │     ├─► intel/local_reasoner.py
  │           │     │               │     └─► intel/emergency_responder.py
  │           │     │               │
  │           │     │               ├─► llm/conversation_governor.py
  │           │     │               ├─► llm/session_state.py
  │           │     │               │     └─► backend/db.py
  │           │     │               ├─► llm/fallback_manager.py
  │           │     │               └─► llm/search_hardener.py
  │           │     │
  │           │     └─► media/media_manager.py
  │           │           └─► media/intelligence/integration_adapter.py
  │           │                 ├─► media/intelligence/continuity_engine.py
  │           │                 ├─► media/intelligence/media_reference_resolver.py
  │           │                 │     └─► media/media_context.py
  │           │                 ├─► media/intelligence/topic_classifier.py
  │           │                 ├─► media/intelligence/answer_composer.py
  │           │                 ├─► media/intelligence/media_response_formatter.py
  │           │                 ├─► media/intelligence/media_entity_memory.py
  │           │                 └─► intel/retrieval_router.py (new)
  │           │
  │           └─► core/continuity_resolver.py
  │                 └─► core/continuity_context_provider.py
  │                       ├─► media/media_manager.py
  │                       ├─► media/entity_state_engine.py [STUB]
  │                       └─► runtime/
  │
  └─► browser/facade.py
        └─► core/browser_operator.py
              └─► external/cua/... [browser_runtime]
```

### Circular Dependency Risks
- `runtime.py` → `conversation_responder.py` (via _route_via_orchestration)
- `conversation_responder.py` → `intelligence_router.py` → `retrieval_synthesizer.py` → (no cycle)
- `media_manager.py` → `integration_adapter.py` → `retrieval_router.py` (no cycle)
- **No hard cycles detected**, but deferred imports throughout suggest fragile dependency graph

---

## 8. TECHNICAL DEBT HEATMAP

### By Module

| Module | Debt Level | Lines | Stubs | Dead Code | Duplicates | Monoliths | Score |
|--------|-----------|-------|-------|-----------|------------|-----------|-------|
| `core/command_router.py` | **EXTREME** | 1556 | 0 | 1 | 2 | 1 (640-line) | ★★★★★ |
| `core/app_operator.py` | **EXTREME** | 1835 | 0 | 0 | 3 | 1 (140-line) | ★★★★★ |
| `media/media_manager.py` | **EXTREME** | 2022 | 0 | 2 | 1 | 1 | ★★★★★ |
| `media/intelligence/integration_adapter.py` | **EXTREME** | 2024 | 0 | 0 | 0 | 1 | ★★★★ |
| `core/runtime.py` | **VERY HIGH** | 1664 | 0 | 2 | 2 | 0 | ★★★★ |
| `core/continuity_resolver.py` | **VERY HIGH** | 610 | 0 | 0 | 3 | 0 | ★★★★ |
| `core/browser_operator.py` | **HIGH** | 502 | 0 | 1 | 1 | 0 | ★★★ |
| `core/execution_boundary.py` | **HIGH** | 1034 | 0 | 2 | 0 | 1 | ★★★ |
| `llm/conversation_responder.py` | **HIGH** | 665 | 0 | 1 | 1 | 0 | ★★★ |
| `browser/` (10 files) | **HIGH** | 258 | 6 | 2 | 1 | 0 | ★★★ |
| `adapters/` (all) | **MEDIUM** | ~500 | 4 | 4 | 0 | 0 | ★★ |
| `knowledge/retrieval_router.py` | **MEDIUM** | 356 | 1 | 0 | 1 | 0 | ★★ |
| `intelligence/retrieval_router.py` | **LOW** | 297 | 3 (stubbed) | 0 | 0 | 0 | ★ |
| `intelligence/local_reasoner.py` | **LOW** | 410 | 0 | 0 | 0 | 0 | ★ |
| `intelligence/emergency_responder.py` | **LOW** | 190 | 0 | 0 | 0 | 0 | 0 |
| `resolvers/*.py` (7 files) | **LOW-MEDIUM** | 485 | 0 | 0 | 0 | 0 | ★ |
| `llm/identity_dataset.py` | **MEDIUM** | 591 | 0 | 1 | 1 | 0 | ★★ |
| `llm/conversation_governor.py` | **LOW** | 364 | 0 | 0 | 0 | 0 | 0 |
| `llm/intent_classifier.py` | **MEDIUM** | 219 | 0 | 1 | 0 | 0 | ★★ |

### Hotspots (files over 500 lines)
1. `media/intelligence/integration_adapter.py` — 2024 lines
2. `media/media_manager.py` — 2022 lines
3. `core/app_operator.py` — 1835 lines
4. `core/runtime.py` — 1664 lines
5. `core/command_router.py` — 1556 lines
6. `core/execution_boundary.py` — 1034 lines
7. `core/context_manager.py` — 627 lines
8. `media/intelligence/media_reference_resolver.py` — 616 lines
9. `core/continuity_resolver.py` — 610 lines
10. `llm/identity_dataset.py` — 591 lines
11. `core/browser_operator.py` — 502 lines

---

## 9. BEHAVIOURAL RISK ASSESSMENT

### How Architectural Issues Manifest to Users

| User Action | Current Behavior | Root Cause | Correct Behavior |
|------------|-----------------|------------|-----------------|
| "hello friend" | Works (typo already handled) | n/a | Same |
| "hallo freind" | Classified differently, unexpected response | Missing typo normalizations (#11) | Normalized and handled same as "hello friend" |
| "can you open chrome" | Treated as informational question, LLM answers but doesn't open | exec_patterns require start anchor (#13) | Opens Chrome |
| "pause" (while media playing) | Treated as casual conversation, confidence 0.4 | "pause" not in exec_patterns (#14) | Pauses media |
| "yes please" (to confirmation prompt) | Treated as topic change, confirmation lost | Exact-match triggers (#15) | Confirms action |
| "Interstellar cast" | LLM answers (might be wrong/outdated) | is_knowledge_query too narrow (#9) | Routes to knowledge providers |
| "tell me about it" (after previous topic) | Works if stores are in sync | Three pronoun systems (#3) | Same |
| "tell me about it" (fresh query) | Treated as followup to old topic, wrong entity | Broad followup detection (#50) | Recognized as new query |
| "go back to conversation" | No handler; "I don't understand" or nearest match | No route handler (#20) | Exits browser mode |
| "volume" (without direction) | Volume increases | Default to UP (#48) | Returns current volume or asks |
| "what is kio's worldview on consciousness" | Works (if within length bound) | Substring match +12 bound (#18) | Same (or better) |
| Open Chrome → Close Chrome | Chrome closes correctly | PID tracking for open_app (#43) | Same |
| Open YouTube via capability → Close | Cannot close; "I didn't open that" | Capability actions not tracked (#43) | Closes capability |
| "open reddit in chrome" | Fails — not in known_webapps whitelist | Strict webapp whitelist (command_parser:248) | Opens reddit in Chrome |
| Multiple parallel sessions | State leaks between sessions | Class-level ContinuityResolver state (#2) | Isolated sessions |
| System restart (power loss) | In-flight confirmations lost; no DB persistence | State machine not persisted (#32) | Resume confirmation after restart |
| Search → Play → Next → Play similar | Next works (sometimes) depending on which state store is hit | Triple state stores (#3) | Consistent transport control |
| "what time is it" inside long query | Gets "I cannot tell the time" canned response | Protected query substring match (#18) | Routes to actual content |

---

## 10. RECOMMENDED INVESTIGATION ORDER

### Phase 1 — Safety-Critical (investigate before any edits)
| Order | Symbol / Module | Why |
|-------|----------------|-----|
| 1 | `_br_loop` / `_br_thread` in `browser_operator.py` | No shutdown path = zombie processes on restart |
| 2 | `ContinuityResolver._state` (class-level) | Global mutable state shared across all sessions |
| 3 | `math_resolver.py:eval()` | RCE vector (low prob, critical impact) |
| 4 | `asyncio.run()` timeout in `llm_ops.py:45` | Hanging LLM blocks entire pipeline |

### Phase 2 — User-Facing Bugs (investigate next)
| Order | Symbol / Module | Why |
|-------|----------------|-----|
| 5 | Triple pronoun resolution stores (ContextStore vs MediaContext vs MediaEntityMemory) | Silent failures for "it"/"that"/"him" |
| 6 | exec_patterns start anchor in `intent_classifier.py:17-25` | "can you open X" never executed |
| 7 | Exact-match confirmation triggers in `conversation_orchestrator.py:41,55` | "yes please" = topic change |
| 8 | `is_knowledge_query()` patterns in `knowledge/retrieval_router.py:131` | "Interstellar cast" missed |

### Phase 3 — Structural (investigate after Phases 1-2)
| Order | Symbol / Module | Why |
|-------|----------------|-----|
| 9 | Dual resolver instances in `conversation_responder.py:128-141` | Memory waste, duplicate calls |
| 10 | `_route_builtin` decomposition in `command_router.py:896-1536` | 640-line monolith |
| 11 | `_normalize_public_result` duplication (browser_operator + app_operator) | Divergent behavior |
| 12 | Triple confirmation bridge (orchestrator + dispatch + mission) | Duplicate logic |

### Phase 4 — Cleanup (investigate last)
| Order | Symbol / Module | Why |
|-------|----------------|-----|
| 13 | Dead browser stubs (6 files in browser/) | Remove |
| 14 | Unused adapter packages (4 in adapters/) | Remove |
| 15 | Dead code: shadowed outcome constants, duplicate keyword dict, etc. | Clean |
| 16 | `entity_state_engine.py` stub | Complete or delete |
| 17 | `is_media_query()` disabled gate | Re-enable or document permanently |
| 18 | `kio_final/` nested directory | Cleanup duplication |

---

## APPENDIX A: FILE RANKING BY TECHNICAL DEBT

```
Rank  File                                     Lines    Score  
────  ────────────────────────────────────────  ─────    ─────  
 1    media/intelligence/integration_adapter    2024     EXTREME
 2    media/media_manager                       2022     EXTREME
 3    core/app_operator                         1835     EXTREME
 4    core/runtime                              1664     VERY HIGH
 5    core/command_router                       1556     EXTREME
 6    core/execution_boundary                   1034     HIGH
 7    core/context_manager                       627     MEDIUM
 8    media/intelligence/media_reference_resolv  616     MEDIUM
 9    core/continuity_resolver                   610     VERY HIGH
10    llm/identity_dataset                       591     MEDIUM
11    core/browser_operator                      502     HIGH
12    core/mission                               436     MEDIUM
13    intel/local_reasoner                       410     LOW
14    core/command_parser                        400     MEDIUM
15    media/intelligence/media_entity_memory      370     LOW
16    llm/conversation_governor                  364     LOW
17    knowledge/retrieval_router                 356     MEDIUM
18    media/intelligence/continuity_engine        325     MEDIUM
19    intel/retrieval_synthesizer                 303     MEDIUM
20    intel/retrieval_router                      297     LOW
21    llm/session_state                          280     MEDIUM
22    media/intelligence/topic_classifier         268     MEDIUM
23    intel/intelligence_router                  264     MEDIUM
24    browser/ (10 files total)                  258     HIGH
25    llm/conversation_orchestrator              247     HIGH
26    core/runtime_response_formatter            225     LOW
27    llm/intent_classifier                      219     HIGH
28    llm/input_normalizer                       188     MEDIUM
29    runtime/runtime_handoff                    184     MEDIUM
30    intel/emergency_responder                  190     LOW
31    core/freshness_classifier                  165     LOW
32    resolvers/memory_resolver                  146     MEDIUM
33    media/intelligence/answer_composer         136     MEDIUM
34    core/continuity_context_provider            120     MEDIUM
35    llm/fallback_manager                       120     LOW
36    browser/facade                             110     MEDIUM
37    media/media_session                        100     LOW
38    knowledge/media_knowledge_router             95     MEDIUM
39    media/intelligence/media_response_formatt   93     MEDIUM
40    resolvers/identity_resolver                 80     LOW
41    resolvers/system_state_resolver             78     LOW
42    resolvers/knowledge_resolver                76     LOW
43    media/media_state                           63     LOW
44    resolvers/math_resolver                     61     MEDIUM
45    media/entity_state_engine                   31     MEDIUM
46    runtime/runtime_contracts                   33     LOW
47    resolvers/reasoning_resolver                27     LOW
48    resolvers/base                              17     LOW
49    llm/trace_context                           18     LOW
50    knowledge/knowledge_models                  16     LOW
```

## APPENDIX B: GLOBAL STATE REGISTRY

| Variable | File | Type | Mutated By |
|----------|------|------|------------|
| `_CURRENT_RUNTIME` | `core/runtime.py:25` | Singleton | `bootstrap_runtime()` |
| `_CAMERA_HANDLE` | `core/camera_runtime.py:25` | cv2.VideoCapture | `open_camera()`, `_release_handle()` |
| `_br_loop` | `core/browser_operator.py:32` | asyncio.EventLoop | `_ensure_br_loop()` |
| `_br_thread` | `core/browser_operator.py:33` | Thread | `_ensure_br_loop()` |
| `_engine` | `backend/db.py:13` | SQLAlchemy Engine | `init_db()`, `close_db()` |
| `_SessionLocal` | `backend/db.py:14` | sessionmaker | `init_db()`, `close_db()` |
| `_REGISTRY` | `core/command_registry.py:39` | Singleton | `get_command_registry()` |
| `_CAPABILITY_REGISTRY` | `core/capability_registry.py:137` | Singleton | `get_capability_registry()` |
| `_GATEWAY` | `core/llm_router.py:38` | Singleton | `_get_gateway()` |
| `_PIPELINE` | `core/mission.py:426` | Singleton | `get_pipeline()` |
| `_ROUTER` | `intel/intelligence_router.py:239` | Singleton | `get_router()` |
| `_BROWSER_REGISTRY` | `core/routing_utils.py:26` | Singleton | `get_browser_registry()` |
| `_stream` | `execution/observations.py:181` | Singleton | `get_observation_stream()` |
| `_registry_instance` | `core/mcp/registry.py:109` | Singleton | `get_mcp_server_registry()` |
| `ContinuityResolver._state` | `core/continuity_resolver.py:102` | **Class-level** | All classmethods |
| `ContinuityResolver._provider` | `core/continuity_resolver.py:103` | **Class-level** | `set_context_provider()` |
| `ContinuityResolver._entity_memory` | `core/continuity_resolver.py:104` | **Class-level** | `set_entity_memory()` |
| `ContinuityResolver._session_state` | `core/continuity_resolver.py:105` | **Class-level** | `set_session_state()` |
| `_CONNECTOR_INSTANCE` | `core/command_router.py:40` | Singleton | `_get_browser_connector()` |
| `_CONNECTOR_STARTED` | `core/command_router.py:41` | bool | `_start_browser_connector()` |
| `_CONNECTOR_MODULES_LOADED` | `core/command_router.py:143` | bool | `_load_connector_module()` |
| `_CACHE_BR_AVAILABLE` | `core/command_router.py:135` | Optional[bool] | `_check_br_available()` |
| `_DIAGNOSTICS_INITIALIZED` | `core/kio_diagnostics.py:30` | bool | `init_diagnostics()` |
| `_installed` | `core/_operational_monkeypatch.py:19` | bool | `install_monkeypatches()` |
| `_DISCORD_THREAD` | `platform/discord_transport.py:162` | Thread | `start_discord_thread()` |
| `MediaManager._instance` | `media/media_manager.py:320` | Singleton | `get_instance()` |
| `MetricsCollector._instance` | `execution/metrics.py:20` | Singleton | `__new__`, `reset` |
| `CapabilityRouter._instance` | `execution/capability_router.py:35` | Singleton | `__new__`, `reset` |
| `ProviderRegistry._instance` | `core/provider_registry.py:14` | Singleton | `__new__` |
| `_RUNTIME_TRACKER` | `core/context_manager.py:121` | `dict[str, str]` | Grows unboundedly |
| `_id_counter` | `core/mcp/client.py:29` | int | `_next_id()` |

---

## APPENDIX C: FILES WITH NO ISSUES (clean)

| File | Lines | Reason |
|------|-------|--------|
| `llm/llm_constants.py` | 42 | Clean constants file |
| `llm/trace_context.py` | 18 | Clean dataclass |
| `runtime/runtime_contracts.py` | 33 | Clean enums/dataclasses |
| `media/media_state.py` | 63 | Clean state machine |
| `media/media_session.py` | 100 | Clean dataclasses |
| `knowledge/knowledge_models.py` | 16 | Clean dataclasses |
| `resolvers/base.py` | 17 | Clean abstract base |
| `resolvers/reasoning_resolver.py` | 27 | Clean LLM wrapper |
| `intel/emergency_responder.py` | 190 | Well-structured sentinel |
| `intel/local_reasoner.py` | 410 | Well-structured fallback |
| `media/intelligence/media_entity_memory.py` | 370 | Well-implemented with TTL, persistence, tests |
