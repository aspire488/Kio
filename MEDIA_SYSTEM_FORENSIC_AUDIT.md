# MEDIA SYSTEM FORENSIC AUDIT
## Date: 2026-08-24

---

## 1. MACHINE INVENTORY (Verified)

### Browsers Installed
| Browser | Path | Status |
|---------|------|--------|
| Google Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` | ✅ Installed |
| Microsoft Edge | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` | ✅ Installed |
| Comet | `C:\Users\joelj\AppData\Local\Perplexity\Comet\Application\comet.exe` | ✅ Installed |
| Firefox | — | ❌ Not installed |
| Brave | — | ❌ Not installed |
| Opera | — | ❌ Not installed |
| Vivaldi | — | ❌ Not installed |
| Arc | — | ❌ Not installed |

### YouTube Desktop/PWA
| Target | Path | Status |
|--------|------|--------|
| YouTube PWA | Chrome App ID: `agimnkijcaahngcdmfeangaknmldooml` | ✅ Installed via Chrome |
| YouTube Desktop App | — | ❌ No native desktop app |

### Desktop Applications
| App | Path | Status |
|-----|------|--------|
| Notepad | `WindowsApps\Microsoft.WindowsNotepad` | ✅ UWP |
| Calculator | `WindowsCalculator_8wekyb3d8bbwe!App` | ✅ UWP |
| Word | `Microsoft Office\Root\Office16\WINWORD.EXE` | ✅ Installed |
| Excel | `Microsoft Office\Root\Office16\EXCEL.EXE` | ✅ Installed |
| PowerPoint | Start Menu shortcut | ✅ Installed |
| Spotify | `WindowsApps\SpotifyAB.SpotifyMusic` | ✅ UWP |
| VS Code | `AppData\Local\Programs\Microsoft VS Code\Code.exe` | ✅ Installed |
| VLC | — | ❌ Not installed |
| Discord | — | ❌ Not installed |
| Telegram Desktop | — | ❌ Not installed |

---

## 2. DEFECT TABLE

### P0 — Correctness / False-Success

| # | Issue | Root Cause | File:Line | Severity | Affects |
|---|-------|-----------|-----------|----------|---------|
| P0-1 | "Play something" sends literal "something" to YouTube | No discovery intent detection in classifier | `pipeline/__init__.py:4735` | HIGH | Arbitrary requests |
| P0-2 | Terminal window appears during bot operation | `cmd /c start` + DETACHED_PROCESS | `app_operator.py:3016` | MEDIUM | All desktop ops |
| P0-3 | Documentary hijacked by previous entity | `is_followup()` too aggressive | `continuity_engine.py:131` | HIGH | Follow-up requests |
| P0-4 | Memory recall-after-forget returns unrelated | `favorite` keyword fallthrough | `pipeline/__init__.py:8449` | MEDIUM | Memory queries |

### P1 — Major Capability

| # | Issue | Root Cause | File:Line | Severity | Affects |
|---|-------|-----------|-----------|----------|---------|
| P1-1 | "Open X in Edge" always uses Chrome | Platform extraction only checks 6 names | `pipeline/__init__.py:4722` | HIGH | Browser targeting |
| P1-2 | YouTube always opens in browser, never PWA | No YouTube PWA detection | `youtube_provider.py` | MEDIUM | YouTube requests |
| P1-3 | Browser scrape lacks channel info | Extension script only extracts title/url/id | `background.js:842` | MEDIUM | Ranking quality |
| P1-4 | Previous track often fails | YouTube has no native "previous" | `youtube_provider.py:1130` | LOW | Transport |
| P1-5 | "put on X" / "show me X" not recognized as media | Only "play" and "watch" prefixes handled | `pipeline/__init__.py:4730` | HIGH | Natural language |

### P2 — Reliability / Latency

| # | Issue | Root Cause | File:Line | Severity | Affects |
|---|-------|-----------|-----------|----------|---------|
| P2-1 | Play latency 17-61s | Sequential API + scrape + nav + verify | `youtube_provider.py` | MEDIUM | All media |
| P2-2 | Discovery intent slow (49-61s) | Intelligence resolution adds overhead | `media_manager.py:800` | MEDIUM | Discovery |
| P2-3 | Stale response filtering discards valid replies | Sequence tracking too aggressive | `kio_bot.py:95` | LOW | Rapid commands |

### P3 — Architecture

| # | Issue | Root Cause | File:Line | Severity | Affects |
|---|-------|-----------|-----------|----------|---------|
| P3-1 | 8700-line Pipeline monolith | Single file, all logic | `pipeline/__init__.py` | LOW | Maintainability |
| P3-2 | 6 overlapping context systems | Multiple competing stores | various | LOW | State management |

---

## 3. SYSTEM ARCHITECTURE

### Media Request Flow (Current)

```
USER: "Play Interstellar trailer"
  → Pipeline._IntentClassifier.classify()
    → _classify_media_transport()
      → lower.startswith("play ") → target = "interstellar trailer"
      → platform extraction: "in Chrome" → platform=chrome
      → MEDIA_PLAY action=play, target="interstellar trailer"
  → _CapabilityResolver.resolve()
    → MEDIA_PLAY → ("media", {"action": "play", "target": "interstellar trailer"})
  → _ExecutionCoordinator._exec_media()
    → MediaManager.play("interstellar trailer")
      → Step -1: Intelligence resolution
      → Step 1: _detect_media_type() → "trailer"
      → Step 3: Provider chain: ["youtube"]
      → YouTubeProvider.play("interstellar trailer", media_type="trailer")
        → API search: 15 candidates
        → Browser scrape: up to 8 candidates
        → _score_candidate() for each
        → Select best (score > 0)
        → Navigate to best URL
        → Identity gate: verify video ID
        → Play loop: 3 attempts
        → Ad detection
        → Playback verification
        → Response: "Playing Interstellar Trailer."
```

### Media Intent Detection (Current)

```
Classifier priority:
1. MEDIA_TRANSPORT: pause/stop/resume/next/previous/volume/seek
2. MEDIA_PLAY: "play X" / "watch X" / "show me X" (with media noun)
3. Context play: "play something similar" / "another one"
4. Switch: "nah play X instead"
5. Platform: "play X in Chrome" / "watch X on Edge"
6. Discovery: "play something random" (newly added)
```

### Platform Extraction (Current)

```python
# Only these 6 browser names are recognized:
_browser_names = ("chrome", "edge", "firefox", "brave", "comet", "browser")
# Only these platform names:
_platform_names = ("youtube", "youtube desktop", "desktop", "youtube music", "ytmusic")
```

---

## 4. ROOT CAUSE ANALYSIS

### P0-1: Discovery Intent

**Current behavior:** "Play something random" → target="something random" → YouTube search for literal "random"

**Root cause:** The classifier doesn't detect discovery-modifier words. My previous fix added `_DISCOVERY_TARGETS` but the detection is incomplete — it only catches exact matches and "play " prefix, not natural variants like "put something on", "surprise me", etc.

**Fix strategy:** Expand the discovery detection to cover all natural-language discovery variants. Use the intelligence recommender for context-aware discovery.

### P1-1: Browser Targeting

**Current behavior:** "Open ChatGPT in Edge" → platform extraction checks only 6 hardcoded names

**Root cause:** The platform extraction regex is too restrictive. It should dynamically check installed browsers.

**Fix strategy:** Use the discovered browser inventory from `_find_installed_app()` to dynamically resolve browser names.

### P1-5: Natural Language Media

**Current behavior:** "Put on Interstellar" → falls through to conversation (not media)

**Root cause:** Only "play" and "watch" are recognized as media-action prefixes.

**Fix strategy:** Add "put on", "put X on", "show me", "let me watch", "start playing", etc. as media-action prefixes.

### P1-2: YouTube PWA

**Current behavior:** YouTube always opens via browser connector

**Root cause:** No YouTube PWA detection in the media provider selection.

**Fix strategy:** Detect Chrome PWA for YouTube and offer it as the default when available.

---

## 5. IMPLEMENTATION PLAN

### Phase B: Media Intent Classification (P0-1, P1-5)

1. **Expand discovery detection** — Add natural-language variants: "put something on", "surprise me", "I'm bored", "find something good", etc.
2. **Expand media-action prefixes** — Add "put on", "show me", "let me watch", "start playing", etc.
3. **Keep discovery context-aware** — Use intelligence recommender when available, fallback to trending.

### Phase C: Browser Intelligence (P1-1, P1-2)

1. **Dynamic browser resolution** — Use `_find_installed_app()` to resolve browser names at classification time.
2. **YouTube PWA detection** — Detect Chrome PWA for YouTube, use as default when available.
3. **Platform extraction expansion** — Support all installed browser names, not just 6 hardcoded ones.

### Phase D: Verification (already working)

1. Ad detection — Extension build 0.3.5 working
2. Identity gate — RC8 working
3. Playback verification — Multi-signal working

---

## 6. VERIFICATION EVIDENCE

### YouTube API Actually Used
```
[YT_API_SEARCH] query=something random results=15
[YT_CANDIDATE] query=something random selected=What is Random? score=14
```

### Identity Gate Working
```
[YT_INSTRUMENT] post-bootstrap url=https://www.youtube.com/watch?v=_YUzQa_1RCE title=Dune: Part Two | Official Trailer 2
[ROOT_YT] FINAL_RETURN playback_state=playing success=True
```

### Documentary Fix Working
```
"Play a documentary about the James Webb telescope" → "Playing A Documentary About The James Webb Telescope."
(Before fix: would have returned "Playing An Interview With Elon Musk.")
```

### Terminal Window Fix Working
```
"Open Notepad" → "Opened notepad" (no visible console window)
```

### Discovery Fix Working
```
[CONTEXT_UPDATE] domain=None entity=something random action=play_discovery success=True
[ROOT_YT] FINAL_RETURN playback_state=playing success=True message=Playing Trending Music 2024.
```
