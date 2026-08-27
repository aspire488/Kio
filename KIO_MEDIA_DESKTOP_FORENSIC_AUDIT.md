# KIO MEDIA + DESKTOP FORENSIC AUDIT
## Date: 2026-08-24 | Branch: kio-restoration-safety-20260823

---

## 1. ARCHITECTURE OVERVIEW

### Call Graph: User Message → Execution → Response

```
TELEGRAM UPDATE
  → kio_bot.handle_message()
    → Pipeline.run(text, session_id)
      → _NormalizationService.run()          — normalize text
      → _IntentClassifier.classify()         — determine intent
      → _apply_discourse_context_override()  — conversational continuity
      → _apply_verification_probe_route()    — verification routing
      → _apply_graph_recall_override()       — graph-backed recall
      → _CapabilityResolver.resolve()        — map intent → capability
      → _ExecutionCoordinator.execute()      — run the capability
      → _ResponseComposer.compose()          — format response
    → format_channel_reply()
  → update.message.reply_text()
```

### Pipeline Stages

| Stage | File | Function | Purpose |
|-------|------|----------|---------|
| Normalize | `pipeline/__init__.py` | `_NormalizationService.run()` | Case, punctuation, abbreviations |
| Classify | `pipeline/__init__.py` | `_IntentClassifier.classify()` | IntentType + action + target |
| Override | `pipeline/__init__.py` | `_apply_*()` methods | Context/continuity corrections |
| Resolve | `pipeline/__init__.py` | `_CapabilityResolver.resolve()` | Intent → capability + params |
| Execute | `pipeline/__init__.py` | `_ExecutionCoordinator.execute()` | Run the actual operation |
| Compose | `pipeline/__init__.py` | `_ResponseComposer.compose()` | Format user-facing response |

### Intent Types (Key)

| IntentType | Action | Target | Capability |
|-----------|--------|--------|-----------|
| MEDIA_PLAY | play | query text | `media` → `MediaManager.play()` |
| MEDIA_TRANSPORT | pause/resume/stop/next/previous | (empty) | `media` → transport commands |
| DESKTOP | open_app/close_app | app name | `desktop` → `open_app()` / `close_app()` |
| DESKTOP_ACTION | type/press/save/etc | text/combo | `desktop_action` → `execute_capability()` |
| INFORMATION | research/query | search text | `information` → retrieval + LLM |
| CONVERSATION | converse | text | `conversation` → LLM |
| GREETING | greet | (empty) | `greeting` → canned response |
| MEMORY | remember/forget/recall | fact | `memory` → semantic graph |
| ENTITY_QUERY | entity_lookup | entity | `information` → retrieval |

---

## 2. MEDIA INTENT CLASSIFICATION

### Classifier Logic (Pipeline._IntentClassifier)

```
MEDIA TRANSPORT CHECK (highest priority for active session):
  - "pause" / "hold on" / "wait" → MEDIA_TRANSPORT.pause
  - "resume" / "continue" / "unpause" → MEDIA_TRANSPORT.resume
  - "stop" / "turn off" → MEDIA_TRANSPORT.stop
  - "next" / "skip" → MEDIA_TRANSPORT.next
  - "previous" / "back" → MEDIA_TRANSPORT.previous
  - "shuffle" → MEDIA_TRANSPORT.shuffle
  - "repeat" / "loop" → MEDIA_TRANSPORT.repeat
  - volume patterns → MEDIA_TRANSPORT.set_volume
  - seek patterns → MEDIA_TRANSPORT.seek

MEDIA PLAY CHECK:
  - "play something similar/another/more" → MEDIA_PLAY (context)
  - "nah/actually...play X instead" → MEDIA_PLAY (switch)
  - "play X" / "watch X" → MEDIA_PLAY
    - "play X in Chrome" → MEDIA_PLAY + platform=chrome
    - "play X on YouTube" → MEDIA_PLAY + platform=youtube
  - bare "play" → MEDIA_PLAY (resume active)
  - "show me the trailer/highlights" → MEDIA_PLAY

PLATFORM EXTRACTION:
  "play X in Chrome" → target=X, platform=chrome
  "play X on YouTube" → target=X, platform=youtube
  "play X in Edge" → target=X, platform=edge
  Browser names: chrome, edge, firefox, brave, comet, browser
  Platform names: youtube, youtube desktop, desktop
```

### Media Manager Play Path

```
MediaManager.play(query, platform)
  → Step -2: Pronoun resolution ("it"/"that"/"this" → last entity)
  → Step -2.5: Bare artifact resolution ("trailer" → "Entity trailer")
  → Step -1: Intelligence/Continuity resolution
    → ContinuityEngine.is_followup()
    → MediaIntelligenceAdapter.handle()
  → Step 0: Resume active session (if no query)
  → Step 1: Content-type detection (score_content_intent)
  → Step 2: Platform-specific path
  → Step 3: Provider selection chain
    → YouTubeProvider.play(query, media_type=mt)
```

---

## 3. YOUTUBE RANKING PIPELINE

### Candidate Discovery

```
YouTubeProvider.play(query)
  → API: _api_search_candidates(query)
    → YouTube Data API v3: part=snippet, type=video, maxResults=15
    → Returns: [{title, url, video_id, channel, description}]
    → Failure: silent degrade to browser scrape
  → Browser: conn.execute_script("search_results")
    → MV3-safe DOM scrape
    → Returns: [{title, url, video_id}] (NO channel info)
    → Max 8 results
  → Merged pool: deduplicate by video_id
```

### Candidate Scoring (_score_candidate)

```
Inputs: title, url, query, channel, description, media_type

1. PHRASE MATCH:
   - Full contiguous phrase in title: +30
   - Separator-tolerant phrase: +15

2. TERM COVERAGE:
   - Individual term in title: +3 (short) or +8 (≥5 chars)
   - Coverage gate: < 50% terms → -25
   - 0 terms matched → -100 (hard reject)

3. CHANNEL IDENTITY:
   - Term in channel name: +10

4. ARTIFACT KEYWORD MATCH:
   - "trailer"/"interview"/etc. in title when requested: +6
   - "official" in title: +6 (+12 extra for artifact match)

5. PHRASE POSITION:
   - Leading (≤20% of title): +10
   - Buried (≥60%): -10

6. LIVE BOOTLEG PENALTY:
   - "live" in title when not requested: -10

7. FRAMING PENALTY:
   - breakdown/reaction/explained/review in title when not requested: -12 each (max -24)

8. AGGREGATION PENALTY:
   - 3+ dash chains: -14
   - 2 dash chains: -4

9. CHANNEL AUTHORITY:
   - VEVO: +10
   - Authority markers: +4 each (max +14)

10. DESCRIPTION CORROBORATION:
    - ≥50% terms in description: +6

11. CONTENT-TYPE VALIDATION:
    - Audio-only candidate when visual requested: -14
    - Type keyword match: +18
    - Type mismatch: -22

12. SHORTS PENALTY:
    - /shorts/ in URL when not requested: -28
    - #shorts in title: -18

13. FAN EDIT/REACTION/COMPILATION:
    - Markers in title when not requested: -12

14. EXACT TITLE MATCH:
    - Title == query: +20
```

### Selection

```
best = max(candidates, key=(score, -title_length))
if best.score > 0: navigate to best.url
else: youtube_bootstrap (click first result)
```

---

## 4. PLAYBACK VERIFICATION

### Identity Gate (RC8)

```
After navigation:
  → get_page_info → actual URL
  → _video_id_from_url(actual_url) → loaded_id
  → Compare: loaded_id == selected_video_id
  → Mismatch → identity_fail → FAIL
```

### Playback State

```
execute_script("play") → dict:
  - playerState (YouTube Iframe API)
  - paused (video element)
  - status ("playing"/"paused"/"blocked"/"no media")
  - player_status_from_script ("playing"/"paused"/"ad_playing")

Decision:
  playerState == 1 AND not paused → PLAYING (authoritative)
  player_status == "playing" AND not paused → PLAYING
  status == "playing" AND not paused → PLAYING
  status == "ad_playing" → AD_WAIT (bounded retry)
```

### Ad Detection (Extension build 0.3.5)

```
DOM selectors:
  - ytd-ad-slot-renderer, .ytp-ad-player-overlay
  - .ytp-ad-badge-item, .ytp-ad-duration-remaining
  - .ytp-ad-skip-button, .ytp-ad-skip-button-modern
  - Page title ad markers

If detected → status = "ad_playing"
Python handler:
  → wait 3s, retry max 2 cycles
  → re-verify target video after ad
  → if still ad: degraded (READY), NOT PLAYING
```

---

## 5. INSTALLED APP DISCOVERY

### Discovery Chain

```
_find_installed_app(name):
  1. _app_paths_discovery() — Windows App Paths registry
  2. _start_menu_discovery() — Start Menu .lnk files
  3. shutil.which() — PATH lookup
  4. _windows_apps_alias() — WindowsApps execution aliases
  5. _uwp_app_discovery() — UWP AUMID source
```

### APP_REGISTRY (Hardcoded)

Browsers: chrome, edge, firefox, brave, comet
Apps: vscode, notepad, calculator, explorer, terminal, paint, vlc, spotify, discord, telegram, word, excel, powerpoint, snipping tool, microsoft store, settings, photos

### Browser Routing

```
get_browser_routing(target, browser_name):
  1. Registered native app → native route
  2. Generic installed-app discovery → native route
  3. Explicit web target (URL/dotted domain) → browser_fallback
  4. Not found → truthful "couldn't find X installed"
```

---

## 6. DESKTOP EXECUTION

### Word/Excel/PPT Creation

```
Pipeline._exec_create_document()
  → artifact_operator._build_docx() / _build_xlsx() / _build_pptx()
  → Uses: python-docx, openpyxl, python-pptx
  → Verification: verify_docx() / verify_xlsx() / verify_pptx()
  → File saved to Desktop or specified path
```

### Notepad/Desktop Automation

```
Pipeline._exec_desktop_action()
  → execute_capability(action, target)
  → Uses: subprocess.Popen with _creation_flags() = DETACHED_PROCESS
  → Verification: _verify_process_started_windows()
```

---

## 7. PROCESS LIFECYCLE

### Bot Launch

```
kio_bot.py:
  → Application(Builder().token().build())
  → app.run_polling()
  → Concurrent update handling (concurrent_updates=4)
```

### Terminal Window Bug

```
app_operator.py line 3016:
  subprocess.Popen(["cmd", "/c", "start", "", name],
                    shell=False, creationflags=_creation_flags())

_creation_flags() = 0x00000008  # DETACHED_PROCESS

ISSUE: "cmd /c start" always opens a visible console window.
FIX: Use CREATE_NO_WINDOW (0x08000008) or avoid cmd /c start entirely.
```

---

## 8. ROOT CAUSES FOUND

### P0 — Correctness / False-Success

| # | Issue | File:Line | Root Cause |
|---|-------|-----------|-----------|
| P0-1 | "Play something random" searches literal "random" | `pipeline/__init__.py:4729` | No discovery intent detection; "something random" passed as literal YouTube query |
| P0-2 | Terminal window appears during bot operation | `app_operator.py:3016` | `cmd /c start` always opens visible console; `_creation_flags()` uses DETACHED_PROCESS instead of CREATE_NO_WINDOW |
| P0-3 | Memory recall-after-forget returns unrelated favorites | `pipeline/__init__.py:8449` | `favorite` keyword in query triggers fallthrough to generic favorites display after scoped recall fails |

### P1 — Major Capability Failure

| # | Issue | File:Line | Root Cause |
|---|-------|-----------|-----------|
| P1-1 | Browser scrape lacks channel info | `background.js:842` | `search_results` script only extracts title/url/video_id, not channel |
| P1-2 | Previous track often fails | `youtube_provider.py:1130` | YouTube has no native "previous"; no session play history maintained |
| P1-3 | "Open X in Chrome" always uses Chrome | `pipeline/__init__.py:4720` | Platform extraction only checks 6 hardcoded browser names |

### P2 — Reliability / Latency

| # | Issue | File:Line | Root Cause |
|---|-------|-----------|-----------|
| P2-1 | Play latency 17-36s | `youtube_provider.py` | Sequential API + scrape + navigation + verification |
| P2-2 | Fan edit reply timeout (>40s) | `youtube_provider.py` | Complex queries with intelligence resolution add overhead |
| P2-3 | Stale response filtering causes false negatives in tests | `kio_bot.py:95-138` | Sequence tracking discards valid responses during concurrent operations |

### P3 — Architecture

| # | Issue | File:Line | Root Cause |
|---|-------|-----------|-----------|
| P3-1 | 8700-line Pipeline monolith | `pipeline/__init__.py` | Single file contains all classification, routing, execution, composition |
| P3-2 | 6 overlapping context systems | various | SessionState, ContextManager, MediaContext, ContinuityResolver, etc. |
| P3-3 | APP_REGISTRY has ~25 hardcoded entries | `app_operator.py:196` | Generic discovery exists but registry supplements it |

---

## 9. VERIFICATION EVIDENCE

### YouTube API Actually Used

```
[2026-08-24 19:00:07,092] [YT_API_SEARCH] query=something random results=15
[2026-08-24 19:00:07,100] [YT_CANDIDATE] query=something random selected=What is Random? score=14
```

### Identity Gate Working

```
[2026-08-24 19:18:24,659] [YT_INSTRUMENT] post-bootstrap url=https://www.youtube.com/watch?v=_YUzQa_1RCE title=Dune: Part Two | Official Trailer 2
[2026-08-24 19:18:26,057] [ROOT_YT] FINAL_RETURN playback_state=playing success=True
```

### Ad Detection Present

```
extension/background.js build 0.3.5:
  - ytd-ad-slot-renderer, .ytp-ad-player-overlay
  - .ytp-ad-badge-item, .ytp-ad-skip-button
  - Returns status: "ad_playing" when detected
```

### Documentary Fix Working

```
[2026-08-24 19:04:41] "Play a documentary about the James Webb telescope"
→ "Playing A Documentary About The James Webb Telescope."
(Before fix: would have returned "Playing An Interview With Elon Musk.")
```

---

## 10. RECOMMENDATIONS

### Phase B: P0 Fixes (Immediate)

1. **Discovery intent detection** — Detect "something random/anything/surprise" and route to discovery strategy instead of literal YouTube search
2. **Terminal window fix** — Replace `cmd /c start` with direct `subprocess.Popen` using `CREATE_NO_WINDOW`
3. **Memory recall fix** — Guard the `favorite` fallthrough with `_has_specific_topic` check

### Phase C: Media Ranking

4. **Add channel to browser scrape** — Extract channel name from `ytd-video-renderer` metadata
5. **Content-type verification** — After navigation, verify page content matches requested type

### Phase D: Browser/App Discovery

6. **Dynamic browser detection** — Query Windows registry for installed browsers instead of hardcoded list
7. **Browser modality routing** — "Open X in Edge" should target Edge, not always Chrome

### Phase E: Process/Window

8. **Fix all subprocess.Popen calls** — Audit every creationflags usage
9. **Headless bot launch** — Ensure bot runs without visible console

---

## 11. DELIVERABLES STATUS

| # | Document | Status |
|---|----------|--------|
| 1 | KIO_MEDIA_DESKTOP_FORENSIC_AUDIT.md | ✅ THIS FILE |
| 2 | KIO_MEDIA_DESKTOP_REMEDIATION_PLAN.md | ⏳ Pending |
| 3 | KIO_MEDIA_ACCEPTANCE_MATRIX.md | ⏳ Pending |
| 4 | KIO_BROWSER_APP_CAPABILITY_MATRIX.md | ⏳ Pending |
| 5 | KIO_RESEARCH_ARTIFACT_GROUNDING_AUDIT.md | ⏳ Pending |
| 6 | KIO_LATENCY_BASELINE.md | ⏳ Pending |
| 7 | KIO_TERMINAL_PROCESS_AUDIT.md | ⏳ Pending |
| 8 | KIO_FINAL_EXECUTION_REPORT.md | ⏳ Pending |
