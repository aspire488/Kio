# HARDCODE_COMPLETE_INVENTORY.md
# Complete Hardcoding Inventory — KIO System
# ==========================================

## METHODOLOGY
Repository-wide scan of all .py, .json, .yaml, .toml files.
Distinguished: hardcoded BEHAVIOR vs legitimate DETERMINISTIC constants.

---

## CATEGORY A: USER-VISIBLE STRINGS

### A1. Greetings (centralized in phrases.py)
- `mini_kio/core/phrases.py`: GREETINGS frozenset (~30 entries)
- `mini_kio/core/pipeline/__init__.py`: _CASUAL_FRAGMENTS (50+ entries) — entity suppression, not routing
- `mini_kio/core/pipeline/__init__.py`: _KNOWN_USER_NAMES — anti-fabrication guard
- Status: ✅ CENTRALIZED

### A2. Identity responses
- `mini_kio/llm/identity_dataset.py`: ~17 identity Q&A pairs
- Status: ✅ CANONICAL

### A3. Deterministic greeting fallbacks
- `mini_kio/core/pipeline/__init__.py:7760-7780`: "Good morning!" / "Good evening!" / "Good afternoon!"
- `mini_kio/core/pipeline/__init__.py:7783-7790`: "Hey! KIO here — how can I help?"
- `mini_kio/core/pipeline/__init__.py:7815-7830`: "All good on my end..." / "Running fine..." / "Everything's working..."
- Status: ⚠️ DETERMINISTIC FALLBACKS (should only fire when LLM unavailable)

### A4. Error responses
- `mini_kio/core/runtime.py`: "Runtime not initialized." / "Runtime is not accepting input." / "Input too long..."
- `mini_kio/core/pipeline/__init__.py`: "Error: ..." / "Command failed." / "Conversation action not implemented."
- `kio_bot.py`: "KIO encountered an error but is still running." / "Unauthorized."
- Status: ✅ LEGITIMATE ERROR MESSAGES

### A5. Media responses
- `mini_kio/media/media_manager.py`: various play/pause/stop confirmations
- Status: ✅ LEGITIMATE MEDIA STATE RESPONSES

### A6. Proactive media offers
- `mini_kio/core/pipeline/__init__.py:7450`: offer_line appended to information queries
- Status: ⚠️ EMBEDDED — should be separate layer

---

## CATEGORY B: PHRASE/KEYWORD HARDCODING

### B1. Canonical phrase sets (centralized)
- `mini_kio/core/phrases.py`: GREETINGS, ACKNOWLEDGEMENTS, THANKS, MEDIA_TRANSPORT, SYSTEM_ACTIONS, FOLDER_KEYWORDS, FORBIDDEN_TARGETS
- Status: ✅ CENTRALIZED (single source of truth)

### B2. Discovery targets
- `mini_kio/core/pipeline/__init__.py:18-55`: _DISCOVERY_TARGETS (~40 entries), _DISCOVERY_PREFIXES (~10 entries)
- Status: ⚠️ LARGE BUT BOUNDED — legitimate media discovery vocabulary

### B3. Context follow-up phrases
- `mini_kio/core/pipeline/__init__.py:5153+`: _classify_context_followup — acceptance/rejection phrases
- Status: ✅ CANONICAL (single owner)

### B4. Discourse morphology patterns
- `mini_kio/core/pipeline/__init__.py`: _CALLBACK_RE, _INFO_REQUEST_RE, _COMPANION_RE
- Status: ✅ LEGITIMATE — generic regex patterns, not phrase lists

### B5. Casual fragments
- `mini_kio/core/pipeline/__init__.py:155-165`: _CASUAL_FRAGMENTS (~60 entries)
- Status: ✅ ENTITY SUPPRESSION (prevents "yo"/"lol" from becoming entity queries)

### B6. Verification probe vocabulary
- `mini_kio/core/pipeline/__init__.py:~750`: _VERIF_PROBE_TOKENS (~40 entries)
- Status: ✅ LEGITIMATE — verification detection vocabulary

### B7. Protected queries
- `mini_kio/llm/conversation_governor.py`: _PROTECTED_QUERIES (~15 entries, after cleanup)
- Status: ✅ FIXED — stale queries removed, exact-match only

### B8. KIO identity triggers
- `mini_kio/llm/identity_dataset.py`: ~17 trigger patterns
- Status: ✅ CANONICAL

### B9. Topic keywords
- `mini_kio/media/intelligence/topic_classifier.py`: 9 static keyword banks (~200+ keywords)
- Status: ⚠️ LARGE STATIC BANK — candidates for semanticization

### B10. Media search queries (fallback)
- `mini_kio/media/media_manager.py`: "good music to listen to" fallback
- Status: ⚠️ HARDCODED FALLBACK — should be last resort

### B11. Mood/activity mappings
- `mini_kio/media/intelligence/media_context_intelligence.py`: activity → query mappings
- Status: ⚠️ STATIC MAPPING — could be semantic

---

## CATEGORY C: ROUTING HARDCODING

### C1. Intent → capability mapping
- `mini_kio/core/pipeline/__init__.py:5787-5900`: _CapabilityResolver static mapping dict
- Status: ✅ CANONICAL — single routing table

### C2. Execution dispatch table
- `mini_kio/core/pipeline/__init__.py:5910-5925`: _ExecutionCoordinator._dispatch() dispatch dict
- Status: ✅ CANONICAL — single dispatch table

### C3. Transport action mapping
- `mini_kio/core/pipeline/__init__.py:7250-7270`: transport_actions dict in _exec_media
- Status: ✅ CANONICAL — single transport mapping

### C4. Long-op pool keywords
- `kio_bot.py:155-160`: _LONG_KEYWORDS tuple
- Status: ✅ LEGITIMATE — thread pool routing heuristic

---

## CATEGORY D: RESPONSE HARDCODING

### D1. Every return "..." location
Found in:
- `_exec_conversation()`: 8 deterministic response paths
- `_exec_utility()`: utility_answer responses
- `identity_dataset.py`: 17 identity responses
- `render_social_reply()`: social responses
- Error paths: ~12 error message strings
- Total: ~50+ response strings across codebase

Status: ✅ MOSTLY LEGITIMATE (deterministic responses or error messages)

---

## CATEGORY E: SEMANTIC HARDCODING

### E1. Activity → music query
- "while I eat" → food/cooking music
- "while studying" → study/lofi music
- "while coding" → coding playlist
- Location: `media_context_intelligence.py`
- Status: ⚠️ STATIC MAPPING — candidates for semantic resolution

### E2. Bored → media recommendation
- "I'm bored" → project recommendation OR music
- Location: `_classify_emotion()` + `_DISCOVERY_TARGETS`
- Status: ⚠️ COMPETING ROUTING — boredom can be emotion OR discovery

### E3. Social → fixed reply patterns
- "good morning" → "Good morning! How can I help?"
- Location: `_exec_conversation()` deterministic fallback
- Status: ✅ EMERGENCY FALLBACK only (LLM preferred)

---

## CATEGORY F: FALLBACK HARDCODING

### F1. Provider fallback chain
- Gemini → Groq → OpenRouter → Together → Cerebras
- Location: `llm/llm_ops.py`
- Status: ✅ LEGITIMATE — provider priority chain

### F2. Greeting response fallback chain
1. render_social_reply() → 2. morning/evening/afternoon → 3. _chat_converse() → 4. "Hey! KIO here"
- Location: `_exec_conversation()` greeting template
- Status: ✅ LEGITIMATE — progressive fallback

### F3. Conversation fallback
- _chat_converse() returns None → "My language providers are having a rough moment..."
- Location: `_exec_conversation()` converse action
- Status: ✅ LEGITIMATE — honest failure message

---

## CATEGORY G: DEFAULTS

### G1. Ports/URLs
- Browser connector: port 9877
- Status: ✅ CONFIGURABLE via env vars

### G2. Timeouts/retries
- Telegram timeouts: 30s (kio_bot.py)
- LLM provider timeouts: varies per provider
- Status: ✅ LEGITIMATE

### G3. Limits
- Runtime context limit: 16 items
- Runtime context TTL: 300s
- RAM budget: 350MB soft, 400MB hard
- Observer limit: 8
- Status: ✅ LEGITIMATE ENGINEERING LIMITS

---

## CATEGORY H: PROACTIVE HARDCODING

### H1. Stale goal threshold
- `monitoring/proactive.py`: MIN_AGE_S = 24 * 3600
- Status: ✅ LEGITIMATE — minimum age before proactive notification

### H2. Proactive cooldown
- `companion/proactive.py`: _proactive_cooldown_messages = 3
- Status: ✅ LEGITIMATE — rate limiting

### H3. Proactive confidence thresholds
- `companion/proactive.py`: confidence >= 0.4, relevance >= 0.3
- `monitoring/proactive.py`: MIN_CONFIDENCE = 0.5
- Status: ✅ LEGITIMATE — quality thresholds

### H4. Proactive session list
- `monitoring/proactive.py`: DEFAULT_SESSIONS = ("tg_2146008061",)
- Status: ⚠️ HARDCODED SESSION ID — should be configurable

---

## CATEGORY I: LEGACY/DEAD CODE

### I1. _reply_greeting() method
- `mini_kio/core/pipeline/__init__.py:7815`: _reply_greeting() — 30+ lines of deterministic greeting responses
- Status: ⚠️ DEAD CODE — never called from _exec_conversation (pragmatics + LLM preferred)
- Recommendation: Remove or keep as documented emergency fallback

### I2. _CASUAL_FRAGMENTS overlaps
- Pipeline _CASUAL_FRAGMENTS vs phrases.py ACKNOWLEDGEMENTS vs pragmatics vocabulary
- Status: ⚠️ OVERLAP — could consolidate

---

## TOTAL INVENTORY

| Category | Count | Centralized? | Action Needed |
|----------|-------|-------------|---------------|
| A. User-visible strings | ~50 | Mostly | No |
| B. Phrase/keyword hardcoding | ~11 banks | Mostly | Phase 2 review |
| C. Routing hardcoding | 4 tables | YES | No |
| D. Response hardcoding | ~50 strings | Distributed | No |
| E. Semantic hardcoding | ~5 mappings | No | Phase 2 review |
| F. Fallback hardcoding | 3 chains | YES | No |
| G. Defaults | ~15 values | Mostly | No |
| H. Proactive hardcoding | ~8 values | Distributed | 1 fix needed |
| I. Legacy/dead code | ~2 items | N/A | Cleanup |

**Total findings:** ~146 individual hardcoding instances
**Actionable for reduction:** ~25 (phrase banks, semantic mappings, dead code)
**Legitimately deterministic:** ~121 (error messages, limits, fallbacks, constants)
