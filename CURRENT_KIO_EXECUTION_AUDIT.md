# CURRENT KIO EXECUTION AUDIT

## A. Real Telegram Execution Path

```
Telegram update
  → kio_bot.py::handle_message()           [async, Telegram handler thread]
    → asyncio.to_thread(route, cmd, uid)   [OR run_in_executor for long ops]
      → route()                             [synchronous, blocks thread]
        → dispatch_channel_input()          [runtime entry point]
          → InputNormalizer.strip_emoji()
          → handle_command()
            → Pipeline.run()
              → _normalizer.run()           [normalize text]
              → _classifier.classify()      [IntentType + action + target]
              → _apply_discourse_context_override()
              → _resolver.resolve()         [capability + params]
              → _coordinator.execute()      [dispatch to handler]
                → _exec_media()             [for MEDIA_PLAY / MEDIA_TRANSPORT]
                  → MediaManager.play()     [provider selection + execution]
                    → YouTubeProvider.play() [Chrome extension: search → rank → navigate → verify]
              → _composer.compose()         [response formatting]
              → return result dict
          → format_result()                 [runtime response formatter]
        → format_channel_reply()            [extract message string]
      → return string
    → update.message.reply_text(reply)      [Telegram send]
  → command complete
```

**Critical observation**: The ENTIRE path is synchronous from `route()` to return. The bot handler blocks the thread pool worker until every step completes — including media verification polling (up to ~10 seconds per attempt × 3 attempts). Telegram's `concurrent_updates=4` and `_LONG_OP_POOL` (3 workers) provide some isolation, but a media play operation monopolizes a thread for its full duration.

**No async boundary within `route()`**: The pipeline, provider, and verification all run synchronously within a single thread. There is no yield point between "search started" and "playback verified". This means a single slow media operation blocks that thread for 5-15 seconds.

## B. Media State Machine

**Defined states** (`media_state.py`):
```
IDLE → LOADING → READY → PLAYING ⇄ PAUSED → STOPPED → IDLE
                                        ↓
                                     ERROR → IDLE
```

**Actual state transitions in `YouTubeProvider.play()`**:

1. `conn.open_tab(search_url)` → tab created (state: IDLE → implicit LOADING)
2. `_select_best_candidate(tab_id, query)` → scrape YouTube search results + API → score candidates → best selected
3. `conn.open_tab(candidate_url)` → navigate to watch page
4. Bootstrap retry loop (2 attempts, 1s sleep) → confirm page navigation
5. **RC8 identity gate**: loaded page video ID ≠ selected video ID → FAIL (wrong video)
6. **Play verification loop** (3 attempts, 0.7s sleep each):
   - Execute extension `play` script
   - Check: `playerState == 1` AND `!paused` → **PLAYING**
   - Check: `player_status == "playing"` AND `!paused` → **PLAYING**
   - Check: `status == "ad_playing"` → wait 3s, retry (max 2 ad cycles)
   - Check: `status == "blocked"` → READY (can't force play)
   - Check: `status == "no media"` → retry (timing signal)
   - Check: script error → break
7. Return `MediaResult(success=..., state=PLAYING/READY/IDLE, ...)`

**State machine assessment**: The defined states (IDLE→LOADING→READY→PLAYING) are present but the transitions are implicit — there's no explicit state variable set at each boundary. The session object's `state` field is set once at the end of `play()`, not updated during the verification loop. Intermediate states (LOADING, READY) are never explicitly set during a play operation.

**The response arrives ONLY after verification**: The `play()` method returns a `MediaResult` with `state=PLAYING` only after the verification loop confirms actual playback. The response to Telegram is sent only AFTER `play()` returns. So the "Playing X" response IS post-verification.

## C. Media Ranking

**`_score_candidate()`** implements a multi-signal ranking:

| Signal | Weight | Condition |
|--------|--------|-----------|
| Full contiguous phrase match | +30 | Query appears as substring in title |
| Ordered term match (separator-tolerant) | +15 | Terms in same order with light separators |
| Distinctive term match (≥5 chars) | +8 | Each significant word found in title |
| Short term match (<5 chars) | +3 | Each short word found in title |
| Coverage gate (<50%) | -25 | Less than half query terms matched |
| Channel identity match | +10 | A query term found in channel name |
| Artifact keyword match | +6 | "trailer" in both query and title |
| "Official" in title | +6 | Authoritative upload signal |
| Official + artifact match | +12 | "Official Trailer" when trailer requested |
| Phrase position (leading) | +10 | Query is the subject, not buried |
| Phrase position (buried) | -10 | Query at end of title |
| Live bootleg (not requested) | -10 | "LIVE" in title when not asked for |
| Framing penalty (reaction/review/etc) | -12 each | Up to -24 total |
| Mashup/compilation penalty | -4 to -14 | Dash-chain or multi-IP titles |
| Long title penalty (>90 chars) | -6 | Spammy titles |
| VEVO channel | +10 | Canonical music publisher |
| Authority markers | +4 each (max 14) | studios/records/entertainment/etc |
| Audio-type mismatch | -14 | "- Topic" channel or soundtrack markers |
| Content-type match | +18 | Title explicitly matches requested type |
| Content-type mismatch | -22 | User asked for X, title doesn't contain X |
| Emoji/clickbait penalty | -8 | Unicode emoji in title |
| Shorts URL penalty | -28 | `/shorts/` in URL (normal play only) |
| Shorts title marker | -18 | `#shorts` or "vertical" in title |
| Weak upload penalty | -12 | fan edit, reaction, compilation, etc. |
| Exact title == query | +20 | Strongest match |
| All terms present | +8 | Partial exact match |

**Assessment**: The ranking is sophisticated and handles most media types correctly. The content-type mismatch penalty (-22) is strong enough to prevent "Bethlehem interview" from selecting a trailer. The Shorts penalty (-28) overcomes the phrase match (+30), preventing Shorts from winning normal play requests. The ranking is intent-aware: Shorts are penalized only when `_wants_short` is False.

**Remaining weakness**: The ranking relies on the Chrome extension's `search_results` script scraping the DOM, which returns limited metadata (title, url, channel). The YouTube API provides richer metadata when configured, but the API key availability depends on `.env`. Without the API key, the ranking uses only title/url/channel from the DOM scrape.

## D. Ad Handling

**Chrome extension detection** (`background.js` line 414-462):
- Checks DOM for ad containers: `ytd-ad-slot-renderer`, `.ytp-ad-player-overlay`, `.video-ads`
- Checks ad attribution badge: `.ytp-ad-badge-item`, `.ytp-ad-overlay-close-button`
- Checks page title for " ad " markers
- Checks skip button: `.ytp-ad-skip-button`, `.ytp-skip-ad-button-modern`
- Returns `{status: 'ad_playing', ...}` when any ad signal detected

**YouTube provider handling** (line 830-847):
```python
elif msg.get("status") == "ad_playing":
    if attempt < 2:
        time.sleep(3.0)
        continue
    # Ad persisted through retry budget — report as success with caveat
    playback_state = MediaState.PLAYING
    break
```

**Assessment**: Ad detection exists but has a design flaw:
1. When an ad is detected, the provider waits 3s and retries (up to 2 cycles)
2. If the ad persists after 2 retries (6s total wait), it **accepts the ad as "playing"** and returns success
3. This means a pre-roll ad can cause KIO to report "Playing X" while an ad is actually playing
4. The rationale is "reporting failure here would be worse than reporting playing with ad" — but the user experience is still wrong

**The fix needed**: After the ad-wait cycle, re-check the player state to confirm the TARGET video is now playing (not just that the ad ended). Currently, the code sets `playback_state = MediaState.PLAYING` without verifying the target is actually loaded.

## E. Playback Verification

**Verification chain** in `YouTubeProvider.play()`:
1. **Tab created**: `conn.open_tab()` returns success
2. **Page rendered**: `get_page_info` returns URL + title + hasVideo
3. **Candidate selected**: `_select_best_candidate()` returns best match
4. **Navigation succeeded**: `conn.open_tab(candidate_url)` returns success
5. **Identity gate**: loaded page video ID matches selected candidate ID
6. **Player state**: `playerState == 1` (YouTube Iframe API) AND `!paused`
7. **Script confirmation**: `player_status == "playing"` AND `!paused`
8. **Legacy fallback**: `status == "playing"` AND `!paused`

**Verification gaps**:
- Step 6 uses YouTube's own player state, which is authoritative
- Step 5 (identity gate) prevents playing the wrong video
- BUT: if the identity gate passes (correct video loaded) but the video has a pre-roll ad, the play script may report `ad_playing` → wait → re-check → still ad → accept as playing
- The `paused` field check is important: `paused=True` with `status="playing"` is a self-contradictory payload that is correctly rejected

**Overall**: Playback verification is genuine — it requires actual player state confirmation. The main weakness is the ad-handling path that accepts ads as "playing" after timeout.

## F. Media Serialization

**Implementation**: Module-level `_MEDIA_OP_LOCK = threading.RLock()` with `_serialize_media_op` decorator applied to:
- `play()` (line 769)
- `pause()` (line 1096)
- `resume()` (line 1061)
- `stop()` (line 1096)
- `next_track()` (line 1131)
- `previous_track()` (line 1154)
- `volume_up()` (line 1183)
- `volume_down()` (line 1214)
- `mute()` / `unmute()` (line 1239/1264)
- `seek_forward()` / `seek_backward()` (line 1275/1286)
- All other media operations

**Behavior**: When "Play X" is executing (holding the lock), a subsequent "Pause" will **block on the lock** until play completes. This is correct serialization — commands are processed in order, and a media operation cannot be interrupted mid-execution.

**Assessment**: Serialization is correctly implemented. The `_MEDIA_OP_LOCK` is a reentrant lock (RLock), so nested calls within the same thread don't deadlock. The main concern is latency: if Play takes 10 seconds, Pause waits 10 seconds before executing. This is the correct behavior — you can't pause a video that hasn't started yet.

## G. Latency Measurements

The pipeline includes stage-latency instrumentation (`pipeline_profile` trace event):

| Stage | What it measures |
|-------|-----------------|
| `normalize_ms` | Text normalization (emoji strip, polite prefix, etc.) |
| `classify_ms` | Intent classification (pipeline classifier) |
| `resolve_ms` | Capability resolution (routing decision → capability + params) |
| `exec_ms` | Execution (provider call, browser navigation, verification) |
| `compose_ms` | Response composition (format result, strip leaks) |
| `total_ms` | End-to-end pipeline time |

**Typical latency breakdown** (estimated from code inspection):
- Classification: ~5-20ms
- Resolution: ~5-10ms
- Execution: **5,000-15,000ms** (YouTube search + navigation + verification)
- Composition: ~1-5ms
- Total: **5,020-15,040ms** for media commands

**Non-media latency**: LLM-based operations (conversation, research) add 1,000-8,000ms depending on the provider.

**Bottleneck**: The YouTube provider's verification loop (3 attempts × 0.7s + potential 2 ad cycles × 3s) accounts for the majority of media latency. This is necessary for truthful verification — reducing it would sacrifice correctness.

## H. Web Search Provider Usage

**Provider chain** (`retrieval_router.py`):
```
Wikipedia → Exa → Tavily → DuckDuckGo
```

**Per-topic priority**:
- MOVIES/TV/MUSIC/GAMING/TECH/BOOKS: Wikipedia → Exa → Tavily → DuckDuckGo
- SPORTS: Exa → Tavily → Wikipedia → DuckDuckGo
- STANDINGS/FIXTURES/RESULTS: Exa → Tavily → Wikipedia → DuckDuckGo

**Fallback guarantee**: If all providers fail, DuckDuckGo is always tried last. Wikipedia is the deterministic fallback for encyclopedic topics.

**Assessment**: The provider routing is functional. Each provider is configured via `.env` and called through its respective module. The `KnowledgeRouter.route_for_topic()` method iterates through the priority chain until a provider returns results.

**Issue found**: The `_exec_knowledge` method in the pipeline (line 8417) has a HARDCODED knowledge base of 5 entries and returns `"No answer in knowledge base"` for anything not in that base. This is the LEGACY knowledge path — the actual information routing goes through `_classify_context_followup()` → `IntentType.INFORMATION` → `_exec_media()` → `MediaManager.process_information_query()` → `MediaIntelligenceAdapter` → `KnowledgeRouter`. The `_exec_knowledge` path is effectively dead for real information queries.

## I. Word/Excel/PPT Execution

**Word (.docx)**:
- `document_operator.create_document()` → `build_docx()` (OOXML ZIP, no python-docx dependency)
- Content generated by LLM (`_generate_content()` with research grounding)
- Verification: `verify_docx()` checks valid ZIP + word count > 0
- Opens in Word via `_activate_launched_window()` after creation

**Excel (.xlsx)**:
- `artifact_operator.create_artifact()` → `build_xlsx()` (openpyxl)
- Content parsed from LLM-generated tab-separated rows
- Validation: `validate_content_for_artifact()` checks for tabular format
- Fallback: `deterministic_spreadsheet_content()` generates minimal but real data
- Verification: `verify_xlsx()` checks valid ZIP + cell count > 0

**PowerPoint (.pptx)**:
- `presentation.engine.create_presentation()` (dedicated presentation design engine)
- Plans slides → researches → designs layout → builds OOXML → validates → opens
- Fallback: `build_pptx()` with LLM-generated SLIDE markers
- Enhancement: `enhance_pptx_transitions()` adds transitions via COM
- Verification: `verify_pptx()` checks valid ZIP + slide count > 0

**Assessment**: All three artifact types use real OOXML construction with verification. The content quality depends on the LLM's output, which is research-grounded via `KnowledgeRouter`. The timeout issue in Word creation is likely from the LLM content generation step, not the file construction.

## J. Response Composer

**`_ResponseComposer`** (line 8486):
- Strips implementation jargon (`_LEAK_PATTERNS`, `_LEAK_WORDS`)
- Strips trailing markdown table rows
- Preserves sentence-final punctuation
- Identity answers bypass leak stripping (authored canon text)
- Updates conversation context after composition

**`runtime_response_formatter.format_result()`**:
- Detects natural messages → passes through
- Detects provider UI artifacts → sanitizes
- Detects structured failures → formats error
- Dispatches to specific formatters (open_app, close_app, search_web, etc.)

**Assessment**: Response quality is mixed:
- Desktop operations: Good ("Opened Calculator.", "Closed Notepad.")
- Media operations: Often terse ("playing" instead of "Playing X on YouTube")
- Memory operations: Improved but still shows raw keys in edge cases
- Artifacts: Good ("Created filename.xlsx — 17 rows, 85 cells.")
- Information: Good (passes through the LLM's natural response)

## K. Current Failures

### Root Cause 1: "playing" Response for Media
**Location**: `YouTubeProvider.play()` → `MediaResult.message` field
**Issue**: The provider sets `message` to a brief status string, and the response composer passes it through without enrichment. The `_ResponseComposer` treats it as "natural" and doesn't add context.
**Fix**: The response composer should enrich media results with the query and platform context.

### Root Cause 2: Ad-Acceptance as Playback Success
**Location**: `YouTubeProvider.play()` line 840-847
**Issue**: After 2 ad-wait cycles, `playback_state = MediaState.PLAYING` is set without re-verifying the target video is actually playing.
**Fix**: After ad-wait, re-check `get_player_state` to confirm the target (not ad) is playing.

### Root Cause 3: Memory Key Leakage
**Location**: `_exec_memory()` line 8390-8410
**Issue**: When no scoped recall matches, the fallback dumps raw keys: `my_favorite_subject: robotics`.
**Fix**: The fallback path should convert keys to natural language like the scoped path does.

### Root Cause 4: Word Creation Timeout
**Location**: `_generate_content()` → LLM call
**Issue**: The LLM content generation step can take 10+ seconds for complex documents, causing the Telegram handler to appear unresponsive.
**Fix**: This is an inherent latency of LLM-based content generation. The `_LONG_OP_POOL` (3 workers) already isolates long operations from fast ones.

### Root Cause 5: "What X did I say I like" Memory Recall
**Location**: `_exec_memory()` recall path
**Issue**: The scoped recall regex matches "favorite", "like", "love", "enjoy", "prefer" in the US-normalized query. The query "what engineering field did I say I like" was fixed in a previous session but may still have edge cases with the "did I say" phrasing.
**Fix**: Verified working in current code — the US normalization handles "favourite"→"favorite" and the topic term extraction catches "engineering field".

## L. Exact Files/Functions Responsible

| Issue | File | Function | Line |
|-------|------|----------|------|
| Media response | `youtube_provider.py` | `play()` | ~1000-1050 |
| Ad acceptance | `youtube_provider.py` | `play()` | 840-847 |
| Memory leakage | `pipeline/__init__.py` | `_exec_memory()` | 8390-8410 |
| Response enrichment | `pipeline/__init__.py` | `_ResponseComposer.compose()` | 8525+ |
| Ranking | `youtube_provider.py` | `_score_candidate()` | 106-377 |
| Serialization | `media_manager.py` | `_serialize_media_op` | 298-302 |
| State machine | `media_state.py` | `MediaState` | 1-35 |
| Information routing | `pipeline/__init__.py` | `_classify_context_followup()` | 4852+ |
| Platform extraction | `pipeline/__init__.py` | `_classify_media_transport()` | 4712-4734 |
| Artifact creation | `artifact_operator.py` | `create_artifact()` | 1689+ |
| Presentation engine | `presentation/engine.py` | `create_presentation()` | separate module |

## M. Minimal Surgical Fix Plan

### Fix 1: Enrich media response (5 min)
In `_ResponseComposer.compose()`, when the action is a media play and the result message is terse (≤10 words, no query mentioned), append context: "Playing [query] on [platform]."

### Fix 2: Re-verify after ad-wait (10 min)
In `YouTubeProvider.play()`, after the ad-wait `continue` loop, add a final `get_player_state` check before accepting as PLAYING.

### Fix 3: Memory key formatting (10 min)
In `_exec_memory()`, the fallback dump path (line 8405-8410) should use the same `_label = key.replace("_", " ").strip()` logic as the scoped path.

### Fix 4: Information routing guard (already working)
Verified: "Latest news about AI" → `_classify_context_followup()` → `IntentType.INFORMATION` → correct routing. No YouTube leak.

### Fix 5: Platform extraction (already working)
Verified: "Play X in Chrome" → `_classify_media_transport()` extracts platform="browser" → correct routing.
