# HARDCODE_ARCHITECTURAL_GAPS — Missing Infrastructure for Decoupling

**Date:** August 26, 2026

---

## 1. MISSING: Single Phrase/Keyword Store

### Problem

Greetings, casual vocabulary, acknowledgement phrases, and social tokens are defined independently in 5+ files. There is NO single source of truth.

### Evidence

| Phrase | pipeline | pragmatics | intent_classifier | identity_resolver | context_manager |
|--------|----------|------------|-------------------|-------------------|-----------------|
| "hello" | ✅ GREETINGS | ✅ _GREETING_TOKENS | ✅ _is_greeting() | ✅ _GREETING_CATEGORY | ✅ stopword |
| "hey" | ✅ | ✅ | ✅ | ✅ | ✅ |
| "yo" | ✅ | ✅ | ✅ | — | — |
| "sup" | ✅ | ✅ | ✅ | — | — |
| "wassup" | ✅ | ✅ | ✅ | ✅ | — |
| "hola" | ✅ | ✅ | — | — | — |
| "bro" | — | ✅ | — | — | — |
| "bruh" | — | ✅ | — | — | — |

### Required Infrastructure

```
config/
  phrases/
    greetings.yaml        # canonical greeting phrases
    acknowledgements.yaml # acknowledgement phrases
    casual_vocabulary.yaml # casual/slang words
    farewell.yaml         # farewell phrases
    thanks.yaml           # thanks phrases
    media_transport.yaml  # media transport commands
    discovery_phrases.yaml # discovery intent phrases
```

Or a single `phrases.yaml` with sections. The Pipeline, pragmatics layer, and intent classifier all import from this single source.

---

## 2. MISSING: Dynamic Entity Database

### Problem

Sports entities, movie entities, TV entities, music entities, gaming entities, and sports events are hardcoded as Python dicts in `media_manager.py`. They become stale immediately.

### Evidence

```python
_SPORTS_EVENTS = {
    "germany_vs_curacao": ["germany vs curacao", ...],  # Specific match
    "brazil_vs_argentina": ["brazil vs argentina", ...],
}
```

### Required Infrastructure

- SQLite table or JSON file for entity→aliases mappings
- API integration for live sports events
- Periodic refresh for movie/TV/music entities
- Or: remove static entity databases entirely and rely on web search for entity resolution

---

## 3. MISSING: Topic Classification Configuration

### Problem

9 keyword banks in `topic_classifier.py` with 200+ keywords total are hardcoded in Python. Adding a new topic or updating keywords requires code changes.

### Required Infrastructure

```
config/
  topics/
    movies.yaml     # keywords, hard_locks, high_weight
    tv.yaml
    gaming.yaml
    sports.yaml
    music.yaml
    tech.yaml
    news.yaml
    books.yaml
    people.yaml
    priority.yaml   # topic priority order
```

---

## 4. MISSING: Mood/Activity Configuration

### Problem

Mood→query and activity→query mappings are hardcoded in TWO different files with DIFFERENT values.

### Required Infrastructure

```
config/
  media/
    mood_queries.yaml    # mood → search query templates
    activity_queries.yaml # activity → search query templates
    similar_artists.yaml  # artist similarity (or: API integration)
    content_types.yaml    # content type definitions
```

---

## 5. MISSING: Protected Query Registry

### Problem

`_PROTECTED_QUERIES` uses substring matching (`query in normalized`) which is too broad. "what time is it" matches inside "what time is it in japan what time is it in india". Also, some protected queries conflict with pipeline's deterministic routing.

### Required Infrastructure

- Exact-match-only registry (no substring matching)
- Validation that protected queries don't conflict with pipeline deterministic routes
- Single source of truth (not duplicated across conversation_governor and identity_dataset)

---

## 6. MISSING: Response Template System

### Problem

Greeting responses, identity responses, joke variants, and error messages are hardcoded in `identity_resolver.py` and `conversation_governor.py`.

### Required Infrastructure

```
config/
  responses/
    greetings.yaml     # category → response variants
    identity.yaml      # identity answer variants
    jokes.yaml         # joke pool
    errors.yaml        # error message templates
    proactive.yaml     # proactive suggestion templates
```

---

## 7. MISSING: Configuration File System

### Problem

All configuration is scattered across `config.py` (env vars with defaults), inline constants in source files, and hardcoded dicts. There is no unified configuration system.

### Required Infrastructure

```
config/
  kio_config.yaml      # master configuration
  providers.yaml       # LLM provider priorities and settings
  browser.yaml         # browser names, ports, selectors
  media.yaml           # media provider priorities, timeouts
  intelligence.yaml    # proactive weights, cooldowns, thresholds
  runtime.yaml         # resource limits, context limits
```

With a `ConfigManager` class that:
1. Loads from YAML
2. Allows env var overrides
3. Supports hot-reload
4. Provides typed access

---

## 8. MISSING: Contraction/Normalization Centralization

### Problem

Two separate contraction maps exist:
- `_NormalizationService._CASUAL_CONTRACTION_MAP` (25+ entries)
- `_IntentClassifier._CONTRACTION_EXPANSIONS` (8 entries)
- `_IntentClassifier._CASUAL_EXPANSIONS` (8 entries)

Plus the pragmatics layer has its own character collapsing logic.

### Required Infrastructure

Single `_NormalizationConfig` class with all contraction/expansion maps, loaded from config.

---

## 9. MISSING: Browser/App Registry

### Problem

Browser names, app aliases, webapp URLs, and platform markers are hardcoded in multiple files.

### Required Infrastructure

```
config/
  apps/
    browsers.yaml    # browser names, executables, process names
    webapps.yaml     # webapp → URL mappings
    aliases.yaml     # app name aliases
    platforms.yaml   # platform markers
```

---

## 10. MISSING: Repeated Character Collapsing Standard

### Problem

Two different collapse strategies exist:
- Pipeline: `_REPEATED_CHAR_RE = re.compile(r"(.)\1+")` — collapses ALL repeats
- Pragmatics: `_COLLAPSE3_RE = re.compile(r"(.)\1{2,}")` — collapses 3+ repeats only

"yooo" → "yo" in pipeline, "yoo" stays "yoo" in pragmatics.

### Required Infrastructure

Single collapse function used by all layers. Recommended: collapse 3+ repeats (pragmatics approach) as it's more linguistically accurate.

---

## GAP PRIORITY MATRIX

| Gap | Impact | Effort | Priority |
|-----|--------|--------|----------|
| Single Phrase Store | CRITICAL (7x duplication) | Medium | P0 |
| Dynamic Entity Database | HIGH (stale data) | High | P1 |
| Protected Query Registry | CRITICAL (live bugs) | Low | P0 |
| Configuration File System | HIGH (scattered config) | High | P1 |
| Topic Classification Config | HIGH (stale keywords) | Medium | P1 |
| Mood/Activity Config | HIGH (duplicated + stale) | Medium | P1 |
| Response Template System | MEDIUM (hardcoded responses) | Medium | P2 |
| Browser/App Registry | MEDIUM (hardcoded names) | Low | P2 |
| Contraction Centralization | MEDIUM (inconsistent normalization) | Low | P2 |
| Collapse Standardization | LOW (minor inconsistency) | Low | P3 |
