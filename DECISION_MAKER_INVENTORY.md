# DECISION_MAKER_INVENTORY.md
# All Independent Decision-Makers in KIO
# =======================================

## COUNT: 28 distinct decision-making locations

---

### DM-001: _IntentClassifier.classify()
- **File:** `mini_kio/core/pipeline/__init__.py:1562`
- **Decision:** Intent type (GREETING, SOCIAL, UTILITY, MEDIA_PLAY, etc.)
- **Trigger:** Every user message (mandatory, first pass)
- **Priority:** 10 (highest — first classifier)
- **Output:** RoutingDecision with intent_type, action, target
- **Can override:** No (canonical first-pass classifier)
- **Can respond:** No (data only)
- **Can execute side effect:** No (pure classification)
- **Canonical:** YES — single canonical first-pass classifier

### DM-002: _NormalizationService.run()
- **File:** `mini_kio/core/pipeline/__init__.py:~1500`
- **Decision:** Input normalization (emoji strip, alias expansion, typo correction, politeness strip)
- **Trigger:** Every user message (pre-classification)
- **Priority:** 10 (pre-processing, mandatory)
- **Output:** Normalized text string
- **Can override:** Yes — modifies text before classification
- **Can respond:** No
- **Can execute side effect:** No
- **Canonical:** YES — single canonical normalizer

### DM-003: _apply_discourse_context_override()
- **File:** `mini_kio/core/pipeline/__init__.py:~1200`
- **Decision:** Override classifier result when message continues ongoing discussion
- **Trigger:** After classification, for ENTITY_QUERY/INFORMATION/CONVERSATION intents
- **Priority:** 9
- **Output:** Modified RoutingDecision (re-routes to CONVERSATION)
- **Can override:** YES — reclassifies entity_query → conversation
- **Can respond:** No
- **Canonical:** YES — single canonical discourse-continuity handler
- **Conflict risk:** LOW (only fires on specific intent types)

### DM-004: _apply_verification_probe_route()
- **File:** `mini_kio/core/pipeline/__init__.py:~1150`
- **Decision:** Route bare verification probes to INFORMATION when pending claims exist
- **Trigger:** After classification, for CONVERSATION intent with pending claims
- **Priority:** 9
- **Output:** Modified RoutingDecision (conversation → information)
- **Can override:** YES
- **Can respond:** No
- **Canonical:** YES

### DM-005: _apply_graph_recall_override()
- **File:** `mini_kio/core/pipeline/__init__.py:~750`
- **Decision:** Route research-bound queries to CONVERSATION when graph holds the answer
- **Trigger:** After classification, for INFORMATION/ENTITY_QUERY intents
- **Priority:** 8
- **Output:** Modified RoutingDecision
- **Can override:** YES
- **Can respond:** No
- **Canonical:** YES

### DM-006: _apply_profile_recall_answer()
- **File:** `mini_kio/core/pipeline/__init__.py:~1050`
- **Decision:** Intercept personal-state questions and return deterministic answers
- **Trigger:** After classification, for specific question patterns
- **Priority:** 9
- **Output:** Full response dict (returns early, bypasses rest of pipeline)
- **Can override:** YES — terminates pipeline early
- **Can respond:** YES — sends message
- **Canonical:** YES

### DM-007: _CapabilityResolver.resolve()
- **File:** `mini_kio/core/pipeline/__init__.py:5787`
- **Decision:** Map RoutingDecision → (capability, params)
- **Trigger:** After classification (mandatory)
- **Priority:** 8
- **Output:** (capability_name, params_dict)
- **Can override:** No (follows classification)
- **Canonical:** YES — single canonical capability resolver

### DM-008: _ExecutionCoordinator._dispatch()
- **File:** `mini_kio/core/pipeline/__init__.py:5910`
- **Decision:** Route to capability-specific executor
- **Trigger:** After capability resolution (mandatory)
- **Priority:** 7
- **Output:** Execution result dict
- **Can override:** No
- **Canonical:** YES

### DM-009: _ResponseComposer.compose()
- **File:** `mini_kio/core/pipeline/__init__.py:8987`
- **Decision:** Final response formatting, leak stripping, context update
- **Trigger:** After execution (mandatory)
- **Priority:** 6
- **Output:** Final response dict
- **Can override:** Can strip/modify response text
- **Canonical:** YES

### DM-010: MediaManager (transport classification)
- **File:** `mini_kio/media/media_manager.py`
- **Decision:** Transport command detection (pause/resume/stop/next)
- **Trigger:** When media intent is routed to media capability
- **Priority:** 7 (downstream of pipeline classification)
- **Output:** Transport action
- **Can override:** No (follows pipeline classification)
- **Canonical:** YES for follow-up media state handling
- **Note:** Separate from pipeline's initial media_transport classification (legitimate separation)

### DM-011: MediaContextIntelligence
- **File:** `mini_kio/media/intelligence/media_context_intelligence.py`
- **Decision:** Context-aware media intent extraction (recommendation vs auto vs direct mode)
- **Trigger:** When action=play/play_discovery reaches _exec_media
- **Priority:** 6
- **Output:** SelectionMode + search_query
- **Can override:** Can override target query
- **Canonical:** YES for media context intelligence

### DM-012: ConversationGovernor.check_protected_query()
- **File:** `mini_kio/llm/conversation_governor.py`
- **Decision:** Intercept protected queries before LLM
- **Trigger:** LLM path only (not deterministic pipeline path)
- **Priority:** 8 (when called)
- **Output:** Protected response string or None
- **Can override:** YES — can intercept queries before LLM
- **Can respond:** YES
- **Status:** FIXED — stale queries removed, exact-match only
- **Canonical:** YES for LLM-path protection

### DM-013: Pragmatics.analyze()
- **File:** `mini_kio/core/pragmatics.py`
- **Decision:** Conversational register, social acts, temporal context
- **Trigger:** Every message (called in classification)
- **Priority:** 9
- **Output:** PragmaticsAnalysis with is_social, acts, register, etc.
- **Can override:** No (data input to other decisions)
- **Canonical:** YES — single canonical pragmatics analyzer

### DM-014: render_social_reply()
- **File:** `mini_kio/core/pragmatics.py`
- **Decision:** Generate deterministic social/greeting response
- **Trigger:** Greeting/social template in _exec_conversation
- **Priority:** 5
- **Output:** Response string
- **Can respond:** YES
- **Canonical:** YES for deterministic social responses

### DM-015: identity_dataset.get_identity_answer()
- **File:** `mini_kio/llm/identity_dataset.py`
- **Decision:** Canonical identity response for KIO self-questions
- **Trigger:** Identity template in _exec_conversation
- **Priority:** 7
- **Output:** Identity response string
- **Can respond:** YES
- **Canonical:** YES — single canonical identity source

### DM-016: utility_answer()
- **File:** `mini_kio/core/utilities.py`
- **Decision:** Deterministic utility answers (time/date/weather/convert)
- **Trigger:** Utility capability in _exec_utility
- **Priority:** 7
- **Output:** Utility response dict
- **Can respond:** YES
- **Canonical:** YES — single canonical utility owner

### DM-017: _maybe_proactive_offer()
- **File:** `mini_kio/core/pipeline/__init__.py:7365`
- **Decision:** Append media offer line to information_query results
- **Trigger:** After information_query execution in _exec_media
- **Priority:** 4
- **Output:** Modifies result["message"] (APPENDS)
- **Can override:** No (adds trailing line, doesn't replace)
- **Can respond:** YES (appends to existing response)
- **STATUS:** RISK — This is the mechanism that causes "dual response" appearance
- **Canonical:** YES for media proactive offers

### DM-018: monitoring/proactive.py poll_proactive()
- **File:** `mini_kio/monitoring/proactive.py`
- **Decision:** Proactive notification of stale goals/workflows
- **Trigger:** Daemon loop (independent of user messages)
- **Priority:** 3
- **Output:** Telegram message (independent send)
- **Can respond:** YES (independent outbound message)
- **STATUS:** RISK — Independent message channel, not a response to user input
- **Canonical:** YES for proactive goal notification

### DM-019: companion/proactive.py evaluate_proactive_items()
- **File:** `mini_kio/companion/proactive.py`
- **Decision:** Companion-model proactive initiative surfacing
- **Trigger:** Companion evaluation (may run in response context)
- **Priority:** 3
- **Output:** Optional proactive message
- **Can respond:** YES (when surfaced)
- **Canonical:** YES for companion-based proactivity

### DM-020: ContextManager.resolve_references()
- **File:** `mini_kio/core/context_manager.py`
- **Decision:** Pronoun/reference resolution ("it", "that", "another one")
- **Trigger:** Pre-classification in normalization
- **Priority:** 9
- **Output:** Resolved text
- **Can override:** YES — rewrites text before classification
- **Canonical:** YES — single canonical reference resolver

### DM-021: InputNormalizer
- **File:** `mini_kio/llm/input_normalizer.py`
- **Decision:** Emoji strip, typo correction, contraction expansion
- **Trigger:** Pre-classification
- **Priority:** 9
- **Output:** Normalized text
- **Can override:** YES — modifies text
- **Canonical:** YES

### DM-022: _IntentClassifier._strip_greeting()
- **File:** `mini_kio/core/pipeline/__init__.py:~2050`
- **Decision:** Strip greeting prefix and recurse on remainder
- **Trigger:** Classification layer 1
- **Priority:** 9
- **Output:** Modified RoutingDecision (recursion into classify)
- **Can override:** YES — can re-route entire classification
- **Canonical:** YES

### DM-023: intent_classifier._is_greeting()
- **File:** `mini_kio/llm/intent_classifier.py`
- **Decision:** LLM-path greeting detection
- **Trigger:** When LLM gateway is used for classification
- **Priority:** 6 (only when LLM path is active)
- **Output:** Boolean
- **Status:** FIXED — now imports from canonical phrases.py
- **Canonical:** YES (after fix — imports from shared phrases)

### DM-024: execution_boundary.execute_action()
- **File:** `mini_kio/core/execution_boundary.py`
- **Decision:** Execute desktop actions with safety boundaries
- **Trigger:** Desktop capability execution
- **Priority:** 5
- **Output:** Execution result dict
- **Can execute side effect:** YES (app launch/close, system ops)
- **Canonical:** YES — single canonical execution boundary

### DM-025: BrowserRuntime / Connector
- **File:** `mini_kio/runtime/browser_runtime/`, `mini_kio/browser_connector/`
- **Decision:** Browser tab control, navigation, playback
- **Trigger:** Browser capability execution
- **Priority:** 5
- **Output:** Browser state / playback state
- **Can execute side effect:** YES (opens tabs, plays media)
- **Canonical:** YES for browser operations

### DM-026: MediaManager.play()
- **File:** `mini_kio/media/media_manager.py`
- **Decision:** Media playback initiation and provider selection
- **Trigger:** Media play capability
- **Priority:** 5
- **Output:** Play result dict
- **Can execute side effect:** YES (opens browser, starts playback)
- **Canonical:** YES — single canonical media playback owner

### DM-027: MediaManager.process_followup()
- **File:** `mini_kio/media/media_manager.py`
- **Decision:** Follow-up state handling (rejection, next, accept)
- **Trigger:** Follow-up context or accept_offer action
- **Priority:** 5
- **Output:** Follow-up response dict
- **Can execute side effect:** YES
- **Canonical:** YES — single canonical follow-up handler

### DM-028: CapabilityRegistry
- **File:** `mini_kio/core/capability_registry.py`
- **Decision:** Dynamic capability registration and lookup
- **Trigger:** _CapabilityResolver.resolve()
- **Priority:** 8
- **Output:** Capability name for given intent
- **Can override:** No (follows registry definitions)
- **Canonical:** YES — single canonical capability registry

---

## SUMMARY

| Category | Count | Canonical |
|----------|-------|-----------|
| Pipeline classification | 10 | All canonical |
| Override/correction layers | 5 | All canonical |
| Execution handlers | 8 | All canonical |
| Proactive systems | 3 | 2 risk (proactive interference) |
| External/subsystem | 2 | All canonical |
| **TOTAL** | **28** | **26 canonical, 2 risk** |

## DUPLICATE OWNERSHIP: NONE FOUND

After thorough investigation, each decision has ONE canonical owner.
The "multiple responses" issue is NOT caused by duplicate decision-makers —
it is caused by:
1. `_maybe_proactive_offer()` appending to existing results
2. `monitoring/proactive.py` daemon sending independent messages
3. Proactive companion items being surfaced during response generation
