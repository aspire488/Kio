# HARDCODE_SEMANTICIZATION_CANDIDATES — Phrase Matching → Semantic Interpretation

**Date:** August 26, 2026

---

## 1. GREETING DETECTION

### Current: Phrase List Matching

```python
GREETINGS = frozenset({
    "hello", "hi", "hey", "yo", "hola", "sup", "wassup", 
    "what's up", "whats up", "good morning", "good afternoon", ...
})
```

### Problem

New greeting forms ("greetings", "salutations", "howdy", "top of the morning") require adding to the phrase list. Slang evolves ("ayyo", "sheesh") and must be manually added.

### Semantic Alternative

A greeting is any short, socially-oriented utterance that doesn't contain a task verb or information request. Instead of listing greetings, detect:
1. Short length (< 5 words)
2. No task verb (open, play, search, etc.)
3. No information query (what, how, when, etc.)
4. Social/casual register (from pragmatics layer)

The pragmatics layer ALREADY does this partially — it classifies conversational acts. The pipeline should delegate greeting detection to the pragmatics layer instead of maintaining its own phrase list.

### Recommendation

**PRAGMATICS already owns this.** The pipeline's `GREETINGS` frozenset should be reduced to a small set of CANONICAL forms for deterministic routing, while the pragmatics layer handles the full vocabulary.

---

## 2. CASUAL VOCABULARY RECOGNITION

### Current: 100+ Word Phrase List

```python
_CASUAL_VOCAB = frozenset({
    "yo", "yoo", "hey", "heyy", "hi", "hii", "hello", "sup", "wassup",
    "wazzup", "whatsup", "wassgood", "ayy", "aye", "ayo", "hola",
    "howdy", "mornin", ...  # 100+ words
})
```

### Problem

Every new slang word requires a code change. The list grows indefinitely.

### Semantic Alternative

Casual vocabulary is characterized by:
1. Short, informal words
2. Non-standard spelling (repeated chars, missing apostrophes)
3. Social function (not task-oriented)
4. Low information content

The pragmatics layer already measures formality, playfulness, and energy. Instead of listing casual words, USE the register analysis:
- `register.formality <= -1` → casual
- `register.playfulness >= 1` → playful
- `register.energy >= 1` → high-energy

### Recommendation

Reduce `_CASUAL_VOCAB` to a CANONICAL set (20-30 most common). Let pragmatics handle the rest.

---

## 3. MEDIA TRANSPORT COMMANDS

### Current: 5 Duplicate Pattern Systems

```python
# Pipeline
MEDIA_TRANSPORT = frozenset({"pause", "resume", "stop", "next", "previous", ...})

# Media Manager
_TRANSPORT_PATTERNS = {
    re.compile(r"\b(pause|hold on|wait|stop music for now)\b"): "pause",
    re.compile(r"\b(resume|continue|unpause|play again|keep going)\b"): "resume",
    ...
}
```

### Problem

"hold on" → pipeline doesn't recognize it (not in MEDIA_TRANSPORT), but media manager does (in _TRANSPORT_PATTERNS). Inconsistent behavior depending on which code path runs.

### Semantic Alternative

Media transport is a SEMANTIC category: "the user wants to control playback." Instead of listing every possible phrase:
1. Detect media context (is media playing?)
2. Detect control intent (user wants to change state)
3. Detect specific action (pause/stop/resume/next/prev)

The specific action can still use keyword matching, but the CONTEXT detection should be semantic.

### Recommendation

Single canonical transport classifier. Pipeline classifies → MediaManager executes. No duplicate pattern matching.

---

## 4. DISCOVERY INTENT

### Current: 30+ Exact Phrases

```python
_DISCOVERY_TARGETS = frozenset({
    "something random", "something", "anything", "anything random",
    "surprise me", "surprise", "whatever", "idk", "i don't know",
    "show me something", "find something", "pick something",
    "play something", "play anything", "play random",
    ...
})
```

### Problem

"I'm bored" used to be in this set (and triggered media) but was REMOVED because it shouldn't auto-trigger. The boundary between "discovery intent" and "emotional expression" is defined by phrase membership.

### Semantic Alternative

Discovery intent is: "the user wants media but hasn't specified what." Instead of listing phrases:
1. User expresses willingness to consume media
2. User does NOT specify a particular entity
3. User delegates choice to KIO

This is a SEMANTIC state, not a phrase match. The `_DISCOVERY_TARGETS` set should be reduced to a small canonical set, with the pragmatics/intelligence layer handling the semantic detection.

### Recommendation

Reduce to ~10 canonical forms. Add semantic detection: "user wants media + no entity specified + delegates choice."

---

## 5. TOPIC CLASSIFICATION

### Current: 200+ Keywords in 9 Banks

```python
_SPORTS_KW = {"fifa", "world cup", "premier league", "la liga", ...}
_MOVIES_KW = {"movie", "film", "cinema", "trailer", ...}
_GAMING_KW = {"game", "gta", "gameplay", ...}
```

### Problem

1. Static — new movies, games, artists never added
2. Keyword overlap — "trailer" appears in both movies and gaming
3. No semantic understanding — "the bear" is a TV show, not an animal

### Semantic Alternative

Topic classification should be SEMANTIC:
1. Use the LLM's existing knowledge for entity→topic mapping
2. Use web search results to determine topic
3. Use the entity's own metadata (YouTube channel, Spotify artist type)
4. Fallback to keyword matching only for ambiguous cases

### Recommendation

Reduce keyword banks to HIGH-WEIGHT disambiguation terms only. Delegate entity→topic to the LLM or web search.

---

## 6. IDENTITY RESPONSE

### Current: 4 Duplicate Systems

1. `identity_dataset.py` — canonical answers
2. `conversation_governor.py` — `_CANONICAL_KNOWLEDGE` + `_PROTECTED_QUERIES`
3. `identity_resolver.py` — greeting/joke responses
4. `pipeline/_check_identity()` — routing

### Problem

Four systems can respond to identity questions. The identity dataset is canonical, but the others can interfere.

### Semantic Alternative

Identity is a SEMANTIC category: "the user is asking about KIO itself." This should be detected ONCE and routed to the canonical identity system. No duplicate response generation.

### Recommendation

Single identity owner. Pipeline routes → identity_dataset answers. Remove duplicate knowledge from conversation_governor.

---

## 7. EMOTION/MOOD DETECTION

### Current: Hardcoded Mood → Query Mappings

```python
_MOOD_QUERIES = {
    "happy": ["feel good songs", "happy music playlist", "upbeat hits"],
    "sad": ["sad songs playlist", "emotional music", "heartbreak playlist"],
    ...
}
```

### Problem

Mood→query is a STATIC mapping. User says "I'm happy" → hardcoded query "feel good songs" regardless of the user's actual happy music preferences.

### Semantic Alternative

Mood should INFLUENCE recommendations, not DICTATE them:
1. Detect mood from context (pragmatics layer already does this)
2. Use mood as a WEIGHT in the recommendation engine
3. Combine with user's actual listening history
4. Let the recommendation engine generate appropriate queries

### Recommendation

Remove static mood→query mappings. Use mood as a signal in the preference model.

---

## 8. PROACTIVE BEHAVIOR

### Current: Hardcoded Weights and Thresholds

```python
_SOURCE_INTERRUPTION_COST = {"watcher_change": 0.2, "reminder_due": 0.1, ...}
_SOURCE_VALUE = {"watcher_change": 0.8, "reminder_due": 0.9, ...}
urgency_mult = {CRITICAL: 2.0, HIGH: 1.5, MEDIUM: 1.0, LOW: 0.5}
cooldown_s = 1800.0
```

### Problem

Proactive behavior is driven by hardcoded weights. KIO decides what to surface based on developer-encoded values, not learned user preferences.

### Semantic Alternative

Proactive behavior should be:
1. Driven by user-explicit preferences ("remind me about X")
2. Learned from user responses (positive/negative feedback)
3. Context-aware (time of day, user activity, conversation state)
4. NOT driven by static weights

### Recommendation

Move weights to config. Add feedback loop for learning.

---

## SEMANTICIZATION PRIORITY

| Behavior | Current Mechanism | Semantic Alternative | Priority |
|----------|------------------|---------------------|----------|
| Greeting detection | 7x phrase lists | Pragmatics layer delegation | P0 |
| Media transport | 5x pattern systems | Single canonical classifier | P0 |
| Identity response | 4x duplicate systems | Single identity owner | P0 |
| Topic classification | 200+ hardcoded keywords | LLM/web search + disambiguation | P1 |
| Mood→query | Static hardcoded mappings | Mood as weight in preference model | P1 |
| Discovery intent | 30+ exact phrases | Semantic state detection | P1 |
| Casual vocabulary | 100+ word list | Pragmatics register analysis | P2 |
| Proactive behavior | Hardcoded weights | Config + learned preferences | P2 |
