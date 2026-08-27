# HARDCODE_REDUCTION_ROADMAP — Prioritized Remediation Plan

**Date:** August 26, 2026
**Total findings:** 137 (22 CRITICAL, 68 HIGH, 35 MEDIUM, 12 LOW)
**Scope:** Audit only — NO implementation until approved

---

## PHASE 0: CRITICAL BUG FIXES (Week 1)

**Goal:** Fix live bugs caused by stale hardcoding
**Risk:** LOW (targeted fixes)
**Files changed:** 2

### 0.1 Delete Stale Protected Queries

**Finding:** H-056, H-057
**File:** `llm/conversation_governor.py`
**Action:** Remove `_PROTECTED_QUERIES["what time is it"]` and `_PROTECTED_QUERIES["what is the date"]`
**Reason:** These conflict with the pipeline's `_detect_utility` which now handles time/date queries deterministically. The protected query returns "I cannot tell you the time" when the pipeline ACTUALLY can.
**Risk:** LOW — removing dead code that conflicts with live code

### 0.2 Fix Protected Query Substring Matching

**Finding:** H-055
**File:** `llm/conversation_governor.py`
**Action:** Change substring matching (`query in normalized`) to exact match only
**Reason:** "what time is it" matches inside "what time is it in japan what time is it in india"
**Risk:** LOW — tightening match logic

---

## PHASE 1: CENTRALIZE DUPLICATED PHRASE STORES (Weeks 2-3)

**Goal:** Eliminate 7x greeting duplication, 5x media transport duplication, 5x casual vocabulary duplication
**Risk:** MEDIUM (many files touched, but behavior should be identical)
**Files changed:** ~15

### 1.1 Create Central Phrase Store

**New file:** `config/phrases.py` or `config/phrases.yaml`
**Action:** Define canonical phrase sets:
- `GREETINGS` — canonical greeting phrases
- `ACKNOWLEDGEMENTS` — acknowledgement phrases
- `THANKS` — thanks phrases
- `CASUAL_VOCABULARY` — casual/slang words
- `MEDIA_TRANSPORT` — media transport commands
- `DISCOVERY_PHRASES` — discovery intent phrases
- `FAREWELL` — farewell phrases
- `CONFIRMATION` — confirmation tokens
- `DISAGREEMENT` — disagreement tokens

### 1.2 Update Pipeline to Import from Central Store

**File:** `pipeline/__init__.py`
**Action:** Replace `_IntentClassifier.GREETINGS`, `ACKNOWLEDGEMENTS`, `THANKS`, `MEDIA_TRANSPORT`, `_CASUAL_FRAGMENTS` with imports from central store
**Risk:** MEDIUM — pipeline is the most critical file

### 1.3 Update Pragmatics to Import from Central Store

**File:** `core/pragmatics.py`
**Action:** Replace `_CASUAL_VOCAB`, `_GREETING_TOKENS`, `_AMUSEMENT_TOKENS`, etc. with imports from central store
**Risk:** LOW — pragmatics is read-only analysis

### 1.4 Update LLM Intent Classifier to Import from Central Store

**File:** `llm/intent_classifier.py`
**Action:** Replace `_is_greeting()` internal set with import from central store
**Risk:** LOW — secondary classifier

### 1.5 Update Identity Resolver to Import from Central Store

**File:** `resolvers/identity_resolver.py`
**Action:** Replace `_GREETING_CATEGORY` with import from central store
**Risk:** LOW — identity resolver is downstream

### 1.6 Update Emergency Responder

**File:** `intelligence/emergency_responder.py`
**Action:** Replace greeting tuples with import from central store
**Risk:** LOW — emergency responder is read-only

### 1.7 Update Context Manager and Continuity Resolver

**Files:** `core/context_manager.py`, `core/continuity_resolver.py`
**Action:** Replace stopword lists with shared imports
**Risk:** LOW

---

## PHASE 2: EXTERNALIZE MEDIA CONFIGURATION (Weeks 3-4)

**Goal:** Move entity databases, mood mappings, topic keywords to config
**Risk:** MEDIUM (media is complex, many interdependencies)
**Files changed:** ~8

### 2.1 Create Media Configuration Files

**New files:**
- `config/media/mood_queries.yaml`
- `config/media/activity_queries.yaml`
- `config/media/topic_keywords.yaml`
- `config/media/entity_databases.yaml`

### 2.2 Centralize Mood/Activity Mappings

**Files:** `media_recommendation_engine.py`, `media_context_intelligence.py`
**Action:** Replace `_MOOD_QUERIES`, `_ACTIVITY_QUERIES` with config-loaded data
**Fix duplication:** Two files define different mood→query mappings
**Risk:** MEDIUM

### 2.3 Externalize Topic Keywords

**File:** `topic_classifier.py`
**Action:** Replace 9 keyword banks with config-loaded data
**Risk:** LOW — topic classification is read-only

### 2.4 Externalize Entity Databases

**File:** `media_manager.py`
**Action:** Replace `_SPORTS_ENTITIES`, `_MOVIES_ENTITIES`, etc. with config-loaded data
**Risk:** MEDIUM — entities are used in routing

### 2.5 Externalize Similar Artists Map

**File:** `media_recommendation_engine.py`
**Action:** Replace `_SIMILAR_ARTISTS` with config or API integration
**Risk:** LOW — fallback only

---

## PHASE 3: CENTRALIZE IDENTITY/RESPONSE SYSTEM (Weeks 4-5)

**Goal:** Single identity owner, single response template system
**Risk:** MEDIUM (identity is user-visible)
**Files changed:** ~5

### 3.1 Consolidate Identity Knowledge

**Files:** `conversation_governor.py`, `identity_dataset.py`
**Action:** Remove `_CANONICAL_KNOWLEDGE` from conversation_governor. All identity answers come from identity_dataset.
**Risk:** MEDIUM

### 3.2 Create Response Template System

**New file:** `config/responses.py` or `config/responses.yaml`
**Action:** Move greeting variants, joke variants, error messages to templates
**Risk:** LOW

### 3.3 Update Identity Resolver

**File:** `resolvers/identity_resolver.py`
**Action:** Import greeting variants and joke pool from templates
**Risk:** LOW

---

## PHASE 4: EXTERNALIZE CONFIGURATION (Weeks 5-6)

**Goal:** Move hardcoded defaults to configuration files
**Risk:** LOW (defaults are overridable via env vars already)
**Files changed:** ~5

### 4.1 Create Master Configuration File

**New file:** `config/kio_config.yaml`
**Action:** Define all configuration with typed sections:
- `providers` (LLM provider priorities, models, timeouts)
- `browser` (names, ports, selectors)
- `media` (provider priorities, timeouts)
- `intelligence` (proactive weights, cooldowns)
- `runtime` (resource limits, context limits)

### 4.2 Create ConfigManager

**New file:** `config/manager.py`
**Action:** Load YAML, allow env var overrides, provide typed access
**Risk:** LOW

### 4.3 Update config.py

**File:** `core/config.py`
**Action:** Import defaults from ConfigManager instead of hardcoded values
**Risk:** LOW

---

## PHASE 5: EXTERNALIZE BROWSER/APP REGISTRY (Week 6)

**Goal:** Move browser names, app aliases, webapp URLs to config
**Risk:** LOW
**Files changed:** ~4

### 5.1 Create App Registry Config

**New file:** `config/apps.yaml`
**Action:** Define browsers, webapps, aliases, platform markers
**Risk:** LOW

### 5.2 Update Command Parser

**File:** `command_parser.py`
**Action:** Import aliases, known_webapps, known_browsers from config
**Risk:** LOW

### 5.3 Update Pipeline Browser Detection

**File:** `pipeline/__init__.py`
**Action:** Import `_KNOWN_BROWSER_NAMES` from config
**Risk:** LOW

---

## PHASE 6: STANDARDIZE NORMALIZATION (Week 7)

**Goal:** Fix repeated character collapsing inconsistency, centralize contraction maps
**Risk:** LOW
**Files changed:** ~3

### 6.1 Standardize Character Collapsing

**Files:** `pipeline/__init__.py`, `core/pragmatics.py`
**Action:** Use single collapse function (collapse 3+ repeats)
**Risk:** LOW

### 6.2 Centralize Contraction Maps

**Files:** `pipeline/__init__.py`, `llm/intent_classifier.py`
**Action:** Merge `_CASUAL_CONTRACTION_MAP`, `_CONTRACTION_EXPANSIONS`, `_CASUAL_EXPANSIONS` into single source
**Risk:** LOW

---

## PHASE 7: CLEANUP (Week 8)

**Goal:** Remove dead code, delete unused variables, update documentation
**Risk:** LOW
**Files changed:** ~5

### 7.1 Delete Dead Code

- `_IDENTITY_KEYWORDS` in conversation_governor.py (unused)
- `_SIMILAR_ARTISTS` static map (move to config or remove)
- Stale protected queries (already done in Phase 0)

### 7.2 Review Aggressive Quality Patterns

- `_CRINGE_PATTERNS` blocking "gonna", "wanna", "gotta" — review if too aggressive
- `_FILLER_ONLY_RE` blocking "right", "sure", "fine" — review if too aggressive

### 7.3 Update Documentation

- Update all audit documents to reflect changes
- Document the new configuration system
- Document the canonical phrase store

---

## IMPLEMENTATION ORDER

```
Phase 0: Critical bug fixes (2 files, 1-2 days)
    ↓
Phase 1: Centralize phrase stores (15 files, 2 weeks)
    ↓
Phase 2: Externalize media config (8 files, 1-2 weeks)
    ↓
Phase 3: Centralize identity/responses (5 files, 1 week)
    ↓
Phase 4: Externalize configuration (5 files, 1 week)
    ↓
Phase 5: Externalize browser/app registry (4 files, 3 days)
    ↓
Phase 6: Standardize normalization (3 files, 2 days)
    ↓
Phase 7: Cleanup (5 files, 2 days)
```

**Total estimated effort:** 6-8 weeks
**Total files changed:** ~45 (across all phases)
**Total new files:** ~8 (config files + manager)

---

## EXPECTED OUTCOMES

### Before (Current State)

- 137 hardcoded behaviors
- 7 duplicate greeting systems
- 5 duplicate media transport systems
- 4 duplicate identity systems
- 200+ hardcoded keywords in topic classifier
- 60+ hardcoded entity mappings
- No configuration file system
- Stale protected queries causing live bugs

### After (Target State)

- ~52 hardcoded behaviors (62% reduction)
- 1 canonical phrase store (imported by all layers)
- 1 canonical media transport classifier
- 1 canonical identity owner
- Topic keywords in config files (updatable without code changes)
- Entity databases in config/DB (refreshable)
- Unified configuration system with YAML + env var overrides
- No stale protected queries

### Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| Phase 0 | LOW | Targeted deletion of dead code |
| Phase 1 | MEDIUM | Comprehensive test suite (190 test files exist) |
| Phase 2 | MEDIUM | Media is complex; test media playback end-to-end |
| Phase 3 | MEDIUM | Identity is user-visible; test all identity queries |
| Phase 4 | LOW | Config loading with fallback to defaults |
| Phase 5 | LOW | App registry is read-only |
| Phase 6 | LOW | Normalization changes are minor |
| Phase 7 | LOW | Cleanup only |

---

## TESTING STRATEGY

### Unit Tests

- Verify all phrase set members are preserved after centralization
- Verify config loading with missing/invalid YAML
- Verify env var overrides work correctly
- Verify backward compatibility (same input → same output)

### Integration Tests

- Run existing 190 test files after each phase
- Test greeting detection across all entry points
- Test media transport across pipeline → media manager
- Test identity queries across all response paths

### Regression Tests

- Run `detect_changes()` before committing each phase
- Compare behavior before/after for each subsystem
- Live Telegram testing for user-visible changes

### Acceptance Criteria

- All existing tests pass
- No behavioral changes for existing inputs
- New config files load correctly
- Phrase centralization preserves all recognized forms
- Stale protected queries removed without breaking time/date functionality
