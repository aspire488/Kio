# OWNERSHIP_CONFLICT_MATRIX.md
# Semantic Concept Ownership Across KIO
# ======================================

## METHODOLOGY
For each major semantic concept, trace: who detects it, who classifies it,
who owns state, who generates response, who executes side effects, who can override.

---

## GREETING

| Aspect | Owner | Status |
|--------|-------|--------|
| Canonical vocabulary | `mini_kio/core/phrases.py` GREETINGS | ✅ CENTRALIZED |
| Pipeline classification | `_IntentClassifier._strip_greeting()` | ✅ CANONICAL |
| Pragmatics detection | `pragmatics.py` ConversationAct.GREETING | ✅ CANONICAL |
| LLM intent classifier | `intent_classifier._is_greeting()` | ✅ imports from phrases.py |
| Response generation | `render_social_reply()` + fallbacks | ✅ CANONICAL |
| Deterministic fallback | `_exec_conversation()` morning/evening/afternoon | ⚠️ LOCAL FALLBACK |

**Conflicts:** NONE — all layers correctly chain
**Previous duplication:** 7 files → NOW 1 canonical vocabulary + 1 canonical response generator

---

## IDENTITY

| Aspect | Owner | Status |
|--------|-------|--------|
| Canonical responses | `identity_dataset.py` | ✅ CANONICAL |
| Pipeline classification | `_IntentClassifier._check_identity()` | ✅ CANONICAL |
| Response generation | `_exec_conversation()` → identity_dataset | ✅ CANONICAL |
| LLM intent classifier | `intent_classifier._check_identity()` | ✅ imports from identity_dataset |
| Emergency responder | `emergency_responder.py` | ⚠️ SEPARATE (safety layer) |

**Conflicts:** NONE
**Previous duplication:** 4 systems → NOW 1 canonical owner + 1 safety layer

---

## MEDIA TRANSPORT (pause/resume/stop/next)

| Aspect | Owner | Status |
|--------|-------|--------|
| Initial classification | `_IntentClassifier._classify_media_transport()` | ✅ CANONICAL |
| Transport patterns | `phrases.py` MEDIA_TRANSPORT | ✅ CENTRALIZED |
| Media manager follow-up | `media_manager._TRANSPORT_PATTERNS` | ⚠️ SEPARATE (follow-up state) |
| Context follow-up | `_classify_context_followup()` | ⚠️ SEPARATE (media acceptance) |
| Execution | `_exec_media()` transport_actions dict | ✅ CANONICAL |

**Conflicts:** LOW — legitimate separation between initial classification and follow-up state
**Previous duplication:** 5 layers → NOW 2 (initial + follow-up state)

---

## CONFIRMATION/REJECTION (yes/no/nah/next)

| Aspect | Owner | Status |
|--------|-------|--------|
| Context follow-up | `_classify_context_followup()` | ✅ CANONICAL |
| Pragmatics analysis | `pragmatics.py` affirmative detection | ✅ DATA INPUT |
| Media follow-up | `media_manager.process_followup()` | ✅ CANONICAL (media context) |
| Offer acceptance | `_exec_conversation()` accept_offer | ⚠️ SECONDARY FALLBACK |

**Conflicts:** LOW — pragmatics correctly yields affirmative phrases to media
**Risk:** `_exec_conversation` accept_offer path can fire if context_followup doesn't match

---

## SOCIAL/WISH (Happy Onam, Happy Birthday, etc.)

| Aspect | Owner | Status |
|--------|-------|--------|
| Pragmatics analysis | `pragmatics.py` is_social + acts | ✅ CANONICAL |
| Pipeline classification | `_classify_pragmatics_social()` | ✅ CANONICAL |
| Response generation | `render_social_reply()` | ✅ CANONICAL |
| Deterministic fallbacks | `_exec_conversation()` morning/evening | ⚠️ LOCAL |

**Conflicts:** NONE
**Key insight:** Cultural greetings ("Happy Onam") are classified by pragmatics as social, NOT by phrase list

---

## UTILITY (time/date/weather)

| Aspect | Owner | Status |
|--------|-------|--------|
| Classification | `_IntentClassifier._detect_utility()` | ✅ CANONICAL |
| Execution | `_exec_utility()` → `utilities.utility_answer()` | ✅ CANONICAL |
| Protected queries | `conversation_governor._PROTECTED_QUERIES` | ✅ FIXED (stale removed) |

**Conflicts:** NONE (after Phase 0 fix)
**Previous conflict:** Protected queries intercepted utility queries — FIXED

---

## KNOWLEDGE/INFORMATION

| Aspect | Owner | Status |
|--------|-------|--------|
| Classification | `_IntentClassifier._classify_entity_query()` | ✅ CANONICAL |
| Graph recall | `_apply_graph_recall_override()` | ✅ CANONICAL |
| Information query | `information_query` in media manager | ✅ CANONICAL |
| Web retrieval | `KnowledgeRouter` (Exa/Tavily/DDG) | ✅ CANONICAL |

**Conflicts:** NONE

---

## PROACTIVE BEHAVIOR

| Aspect | Owner | Status |
|--------|-------|--------|
| Goal notification | `monitoring/proactive.py` poll_proactive() | ✅ CANONICAL |
| Companion proactive | `companion/proactive.py` evaluate_proactive_items() | ⚠️ SEPARATE |
| Media proactive offer | `_maybe_proactive_offer()` in pipeline | ⚠️ EMBEDDED IN MEDIA |

**Conflicts:** MEDIUM — two separate proactive systems with different triggers
**Risk:** Both can fire independently, producing multiple proactive messages

---

## CONVERSATION STATE

| Aspect | Owner | Status |
|--------|-------|--------|
| Session context | `ContextManager` | ✅ CANONICAL |
| Conversation history | `ContextManager.append_exchange()` | ✅ CANONICAL |
| Runtime context | `remember_runtime_context()` | ✅ CANONICAL |
| Media session state | `MediaManager` internal state | ✅ CANONICAL |
| Semantic graph | `SemanticGraph` | ✅ CANONICAL |
| Living model | `living_model.py` | ✅ CANONICAL |

**Conflicts:** NONE — each owns different state domains

---

## SUMMARY MATRIX

| Concept | Canonical Owner | Duplicates | Conflicts |
|---------|----------------|------------|-----------|
| Greeting | phrases.py + pragmatics | 0 | NONE |
| Identity | identity_dataset.py | 0 | NONE |
| Media transport | phrases.py + _classify_media_transport | 0 | LOW |
| Confirmation/rejection | _classify_context_followup | 0 | LOW |
| Social/wish | pragmatics.py | 0 | NONE |
| Utility | _detect_utility + utilities.py | 0 | NONE |
| Knowledge | _classify_entity_query + KnowledgeRouter | 0 | NONE |
| Proactive | monitoring/proactive.py + companion/proactive.py | 1 | MEDIUM |
| Conversation state | ContextManager + runtime_context | 0 | NONE |
| Media follow-up | media_manager.process_followup | 0 | LOW |

**Total conflicts found:** 3 (LOW) + 1 (MEDIUM) = 4
**Total duplicate owners:** 1 (proactive)
**Canonical owners established:** 10/10 major concepts

---

## REMAINING OWNERSHIP GAPS

1. **Proactive behavior**: Two separate proactive systems (monitoring/proactive + companion/proactive)
   - Recommend: consolidate or establish clear boundaries (monitoring = stale goals, companion = contextual initiative)

2. **Media proactive offer**: `_maybe_proactive_offer()` is embedded inside `_exec_media()`
   - Recommend: extract to dedicated proactive offer layer with clear trigger conditions

3. **Deterministic greeting fallbacks**: `_exec_conversation()` morning/evening/afternoon fallbacks
   - Recommend: these are legitimate fast-path fallbacks when pragmatics/render_social_reply fails — keep as emergency fallback only
