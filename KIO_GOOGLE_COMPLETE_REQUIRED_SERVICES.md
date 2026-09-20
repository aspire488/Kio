# KIO — Complete Google Ecosystem Required Services Report

**Generated:** 2026-09-20
**Auditor:** OpenCode (automated)
**Scope:** All 63 YAML templates + KIO capability registry + codebase architecture
**Status:** COMPLETE

---

## 1. Required Service Matrix

Audit: grep all 63 YAMLs, trace `step_runner._ACTION_MAP` -> `app_operator.py` handlers -> providers.

| Google Service | Required? | Evidence | KIO Implementation |
|---|---|---|---|
| **YouTube Data API v3** | YES | `youtube_provider.py:564-628` calls `googleapis.com/youtube/v3/search` | Raw HTTP + `YOUTUBE_API_KEY` |
| **Gmail API v1** | YES | `inbox_monitor.yaml` -> `email/read_inbox` -> email handler -> Gmail OAuth | **NEW:** Email capability handler |
| Google Calendar API | NO | `calendar_ops.py` uses local ICS file | Local ICS |
| Google Drive API | NO | `file_operator.py` uses local filesystem | Local FS |
| Google Sheets API | NO | `artifact_operator.py` uses `openpyxl` | Local openpyxl |
| Google Docs API | NO | `artifact_operator.py` uses `python-docx` | Local python-docx |
| Google Slides API | NO | `artifact_operator.py` uses `python-pptx` | Local python-pptx |
| Google Tasks API | NO | `local_store.py` uses SQLite | Local SQLite |
| Google People/Contacts | NO | Zero codebase references | Not needed |
| Google Places | NO | Zero codebase references | Not needed |
| Google Photos | NO | Zero codebase references | Not needed |
| Google Meet | NO | Zero codebase references | Not needed |
| Google Chat | NO | Zero codebase references | Not needed |

**KIO requires exactly 2 Google services:** YouTube Data API v3 (API key) and Gmail API v1 (OAuth).

---

## 2. Single Auth Architecture

### Credential Record

```
Provider:    google
Type:        oauth2
Credential:  ae3f1cad-183b-41a5-9354-fd03c5db6e05 (1 active)
Client ID:   457219650980-j37psak8itobpbrbflo3nusqjl9pah81.apps.googleusercontent.com
Client Type: Desktop
Scopes:      calendar, drive, youtube, gmail.modify (4 scopes, single token)
```

### No Duplicates

```
Total Google OAuth credentials: 1
Old (bf82b429-...): REVOKED
Current (ae3f1cad-...): ACTIVE
No per-service credentials. No secondary OAuth clients.
```

### Service Builders (all share 1 credential)

```
get_calendar_service()  -> calendar v3  (dead code, local ICS used)
get_drive_service()     -> drive v3     (dead code, local FS used)
get_youtube_service()   -> youtube v3   (dead code, raw HTTP+key used)
get_gmail_service()     -> gmail v1     <- ACTIVE, wired to email handler
```

---

## 3. Scope Registry

```python
GOOGLE_SCOPES = {
    "calendar":    "https://www.googleapis.com/auth/calendar",
    "drive":       "https://www.googleapis.com/auth/drive",
    "youtube":     "https://www.googleapis.com/auth/youtube",
    "gmail":       "https://www.googleapis.com/auth/gmail.modify",
    "gmail_read":  "https://www.googleapis.com/auth/gmail.readonly",
    "gmail_send":  "https://www.googleapis.com/auth/gmail.send",
}
ACTIVE_SCOPES = [calendar, drive, youtube, gmail.modify]
```

---

## 4. Live Evidence

### Gmail API v1 (NEW)

```
Step 1: get_gmail_service() builds service OK
Step 2: messages().list(userId="me", maxResults=3) -> messages returned
Step 3: messages().get(userId="me", id=..., format="metadata") -> subject/from/date
Step 4: messages().send(userId="me", body={raw: ...}) -> message_id returned
Step 5: labels().list(userId="me") -> found existing labels
Step 6: labels().create(userId="me", body={name: "KIO-TEST"}) -> label_id
Step 7: messages().modify(userId="me", id=..., addLabelIds=[label_id]) -> applied
```

### YouTube Data API v3 (pre-existing)

```
GET youtube/v3/search?q=test&part=snippet&type=video&key={KEY} -> items returned
Fallback: DuckDuckGo if API key unavailable.
```

---

## 5. Explicitly NOT Integrated (by design)

| Service | Why Not |
|---|---|
| Google Calendar | Local ICS sufficient for all 63 workflows |
| Google Drive | Local filesystem sufficient |
| Google Sheets | Local openpyxl generates xlsx |
| Google Docs | Local python-docx generates docx |
| Google Slides | Local python-pptx generates pptx |
| Google Tasks | Local SQLite sufficient |
| Google People/Contacts | No workflow needs it; local CRM in SQLite |
| Google Places | Weather via Open-Meteo |
| Google Photos | Not referenced |
| Google Meet | Not referenced |
| Google Chat | Communication via Telegram |

---

## 6. Changes Made This Session

### 6.1 Email Capability Handler (NEW)

**File:** `mini_kio/core/app_operator.py`

Added `if app_name == "email":` block with 4 actions:
- `read_inbox` — Gmail API list + get metadata
- `send_email` — Gmail API MIME send
- `apply_label` — create label if needed, apply to message
- `watch_inbox` — returns polling mode info (push requires Pub/Sub)

Added `"email"` to `APP_CAPABILITIES`.

### 6.2 inbox_monitor.yaml Fix

**File:** `automation/library/monitoring/inbox_monitor.yaml`

Changed:
- `capability: communication` -> `capability: email`
- `action: get_updates` (Telegram) -> `action: read_inbox` (Gmail)
- `providers_required: [imap, llm]` -> `providers_required: [gmail, llm]`
- `capabilities_required` now includes `email`

### 6.3 vector_search Handler (NEW)

**File:** `mini_kio/core/providers/knowledge_provider.py`

Added `_vector_search()` method:
- Uses existing `sentence-transformers` embeddings via `companion/semantic.py`
- Cosine similarity over provided documents
- Returns ranked results with scores
- Added to handlers dict, capabilities list, and test stub

---

## 7. Remaining Gaps (NOT Google-related)

### 7.1 media.content_repurpose -> publish/verify_posts

**Status:** BLOCKED — no social media adapters exist.

The YAML expects LinkedIn, X (Twitter), Instagram publishing. KIO's media providers
(YouTube, Spotify) are media-control only (play/pause/search). No OAuth credentials
for social platforms exist in the credential vault.

**Required to close:**
- LinkedIn API adapter + OAuth2 credentials
- X/Twitter API adapter + OAuth2 credentials
- Instagram API adapter + OAuth2 credentials
- Per-platform publish() and verify_posts() methods

This is a social media integration gap, not a Google gap.

### 7.2 ai.rag_answer -> vector_search

**Status:** CLOSED — vector_search handler implemented.

---

## 8. Acceptance Criteria

- [x] All 63 YAMLs audited for Google service references
- [x] KIO capability registry audited for Google API usage
- [x] Required vs not-required determination documented
- [x] Single OAuth credential confirmed (1 active, no duplicates)
- [x] Scope union computed (4 scopes, single token)
- [x] Gmail API live-verified (read, send, label)
- [x] YouTube Data API live-verified (search)
- [x] Calendar/Drive verified as infrastructure-only (not used in production)
- [x] Explicitly NOT Integrated list documented
- [x] No new Google services added beyond what workflows require
- [x] Architecture principle applied: integrate because required, not because available
