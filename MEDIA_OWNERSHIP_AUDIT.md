# MEDIA_OWNERSHIP_AUDIT.md
# Media System Ownership Audit
# ============================

## MEDIA DECISION OWNERSHIP MAP

### Initial Media Intent Classification
| Aspect | Owner | File |
|--------|-------|------|
| Discovery targets ("play something") | _DISCOVERY_TARGETS | pipeline/__init__.py:18-55 |
| Media transport (pause/resume/stop) | _classify_media_transport() | pipeline/__init__.py:~2260 |
| Transport phrases | MEDIA_TRANSPORT | phrases.py (canonical) |
| Media entity detection | _classify_entity_query() | pipeline/__init__.py:~5500 |
| Context intelligence intent | MediaContextIntelligence | media_context_intelligence.py |

### Media Session State
| Aspect | Owner | File |
|--------|-------|------|
| Current media | MediaManager._current | media_manager.py |
| Played IDs | MediaManager._played_ids | media_manager.py |
| Rejected IDs | MediaManager._rejected_ids | media_manager.py |
| Candidate pool | MediaManager._candidates | media_manager.py |
| Offer state | MediaManager._last_offer | media_manager.py |
| Intelligence offer | MediaManager._intelligence_offer | media_manager.py |

### Media Execution
| Aspect | Owner | File |
|--------|-------|------|
| Play initiation | MediaManager.play() | media_manager.py |
| Provider selection | YouTubeProvider / SpotifyProvider | providers/ |
| Browser execution | BrowserRuntime / Connector | runtime/browser_runtime/ |
| Playback verification | MediaManager._verify_playback() | media_manager.py |
| Transport commands | MediaManager.pause/resume/stop | media_manager.py |

### Media Follow-Up
| Aspect | Owner | File |
|--------|-------|------|
| Follow-up state handling | MediaManager.process_followup() | media_manager.py |
| Context intelligence resolution | MediaContextIntelligence | media_context_intelligence.py |
| Recommendation display | _exec_media() recommendation path | pipeline/__init__.py:7180-7240 |
| User choice resolution | MediaContextIntelligence.resolve_choice() | media_context_intelligence.py |

### Media Response
| Aspect | Owner | File |
|--------|-------|------|
| "Playing X" response | MediaManager.play() | media_manager.py |
| Recommendation list | _exec_media() RECOMMENDATION path | pipeline/__init__.py:7220-7240 |
| Now playing info | MediaManager.now_playing() | media_manager.py |
| Offer line | _maybe_proactive_offer() | pipeline/__init__.py:7365-7464 |

---

## MEDIA COMMAND DUPLICATION ANALYSIS

### Transport Commands
```
"pause" → Pipeline _classify_media_transport() → MEDIA_TRANSPORT → _exec_media() → MediaManager.pause()
"pause" → MediaManager._TRANSPORT_PATTERNS (follow-up path) → MediaManager.pause()
```
**Status:** Two paths, but LEGITIMATE SEPARATION
- Path 1: Direct transport command ("pause")
- Path 2: Follow-up state handling (after media recommendation)
- Both ultimately call MediaManager.pause()

### Discovery Commands
```
"play something" → _DISCOVERY_TARGETS match → MEDIA_PLAY play_discovery → _exec_media()
"play something" → MediaContextIntelligence (RECOMMENDATION mode) → search → present options
```
**Status:** ONE path with intelligence enhancement
- MediaContextIntelligence wraps the discovery flow
- Falls through to existing discovery logic when intelligence fails

### Rejection Commands
```
"nah" → _classify_context_followup() → MEDIA_PLAY → _exec_media() → MediaManager.process_followup()
"nah" → MediaManager._TRANSPORT_PATTERNS (follow-up) → process_followup()
```
**Status:** ONE canonical path — _classify_context_followup is the primary owner

---

## MEDIA FOLLOW-UP STATE FLOW

```
User: "Play something"
→ Discovery → plays candidate A
→ MediaManager stores: current=A, candidates=[A,B,C], offered=[A]

User: "nah"
→ _classify_context_followup() → MEDIA_PLAY play
→ MediaContextIntelligence → process_followup("nah")
→ MediaManager rejects A, selects B
→ Plays B

User: "next"
→ _classify_media_transport() → MEDIA_TRANSPORT next
→ MediaManager.next_track()
→ Plays next in queue

User: "go with 1"
→ _classify_context_followup() → MEDIA_PLAY play
→ MediaContextIntelligence.resolve_choice("1") → option 1
→ Plays selected option
```

---

## MEDIA RECOMMENDATION FLOW

```
User: "pick something to watch while I eat"
→ _exec_media() play_discovery
→ MediaContextIntelligence.extract_intent()
→ SelectionMode.RECOMMENDATION
→ Search for candidates
→ Store recommendations
→ Present numbered options
→ User: "2" → resolve_choice("2") → plays option 2
```

---

## DUPLICATE MEDIA OWNERSHIP: NONE

After thorough analysis, the media system has **ONE canonical owner per concern**:
- Classification: Pipeline _IntentClassifier
- Session state: MediaManager
- Context intelligence: MediaContextIntelligence
- Provider selection: YouTubeProvider/SpotifyProvider
- Browser execution: BrowserRuntime
- Follow-up handling: MediaManager.process_followup()

The apparent duplication (initial classification + follow-up state) is a legitimate architectural separation, not a conflict.

---

## REMAINING MEDIA HARDCODING

| Finding | Location | Treatment |
|---------|----------|-----------|
| "good music to listen to" fallback | media_manager.py | SEMANTICIZE (Phase 2) |
| Activity → music query mappings | media_context_intelligence.py | SEMANTICIZE (Phase 2) |
| Media proactive offer embedding | pipeline _maybe_proactive_offer | ARCHITECTURE (Phase 3) |
| Discovery target phrases (~40) | pipeline _DISCOVERY_TARGETS | KEEP (bounded, functional) |

---

## MEDIA ARCHITECTURE VERDICT

The media architecture is **well-structured** with clear ownership boundaries.
The main issues are:
1. Proactive offer appending (embeds media suggestion in information responses)
2. Static activity → music mappings (could be semantic)
3. Large discovery target list (functional but could be semantic)

**Do NOT redesign the media architecture.** It works correctly.
The focus should be on the 3 items above, not a media overhaul.
