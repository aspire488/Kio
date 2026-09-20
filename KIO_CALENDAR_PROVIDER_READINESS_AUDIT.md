# KIO Calendar Provider Readiness Audit

**Date:** 2026-09-15  
**Scope:** Read-only audit of calendar capability infrastructure  
**Status:** 🔴 **NOT READY — No calendar provider exists**

---

## 1. YAML Templates Using `capability: calendar`

| Template ID | File | Calendar Actions Used |
|-------------|------|----------------------|
| `productivity.ecosystem_briefing` | `library/productivity/ecosystem_briefing.yaml` | `today_events` |
| `productivity.email_to_calendar` | `library/productivity/email_to_calendar.yaml` | `run_command`, `get_event` |
| `productivity.meeting_prep` | `library/productivity/meeting_prep.yaml` | `upcoming_within` |
| `productivity.morning_briefing` | `library/productivity/morning_briefing.yaml` | `today_events` |

**Unique calendar actions across all templates:**
- `today_events` (2 templates)
- `run_command` (1 template)
- `get_event` (1 template)
- `upcoming_within` (1 template)

---

## 2. Existing Calendar Infrastructure

### 2.1 `_ACTION_MAP` in `step_runner.py` (lines 204-210)

```python
("calendar", "list_events"): "execute_capability",
("calendar", "create_event"): "execute_capability",
("calendar", "get_todays_events"): "execute_capability",
("calendar", "get_event"): "execute_capability",
("calendar", "run_command"): "execute_capability",
("calendar", "today_events"): "execute_capability",
("calendar", "upcoming_within"): "execute_capability",
```

**Assessment:** All 7 calendar actions are routed to `execute_capability`. The routing table is complete, but the underlying provider is missing.

### 2.2 `APP_CAPABILITIES` in `app_operator.py` (line 3163)

```python
APP_CAPABILITIES = {
    "chrome": ["search", "open_url", "youtube", "new_tab"],
    "edge": ["search", "open_url", "youtube"],
    "firefox": ["search", "open_url", "youtube"],
    "brave": ["search", "open_url", "youtube"],
    "comet": ["search", "open_url", "youtube"],
    "spotify": ["play", "pause", "next", "previous"],
    "vlc": ["play", "pause"],
    "youtube": ["play"],
    "vscode": ["open_project", "open_file"],
    "telegram": ["send_message"],
    "capcut": ["play"],
}
```

**Assessment:** `calendar` is **NOT** in `APP_CAPABILITIES`. The `execute_capability()` function checks this dict and rejects unknown capabilities. Even if a provider existed, this would need updating.

### 2.3 `CapabilityResolver` in `capability_resolver.py` (line 24)

```python
_CAPABILITY_TO_PROVIDER = {
    ...
    "calendar": ["calendar"],
    ...
}
```

**Assessment:** Mapping exists. It looks up a provider named `calendar` in the `ProviderRegistry`. No such provider is registered.

### 2.4 Status Check in `status.py` (line 102-103)

```python
def _check_calendar(self) -> dict[str, Any]:
    return {"available": False, "reason": "Calendar provider not implemented"}
```

**Assessment:** Hardcoded to always return `False`. No actual availability check.

### 2.5 Provider Registry

**Assessment:** No `CalendarProvider` class exists anywhere in the codebase. No file named `calendar_provider.py` exists. No `class.*Calendar` matches found.

### 2.6 OAuth / Credentials

**Assessment:** No references to `google_oauth`, `calendar.readonly`, or `calendar.events` scopes exist in the provider code. Templates declare these credentials but no infrastructure consumes them.

---

## 3. Template-by-Template Analysis

### 3.1 `productivity.ecosystem_briefing`

| Field | Value |
|-------|-------|
| **Calendar step** | `capability: calendar`, `action: today_events` |
| **Other capabilities** | `ai_reasoning`, `filesystem`, `communication` |
| **Other blockers** | None — `filesystem`, `communication`, `ai_reasoning` are all implemented |
| **Fully blocked by calendar?** | ✅ **YES** — calendar is the sole blocker |

### 3.2 `productivity.email_to_calendar`

| Field | Value |
|-------|-------|
| **Calendar steps** | `capability: calendar`, `action: run_command` (create event); `capability: calendar`, `action: get_event` (verify) |
| **Other capabilities** | `ai_reasoning` (detect_event) |
| **Other blockers** | None — `ai_reasoning` is implemented |
| **Fully blocked by calendar?** | ✅ **YES** — calendar is the sole blocker |

### 3.3 `productivity.meeting_prep`

| Field | Value |
|-------|-------|
| **Calendar step** | `capability: calendar`, `action: upcoming_within` |
| **Other capabilities** | `ai_reasoning`, `communication`, `memory` |
| **Other blockers** | None — all other capabilities are implemented |
| **Fully blocked by calendar?** | ✅ **YES** — calendar is the sole blocker |

### 3.4 `productivity.morning_briefing`

| Field | Value |
|-------|-------|
| **Calendar step** | `capability: calendar`, `action: today_events` |
| **Other capabilities** | `ai_reasoning`, `knowledge`, `communication`, `mcp_tool` |
| **Other blockers** | `mcp_tool` requires an MCP server connection (may be unavailable depending on config) |
| **Fully blocked by calendar?** | ⚠️ **PARTIALLY** — calendar is blocked, and `mcp_tool` may also be blocked depending on deployment |

---

## 4. Gap Summary

| Component | Status | What's Missing |
|-----------|--------|----------------|
| `CalendarProvider` class | ❌ Missing | Entire provider implementation (must implement `ExecutionProvider`) |
| `APP_CAPABILITIES["calendar"]` | ❌ Missing | Entry in `app_operator.py` with supported actions |
| `_check_calendar()` | ❌ Stub | Always returns `False` — needs actual OAuth/credential check |
| OAuth integration | ❌ Missing | Google Calendar API client, token refresh, scope handling |
| Credential vault entry | ❌ Missing | Storage/retrieval of `calendar_oauth` credential |
| Provider registration | ❌ Missing | No code registers a calendar provider with `ProviderRegistry` |
| Action implementations | ❌ Missing | `today_events`, `upcoming_within`, `run_command`, `get_event`, `list_events`, `create_event`, `get_todays_events` |

---

## 5. Required Actions to Enable Calendar

To make calendar functional, the following must be built:

1. **`CalendarProvider(ExecutionProvider)`** — new file at `mini_kio/core/providers/calendar_provider.py`
   - `id()` → `"calendar"`
   - `capabilities()` → list of `ProviderCapability` for each action
   - `health()` → check OAuth token validity
   - `execute(action, target, **kwargs)` → dispatch to Google Calendar API
   - Actions to implement: `today_events`, `upcoming_within`, `run_command`, `get_event`, `list_events`, `create_event`, `get_todays_events`

2. **`APP_CAPABILITIES["calendar"]`** — add to `app_operator.py:3163`

3. **OAuth credential handling** — integrate with `CredentialVault` for `calendar_oauth` token

4. **Status check** — update `_check_calendar()` in `status.py` to actually verify token availability

5. **Provider registration** — register `CalendarProvider` in the startup/initialization flow

---

## 6. Recommendation

### **Category C: Requires Significant Implementation**

Calendar is a **new provider** that must be built from scratch. The infrastructure scaffolding exists (routing table, capability resolver, status check stub) but has zero functional code.

**Effort estimate:** ~3-5 days for a working implementation including:
- Google Calendar OAuth flow
- Provider class with 7 action implementations
- Credential vault integration
- Unit tests

**Priority:** All 4 calendar templates are production-ready (proper error handling, verification, idempotency keys). They become immediately usable once the provider is built.

---

*Audit performed: 2026-09-15 | Read-only — no changes made to source code*
