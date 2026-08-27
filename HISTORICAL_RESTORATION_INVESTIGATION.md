# KIO HISTORICAL RESTORATION INVESTIGATION — FINAL REPORT

## EXECUTIVE SUMMARY

The investigation reveals that **there is no "ChatGPT export regression"** — the ChatGPT export data is **untracked** (never committed to git) and exists only as files on disk. The actual execution regressions stem from the **Pipeline architecture rewrite** (Convergence Gates C-1 through C-4b, July 25-30, 2026) which replaced the old 1723-line `command_router.py` with a new 8659-line Pipeline class. Several routing patterns were lost or incompletely ported during this rewrite.

---

## KEY FINDINGS

### 1. ChatGPT Export Data — NOT IN GIT

```
data/historical/           → UNTRACKED (never committed)
mini_kio/memory/historical_import.py → UNTRACKED (never committed)
data/historical/import_index.json     → UNTRACKED (never committed)
```

**There is no "ChatGPT export boundary commit"** because the export was never committed to git. The data exists on disk only. There is nothing to "restore" from git — the data is safe as-is.

### 2. Last Known Good Commit — `2ce8d6e` (KIO v2 standalone, Jul 15, 2026)

This was the last commit with the old execution fabric:
- **command_router.py**: 1723 lines (if/elif chain)
- **execution_boundary.py**: 1034 lines (STATIC_ACTION_TABLE with execute_action)
- **No Pipeline architecture**
- **No artifact_operator.py** (document creation was NEW after this)
- **No document_operator.py**
- Media: YouTube provider, MediaManager, basic transport (play/pause/resume/next/prev/stop)

### 3. Architecture Rewrite Timeline

| Date | Commit | Event |
|------|--------|-------|
| Jul 15 | `2ce8d6e` | KIO v2 standalone (OLD execution fabric) |
| Jul 15-17 | `624d37a`-`325e19c` | Batches 2.1-4.2 (architecture restructure) |
| Jul 25-30 | `a2cb080`-`930c12a` | Convergence Gates C-1 through C-4b |
| Aug 8 | `3584d8e`-`b5db667` | Media playback stabilization |
| Aug 12 | `5e227c7`-`23da4ba` | Document creation + natural-language artifacts |

### 4. Regression Analysis — What's Actually Broken

#### 4a. Excel Creation — ROUTING GAP (CONFIRMED)

**Query**: "Create an Excel spreadsheet with 5 students and their marks"
**Expected**: Creates actual .xlsx file
**Actual**: Returns conversational instructions ("Open Excel and set up a table...")
**Root cause**: The Pipeline's document-creation regexes only match:
- "Create X **about** Y **and save as** Z" (save_as pattern)
- "Create a bare spreadsheet" (bare artifact)
- "Open Excel **and make** Y" (open_and_make pattern)

The "Create X **with** [content]" pattern is NOT matched by any regex. The query falls through to conversation.

#### 4b. "Play X in Chrome" — PLATFORM HINT NOT EXTRACTED (CONFIRMED)

**Query**: "Play Lofi Hip Hop Radio in Chrome"
**Expected**: Opens YouTube in Chrome browser
**Actual**: "I couldn't start Lofi Hip Hop Radio In Chrome."
**Root cause**: The Pipeline's MEDIA_PLAY classification does NOT extract "in Chrome" / "in browser" as a platform hint. The entire string becomes the search target. The `RoutingDecision.platform` field is never set for media play intents.

#### 4c. Media Play Without Connector — BROWSER FALLBACK BROKEN (CONFIRMED)

**Query**: "Play Lofi Hip Hop Radio"
**Expected**: Opens YouTube in default browser (when connector unavailable)
**Actual**: "I couldn't start Lofi Hip Hop Radio."
**Root cause**: The YouTube provider's `_browser_fallback()` is only triggered when `BROWSER_CONNECTOR_ENABLED=False`. When the connector is enabled but not connected (port conflict), it returns an error instead of falling back.

#### 4d. Conversation Continuity — FOLLOW-UP CONTEXT LOST (PARTIAL)

**Query**: "Explain recursion" → good response
**Follow-up**: "Now give me a Python example" → returns unrelated Python 3.14 news
**Root cause**: The LLM provider chain is exhausted (Gemini quota, others returning errors). The Groq provider returns empty content. The conversation context is not being preserved correctly through the Pipeline's classify → compose → execute flow.

#### 4e. "Latest news about AI" — WORKS ✓

Returns actual news content about AI. No YouTube media offer pollution.

#### 4f. Word Document Creation — WORKS ✓

"Create a Word document about Python file handling" correctly creates and opens a .docx file.

#### 4g. PowerPoint Creation — WORKS ✓

"Create a PowerPoint about artificial intelligence" creates a 9-slide .pptx and opens it.

#### 4h. Notepad Typing — WORKS ✓

"Open Notepad" + "Write Hello World to Notepad" correctly types text.

#### 4i. LLM — WORKS ✓

"What is 2+2?" returns "4".

---

## WHAT WAS NEVER IN THE OLD CODEBASE

These capabilities did NOT exist in the v2 standalone (`2ce8d6e`) and were added NEW:

1. **Word/Excel/PowerPoint document creation** (artifact_operator.py, document_operator.py — added in `5e227c7`, Aug 12)
2. **Natural-language content completion** (added in `23da4ba`, Aug 12)
3. **Companion model** (added in `44b2597`, Aug 12)
4. **Semantic graph** (added in Batches)
5. **Credential vault** (added in `6f50eac`, Aug 9)
6. **Operational health** (added in `abaad6f`, Aug 9)

These are NOT regressions — they are new features that need bug fixes.

---

## EXACT ROOT CAUSES AND FIXES NEEDED

### Fix 1: Excel/Document "with" Pattern (Document Creation)

**File**: `mini_kio/core/pipeline/__init__.py`
**Location**: `_detect_document_save_as` and nearby regex patterns
**Issue**: No regex matches "Create X **with** [content description]"
**Fix**: Add a new regex pattern `_CREATE_DOC_WITH_CONTENT_RE` that matches:
```
^(?:create|make|draft|generate|produce|build|write|prepare)\s+
(?:a|an|the)?\s*(?:new|fresh|short|brief|quick|detailed|concise|simple|small|clean|
nice|basic|professional|formal|mini|full|proper)?\s*
(artifact noun)\s+
(?:with|containing|including)\s+(.+?)\s*$
```
This routes to `DESKTOP_ACTION` with `action="create_document"` and the content in metadata.

### Fix 2: "Play X in Chrome" Platform Hint Extraction

**File**: `mini_kio/core/pipeline/__init__.py`
**Location**: `_classify_media_transport` or the MEDIA_PLAY classification in `classify`
**Issue**: "in Chrome" / "in browser" is not extracted as a platform hint
**Fix**: Before creating the MEDIA_PLAY RoutingDecision, strip "in chrome"/"in browser"/"on youtube" from the target and set `platform="browser"` or `platform="youtube"` accordingly.

### Fix 3: YouTube Browser Fallback

**File**: `mini_kio/media/media_manager.py`
**Location**: The `play` method's fallback chain (Step 3 → gate3 → final fallback)
**Issue**: When connector is enabled but not connected, YouTube provider returns error instead of browser fallback
**Fix**: The final fallback already tries `_browser_fallback()` but only when `config.BROWSER_CONNECTOR_ENABLED=False`. Need to also trigger it when the connector is enabled but disconnected.

---

## CAPABILITY-BY-CAPABILITY STATUS

| Capability | Old (v2) | Current | Status |
|-----------|----------|---------|--------|
| LLM responses | ✓ | ✓ | WORKING |
| Conversation continuity | ✓ | Partial | FOLLOW-UP CONTEXT ISSUE |
| Memory store/recall/forget | N/A | ✓ | NEW, WORKING |
| Word creation | N/A | ✓ | WORKING |
| Excel creation | N/A | ✗ | ROUTING GAP |
| PowerPoint creation | N/A | ✓ | WORKING (9 slides) |
| Notepad typing | ✓ | ✓ | WORKING |
| Desktop open/close | ✓ | ✓ | WORKING |
| Chrome/browser | ✓ | ✓ | WORKING |
| YouTube/media | ✓ | Partial | CONNECTOR-DEPENDENT |
| Media pause/resume | ✓ | ✓ | WORKING (with connector) |
| Media next/prev | ✓ | ✓ | WORKING (with connector) |
| Telegram runtime | ✓ | ✓ | WORKING |
| Multi-step commands | ✓ | ✓ | WORKING |
| "Play X in Chrome" | ✓ | ✗ | PLATFORM HINT MISSING |
| Content-type ranking | N/A | ✓ | WORKING (Bethlehem fix applied) |
| Spotify disabled | N/A | ✓ | WORKING (this session) |

---

## CHATGPT EXPORT PRESERVATION

- ✅ `data/historical/` exists on disk (untracked, never in git)
- ✅ ChatGPT export files intact
- ✅ `import_index.json` intact
- ✅ `historical_import.py` intact (untracked)
- ✅ No git operations affected these files
- ✅ All current work is additive, never destructive to export data

---

## FILES CHANGED IN THIS SESSION

1. `mini_kio/core/media_contract.py` — Removed Spotify from CONTENT_TYPE_PRIORITY; added YouTube to RADIO chain
2. `mini_kio/media/media_manager.py` — Disabled Spotify provider; added ACTIVE_PROVIDERS guard; added observability logging

---

## REMAINING FAILURES

1. **Excel "with" pattern** — Needs new regex in Pipeline
2. **"Play X in Chrome"** — Needs platform hint extraction
3. **Conversation follow-up context** — LLM provider chain issues (Gemini quota, others failing)
4. **Media connector dependency** — Browser fallback needs improvement when connector is enabled but disconnected

---

## SAFETY BRANCH

Created: `kio-restoration-safety-20260823`
Base: Current HEAD (`23da4ba`)

---

## RECOMMENDATION

**Do NOT do a historical restoration.** The current architecture is structurally sound. The regressions are specific routing gaps in the Pipeline classifier, not wholesale architecture failures. The fixes are surgical:

1. Add 1 regex pattern for "Create X with Y" document creation
2. Add platform hint extraction for "Play X in Chrome"
3. Improve YouTube browser fallback for disconnected connector

These are 3 targeted fixes, not a full restoration.
