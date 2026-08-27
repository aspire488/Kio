# DUPLICATED_DECISIONS — Refreshed Cross-Subsystem Duplication Audit

**Date:** August 26, 2026
**Previous audit:** 12 duplications found
**This audit:** 15 duplications found (3 new)

---

## CRITICAL DUPLICATIONS

### 1. Greeting Classification (7 implementations)

| # | File | Variable/Method | Purpose |
|---|------|----------------|---------|
| 1 | `pipeline/__init__.py` | `_IntentClassifier.GREETINGS` | Pipeline routing |
| 2 | `llm/intent_classifier.py` | `_is_greeting()` internal set | LLM intent classification |
| 3 | `resolvers/identity_resolver.py` | `_GREETING_CATEGORY` dict | Identity resolution |
| 4 | `core/context_manager.py` | stopword list | Context filtering |
| 5 | `core/continuity_resolver.py` | stopword list | Continuity resolution |
| 6 | `intelligence/emergency_responder.py` | tuple list | Emergency detection |
| 7 | `core/pragmatics.py` | `_GREETING_TOKENS` | Pragmatic analysis |

**Impact:** Adding a greeting requires updating 7 files. Missing any creates inconsistent behavior.
**Canonical owner:** Pipeline._IntentClassifier (with pragmatics as semantic analysis layer)

### 2. Media Transport Commands (5 implementations)

| # | File | Variable | Patterns |
|---|------|----------|----------|
| 1 | `pipeline/__init__.py` | `_IntentClassifier.MEDIA_TRANSPORT` | ~25 phrases |
| 2 | `media/media_manager.py` | `_TRANSPORT_PATTERNS` | ~9 regex |
| 3 | `media/media_manager.py` | `_VOLUME_UP/DOWN/SET` | 3 regex |
| 4 | `llm/intent_classifier.py` | `_DETERMINISTIC_MEDIA_ACTIONS` | 10 words |
| 5 | `intelligence/emergency_responder.py` | greeting tuples | ~6 patterns |

**Impact:** "pause" routes through 5 different pattern matchers.
**Canonical owner:** Pipeline._IntentClassifier → MediaManager

### 3. Identity Response (4 implementations)

| # | File | Variable | Purpose |
|---|------|----------|---------|
| 1 | `llm/identity_dataset.py` | `IDENTITY_ENTRIES` | Canonical answers |
| 2 | `llm/conversation_governor.py` | `_CANONICAL_KNOWLEDGE` | Duplicate knowledge |
| 3 | `llm/conversation_governor.py` | `_PROTECTED_QUERIES` | Protected queries |
| 4 | `resolvers/identity_resolver.py` | `_GREETING_VARIANTS` | Greeting responses |

**Impact:** Four systems can respond to identity questions.
**Canonical owner:** identity_dataset.py

---

## HIGH DUPLICATIONS

### 4. Casual Vocabulary (5 implementations)

| # | File | Variable | Count |
|---|------|----------|-------|
| 1 | `pipeline/__init__.py` | `_CASUAL_FRAGMENTS` | ~60 |
| 2 | `core/pragmatics.py` | `_CASUAL_VOCAB` | ~100 |
| 3 | `core/pragmatics.py` | `_GREETING_TOKENS` | ~30 |
| 4 | `llm/input_normalizer.py` | casual words list | ~5 |
| 5 | `media/intelligence/integration_adapter.py` | stopword set | ~20 |

### 5. Folder Keywords (3 implementations)

| # | File | Variable |
|---|------|----------|
| 1 | `pipeline/__init__.py` | `_IntentClassifier.FOLDER_KEYWORDS` |
| 2 | `command_parser.py` | `_FOLDER_KEYWORDS` |
| 3 | `core/context_manager.py` | stopword list |

### 6. Platform/Browser Names (4 implementations)

| # | File | Variable |
|---|------|----------|
| 1 | `pipeline/__init__.py` | `_KNOWN_BROWSER_NAMES` |
| 2 | `command_parser.py` | `_PLATFORM_MARKERS` |
| 3 | `command_parser.py` | `known_browsers` |
| 4 | `command_parser.py` | `known_webapps` |

### 7. Mood → Query Mapping (2 implementations)

| # | File | Variable | Values |
|---|------|----------|--------|
| 1 | `media_recommendation_engine.py` | `_MOOD_QUERIES` | 8 moods, 3 queries each |
| 2 | `media_context_intelligence.py` | Mood enum→query | 8 moods, DIFFERENT queries |

**Impact:** "happy" maps to different query lists in each file.

### 8. Contraction Maps (3 implementations)

| # | File | Variable |
|---|------|----------|
| 1 | `pipeline/__init__.py` | `_NormalizationService._CASUAL_CONTRACTION_MAP` |
| 2 | `pipeline/__init__.py` | `_IntentClassifier._CONTRACTION_EXPANSIONS` |
| 3 | `pipeline/__init__.py` | `_IntentClassifier._CASUAL_EXPANSIONS` |

### 9. Character Collapsing (2 implementations)

| # | File | Pattern | Behavior |
|---|------|---------|----------|
| 1 | `pipeline/__init__.py` | `_REPEATED_CHAR_RE = (.)\1+` | Collapse ALL |
| 2 | `core/pragmatics.py` | `_COLLAPSE3_RE = (.)\1{2,}` | Collapse 3+ only |

**Impact:** "yooo" → "yo" in pipeline, "yoo" stays "yoo" in pragmatics.

---

## MODERATE DUPLICATIONS

### 10. Provider Selection Logic (4 mechanisms)

| # | File | Mechanism |
|---|------|-----------|
| 1 | `llm_router.py` | Priority chain |
| 2 | `provider_registry.py` | Capability-based |
| 3 | `media_registry.py` | Priority table |
| 4 | `core/mcp/servers.py` | Server name registry |

### 11. Error Handling (5 patterns)

| # | File | Pattern |
|---|------|---------|
| 1 | `pipeline/__init__.py` | `except Exception → "Error: {str(exc)[:200]}"` |
| 2 | `llm_router.py` | Provider-specific fallback |
| 3 | `media_manager.py` | Media-specific error |
| 4 | `browser_connector/` | Browser-specific error |
| 5 | `kio_bot.py` | `"KIO encountered an error but is still running."` |

### 12. Response Templates (4 locations)

| # | File | Templates |
|---|------|-----------|
| 1 | `runtime_response_formatter.py` | Generic templates |
| 2 | `media_manager.py` | Media-specific responses |
| 3 | `resolvers/identity_resolver.py` | Identity/greeting responses |
| 4 | `pipeline/__init__.py` | Error/fallback responses |

### 13. Mood Classification (4 layers)

| # | File | Layer |
|---|------|-------|
| 1 | `pipeline/__init__.py` | Intent classification |
| 2 | `media_recommendation_engine.py` | Mood → genre |
| 3 | `media_context_intelligence.py` | Mood detection |
| 4 | `intelligence/proactive_evaluator.py` | Context → mood |

### 14. Topic Classification (2 implementations)

| # | File | Mechanism |
|---|------|-----------|
| 1 | `topic_classifier.py` | 9 keyword banks, 200+ keywords |
| 2 | `media_manager.py` | `_MEDIA_TOPIC_KEYWORDS` — 6 topic strings |

### 15. Configuration Values (4+ scattered locations)

| # | File | Values |
|---|------|--------|
| 1 | `core/config.py` | All env var defaults |
| 2 | `media_manager.py` | Media-specific defaults |
| 3 | `browser_connector/` | Browser-specific defaults |
| 4 | `runtime.py` | Runtime limits |

---

## DUPLICATIONS THAT SHOULD BE CONSOLIDATED

| Duplication | Canonical Owner | Phase |
|-------------|----------------|-------|
| Greeting classification (7x) | Pipeline._IntentClassifier | Phase 1 |
| Media transport (5x) | Pipeline → MediaManager | Phase 1 |
| Identity response (4x) | identity_dataset.py | Phase 3 |
| Casual vocabulary (5x) | Central phrase store | Phase 1 |
| Mood mapping (2x) | Config file | Phase 2 |
| Contraction maps (3x) | Central normalization | Phase 6 |
| Character collapsing (2x) | Single function | Phase 6 |
| Browser names (4x) | App registry config | Phase 5 |
| Folder keywords (3x) | Central phrase store | Phase 1 |

---

## DUPLICATIONS THAT ARE LEGITIMATE

| Duplication | Reason |
|-------------|--------|
| Pipeline intent + LLM intent classifier | Different layers (deterministic vs LLM) |
| Media session state + Media manager actions | State machine pattern |
| LLM system prompt + canonical knowledge | Different concerns (behavior vs facts) |
| Safety patterns in conversation_governor | Safety requires redundant checks |
| Runtime capability groups + execution boundary | Different abstraction levels |
