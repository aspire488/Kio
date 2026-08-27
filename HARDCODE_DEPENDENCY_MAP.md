# HARDCODE_DEPENDENCY_MAP — Cross-Finding Dependencies

**Date:** August 26, 2026

---

## DEPENDENCY GRAPH

### Cluster 1: Phrase Store Duplication (7 findings → 1 fix)

```
H-001 (pipeline GREETINGS) ─────┐
H-002 (pipeline ACKNOWLEDGEMENTS) ──┤
H-003 (pipeline THANKS) ────────┤
H-073 (intent_classifier _is_greeting) ──┤──→ FIX: Central Phrase Store (Phase 1)
H-075 (identity_resolver _GREETING_CATEGORY) ──┤
H-109 (pragmatics _CASUAL_VOCAB) ──────┤
H-110 (pragmatics _GREETING_TOKENS) ───┘
```

**Dependency:** All 7 findings share the same root cause (no single phrase store). Fixing H-001 fixes all 7.

### Cluster 2: Media Transport Duplication (5 findings → 1 fix)

```
H-004 (pipeline MEDIA_TRANSPORT) ─────┐
H-074 (intent_classifier _DETERMINISTIC_MEDIA_ACTIONS) ──┤
H-082 (media_manager _TRANSPORT_PATTERNS) ──┤──→ FIX: Canonical Transport Classifier (Phase 1)
H-083 (media_manager _VOLUME_UP/DOWN/SET) ──┤
H-133 (emergency_responder greeting tuples) ──┘
```

### Cluster 3: Identity Duplication (4 findings → 1 fix)

```
H-054 (conversation_governor _CANONICAL_KNOWLEDGE) ──┐
H-055 (conversation_governor _PROTECTED_QUERIES) ───┤
H-076 (identity_resolver _GREETING_VARIANTS) ───────┤──→ FIX: Single Identity Owner (Phase 3)
H-077 (identity_resolver _JOKE_VARIANTS) ───────────┘
```

### Cluster 4: Mood/Activity Duplication (2 findings → 1 fix)

```
H-094 (media_recommendation_engine _MOOD_QUERIES) ──┐
H-096 (media_context_intelligence mood→query) ──────┘──→ FIX: Centralize Mood Config (Phase 2)
```

### Cluster 5: Topic Keywords (10 findings → 1 fix)

```
H-097 (_MOVIES_KW) ─────┐
H-098 (_TV_KW) ──────────┤
H-099 (_GAMING_KW) ──────┤
H-100 (_SPORTS_KW) ──────┤
H-101 (_MUSIC_KW) ───────┤
H-102 (_TECH_KW) ────────┤──→ FIX: Topic Config Files (Phase 2)
H-103 (_NEWS_KW) ────────┤
H-104 (_BOOKS_KW) ───────┤
H-105 (_PEOPLE_KW) ──────┤
H-106 (_HARD_LOCK) ──────┘
```

### Cluster 6: Entity Databases (6 findings → 1 fix)

```
H-086 (_SPORTS_ENTITIES) ──┐
H-087 (_MOVIES_ENTITIES) ──┤
H-088 (_TV_ENTITIES) ──────┤
H-089 (_MUSIC_ENTITIES) ───┤──→ FIX: Entity Config/DB (Phase 2)
H-090 (_GAMING_ENTITIES) ──┤
H-091 (_SPORTS_EVENTS) ────┘
```

### Cluster 7: Contraction Maps (3 findings → 1 fix)

```
H-011 (_CASUAL_CONTRACTION_MAP) ──┐
H-012 (_CONTRACTION_EXPANSIONS) ──┤──→ FIX: Central Normalization (Phase 6)
H-013 (_CASUAL_EXPANSIONS) ───────┘
```

### Cluster 8: Browser/App Names (4 findings → 1 fix)

```
H-030 (_KNOWN_BROWSER_NAMES in pipeline) ──┐
H-039 (_PLATFORM_MARKERS in parser) ───────┤
H-045 (known_browsers in parser) ──────────┤──→ FIX: App Registry Config (Phase 5)
H-044 (known_webapps in parser) ───────────┘
```

### Cluster 9: Folder Keywords (3 findings → 1 fix)

```
H-006 (pipeline FOLDER_KEYWORDS) ──┐
H-037 (parser _FOLDER_KEYWORDS) ───┤──→ FIX: Central Phrase Store (Phase 1)
H-??? (other folder references) ───┘
```

### Cluster 10: Character Collapsing (2 findings → 1 fix)

```
H-033 (pipeline _REPEATED_CHAR_RE) ──┐
H-118 (pragmatics _COLLAPSE3_RE) ────┘──→ FIX: Standardize Collapse (Phase 6)
```

---

## INDEPENDENT FINDINGS (No cluster dependency)

These findings can be fixed independently:

| ID | Description | Phase |
|----|-------------|-------|
| H-056 | Stale "what time is it" protected query | Phase 0 |
| H-057 | Stale "what is the date" protected query | Phase 0 |
| H-049 | LLM provider defaults | Phase 4 |
| H-050 | Browser connector port | Phase 4 |
| H-051 | Default browser | Phase 4 |
| H-119 | Proactive interruption costs | Phase 4 |
| H-120 | Proactive source values | Phase 4 |
| H-121 | Urgency multipliers | Phase 4 |
| H-122 | Cooldown timer | Phase 4 |
| H-128-132 | Runtime constants | Phase 4 |
| H-135 | Long operation keywords | Phase 4 |
| H-068 | Unused _IDENTITY_KEYWORDS | Phase 7 |
| H-093 | Static similar artists map | Phase 2 or 7 |

---

## FIX ORDERING (Dependency-Aware)

```
Phase 0 (no dependencies):
  H-056, H-057 → Delete stale protected queries

Phase 1 (depends on nothing):
  H-001-H-003, H-073, H-075, H-109-H-110 → Central phrase store
  H-004, H-074, H-082-H-083, H-133 → Canonical transport classifier
  H-006, H-037 → Folder keywords (part of phrase store)

Phase 2 (depends on Phase 1):
  H-094, H-096 → Mood config (after phrase store exists)
  H-097-H-106 → Topic config files
  H-086-H-091 → Entity databases
  H-093 → Similar artists

Phase 3 (depends on Phase 1):
  H-054, H-055, H-076, H-077 → Identity consolidation

Phase 4 (depends on nothing):
  H-049-H-053, H-119-H-122, H-128-H-132, H-135-H-137 → Config system

Phase 5 (depends on Phase 1):
  H-030, H-039, H-044-H-045 → App registry

Phase 6 (depends on Phase 1):
  H-011-H-013, H-033, H-118 → Normalization standardization

Phase 7 (depends on nothing):
  H-068 → Delete unused code
```

---

## CLUSTER SIZE SUMMARY

| Cluster | Findings | Fix Effort | Impact |
|---------|----------|------------|--------|
| Phrase Store Duplication | 7 | Medium | CRITICAL |
| Media Transport Duplication | 5 | Medium | CRITICAL |
| Identity Duplication | 4 | Medium | HIGH |
| Topic Keywords | 10 | Low (config files) | HIGH |
| Entity Databases | 6 | Medium | HIGH |
| Mood/Activity Duplication | 2 | Low | HIGH |
| Browser/App Names | 4 | Low | MEDIUM |
| Contraction Maps | 3 | Low | MEDIUM |
| Folder Keywords | 3 | Low | MEDIUM |
| Character Collapsing | 2 | Low | LOW |
| **Total clustered** | **46** | | |
| **Independent** | **14** | | |
| **Safety/keep** | **77** | N/A | N/A |
