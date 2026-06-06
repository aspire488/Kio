# Browser Connector V1 — Architecture Review

> **Canonical architecture document.**
> Updated: 2026-06-04
> Audit scope: All 14 Browser Connector documentation files across the repository.
> Runtime source of truth: `connector.py`, `background.js`, `protocol.py`, `registry.py`, `command_router.py`.

---

## 1. Documentation Drift Report

| # | Document | Outdated Section | Why Incorrect | Correct Description |
|---|----------|-----------------|---------------|-------------------|
| 1 | `ARCHITECTURE_REVIEW.md` (this file, prior version) | "Files to Create" §1 | Lists `poc_server.py` which was never created; estimates background.js at ~100 lines (actual: 249). Token described as uuid4 (128-bit); actual is `secrets.token_hex(32)` — 256-bit. Extension token described as "hardcoded for POC"; actual has bootstrap flow. | See §3 (V1 Reality Snapshot) below. |
| 2 | `mini_kio/browser_connector/IMPLEMENTATION_REPORT.md` | "Comparison to Spec" §7 | States server uses `asyncio.start_server`; actual server uses `websockets.asyncio.server.serve()`. States background.js is 161 lines; actual is 249 lines. Implies close/focus operate on "owned tabs only" in the full sense; command_router's close handler falls through to existing close path on non-owned tabs. States `list_tabs` returns owned tabs only; actual returns ALL tabs with `is_owned` flag. | Server: `websockets.asyncio.server.serve()`. background.js: 249 lines. Close: owned-tab check via `_tab_from_target()` with fallback. list_tabs: returns all tabs + `is_owned` flag. |
| 3 | `mini_kio/browser_connector/POC_TEST_PLAN.md` | Entire document | References `poc_server.py` which does not exist. Uses hardcoded token auth flow; current connector uses bootstrap auth (empty token → `set_token` → reconnect). | This document is historical. POC server was never built. |
| 4 | `mini_kio/browser_connector/SECURITY_REVIEW.md` | "Data Flow Security" §3 | States `TabRegistry.validate_ownership()` guards all close/focus operations. The method exists but is NOT called by `command_router.py` — close/focus use `_tab_from_target()` which calls `registry.resolve()`. | Close/focus guarded by `_tab_from_target()` + `registry.resolve()`, not `validate_ownership()`. |
| 5 | `BROWSER_CONNECTOR_FEATURE_FLAG_PLAN.md` | "Activation Sequence" §2 | Uses placeholder `.start()`; actual method is `.start_background()`. Shows `await conn.open_tab()` in planning examples but actual `command_router.py` uses `asyncio.run(conn.open_tab())`. | Method: `start_background()`. Async bridge: `asyncio.run()`. |
| 6 | `BROWSER_CONNECTOR_FAILURE_ANALYSIS.md` | "Failure Mode 3: Port Conflict" §3 | References `asyncio.start_server` (removed). References `connector.start()` (actual: `start_background()`). | Server: `websockets.asyncio.server.serve()`. Start: `start_background()`. |
| 7 | `BROWSER_CONNECTOR_FORENSIC_AUDIT.md` | Entire "Root Cause" analysis | States mock mode is unconditionally hardcoded with `mock=True` and WebSocket server never started. This was patched — mock mode is now controlled by `BROWSER_CONNECTOR_MOCK` env var (default `false`). Real WebSocket transport has been implemented and tested. | Mock configurable via `BROWSER_CONNECTOR_MOCK` env var. Real WebSocket transport exists and is active when flag is `false`. |
| 8 | `BROWSER_CONNECTOR_INTEGRATION_MAP.md` | "Files that MUST change" §Minimum Surface | References `app_operator.py:667` NameError as live bug requiring fix. This was already fixed in the integration patch. | Bug fixed. `app_operator.py` no longer requires changes. |
| 9 | `BROWSER_CONNECTOR_INTEGRATION_REPORT.md` | "Known Limitations" §1 | States "Mock mode only: The connector runs in `mock=True` mode." This is outdated — mock mode is now config-controlled, and real WebSocket transport exists. | Connector uses `config.BROWSER_CONNECTOR_MOCK` (default `false`). Real transport is the default. |
| 10 | `BROWSER_CONNECTOR_V1_SPEC.md` | §2.1 Module Structure, §5.2 Registry Schema, §11.1 Public API | Lists `native_host.py` which does not exist. Shows `_url_index` dict in TabRegistry that is not implemented. Shows `BrowserConnector` class (actual: `Connector`). Shows `ConnectorStatus` enum (actual: boolean `is_connected()`). Shows `list_tabs` as purely local (actual: uses Chrome extension via WebSocket). | No `native_host.py`. No `_url_index`. Class is `Connector`. Status is `is_connected()`. `list_tabs` delegates to extension. |
| 11 | `AUTH_FLOW.md` | None | Accurately describes bootstrap auth flow. Matches current implementation. | No drift. |
| 12 | `MOCK_MODE_AUDIT.md` | None | Accurately describes config-controlled mock behavior. | No drift. |
| 13 | `REAL_TRANSPORT_IMPLEMENTATION_REPORT.md` | None | Accurately describes real WebSocket transport. | No drift. |
| 14 | `TRANSPORT_PROTOCOL_AUDIT.md` | None | Accurately describes protocol transition. | No drift. |

### Drift Summary

| Severity | Count | Documents |
|----------|-------|-----------|
| **None** | 4 | `AUTH_FLOW.md`, `MOCK_MODE_AUDIT.md`, `REAL_TRANSPORT_IMPLEMENTATION_REPORT.md`, `TRANSPORT_PROTOCOL_AUDIT.md` |
| **Minor** | 6 | `ARCHITECTURE_REVIEW.md` (pre-v1), `IMPLEMENTATION_REPORT.md`, `SECURITY_REVIEW.md`, `FEATURE_FLAG_PLAN.md`, `FAILURE_ANALYSIS.md`, `INTEGRATION_MAP.md` |
| **Moderate** | 2 | `V1_SPEC.md` (architectural details), `INTEGRATION_REPORT.md` (mock statement) |
| **Major** | 1 | `FORENSIC_AUDIT.md` (mock-root-cause conclusion — now fixed) |
| **Obsolete** | 1 | `POC_TEST_PLAN.md` (references never-built POC server) |

---

## 2. Architecture Corrections

### Document: `ARCHITECTURE_REVIEW.md` (prior version)

**OLD:**
```
| 1 | mini_kio/browser_connector/poc_server.py | ~80 | WebSocket server, token auth, ping/pong |
```

**NEW:**
```
The POC server was never created. Connector.py directly implements the WebSocket server.
```

**OLD:**
```
| Extension side? | Hardcoded for POC — production would use native messaging to convey token securely |
```

**NEW:**
```
Extension side uses bootstrap flow: connects with empty token → receives set_token → saves to chrome.storage.local → reconnects with token.
```

---

### Document: `IMPLEMENTATION_REPORT.md`

**OLD:**
```
| WebSocket server on 127.0.0.1:9877 | ✅ Via asyncio.start_server |
```

**NEW:**
```
| WebSocket server on 127.0.0.1:9877 | ✅ Via websockets.asyncio.server.serve() (RFC 6455) |
```

**OLD:**
```
| `extension/background.js` | 161 | — | Tab handlers, WS lifecycle, auto-reconnect |
```

**NEW:**
```
| `extension/background.js` | 249 | — | Tab handlers, WS lifecycle, auto-reconnect, bootstrap auth |
```

---

### Document: `BROWSER_CONNECTOR_FORENSIC_AUDIT.md`

**OLD:**
```
The system is a closed loop: KIO talks to MockExtension, which simulates success,
the registry records the simulation, and the user sees "Opened Youtube in Chrome"
— but no Chrome process, tab, or extension was ever involved.
```

**NEW:**
```
This finding is HISTORICAL. The connector was subsequently patched to support real
WebSocket transport. Mock mode is now controlled by BROWSER_CONNECTOR_MOCK env var
(default: false). When BROWSER_CONNECTOR_MOCK=false and BROWSER_CONNECTOR_ENABLED=true:
- WebSocket server binds 127.0.0.1:9877
- Chrome extension connects via new WebSocket("ws://127.0.0.1:9877")
- Tab operations go through real Chrome tabs API
- Registry updates only after extension ACK
- All 82 tests pass (36 mock + 46 real)
```

---

### Document: `BROWSER_CONNECTOR_V1_SPEC.md`

**OLD (Module Structure):**
```
mini_kio/browser_connector/
├── native_host.py         # Native messaging host stub (stdin/stdout)
```

**NEW:**
```
`native_host.py` was specified but never implemented. It is not part of V1.
```

**OLD (Registry Schema):**
```
class TabRegistry:
    _tabs: dict[int, OwnedTab]
    _url_index: dict[str, int]     # url → tab_id (for O(1) lookup)
```

**NEW:**
```
class TabRegistry:
    _tabs: dict[int, OwnedTab]     # No _url_index — lookups are O(n) over small sets
```

**OLD (List Tabs description):**
```
List is purely local — no extension message needed. Registry is kept in sync by tab lifecycle events.
```

**NEW:**
```
List_tabs sends a command to the Chrome extension via WebSocket. The extension calls
chrome.tabs.query({}) and returns all browser tabs. The connector marks each tab with
is_owned based on local registry lookup.
```

---

### Document: `BROWSER_CONNECTOR_INTEGRATION_REPORT.md`

**OLD:**
```
1. Mock mode only: The connector runs in mock=True mode. No real WebSocket
   server, no Chrome extension connection.
```

**NEW:**
```
1. Mock mode is configurable via BROWSER_CONNECTOR_MOCK env var (default: false).
   When mock=false and enabled=true, a real WebSocket server binds on 127.0.0.1:9877
   and accepts Chrome extension connections. Real tab operations use chrome.tabs API.
```

---

## 3. Browser Connector V1 Reality Snapshot

This is the canonical description of the current (V1) implementation.

### Components

| Component | File | Role |
|-----------|------|------|
| `Connector` | `mini_kio/browser_connector/connector.py` (530 lines) | WebSocket server host, command dispatch, background thread lifecycle |
| `TabRegistry` | `mini_kio/browser_connector/registry.py` (167 lines) | In-memory dict of KIO-owned tabs (`tab_id → OwnedTab`) |
| `Protocol` | `mini_kio/browser_connector/protocol.py` (141 lines) | Message dataclasses (`Message`, `OwnedTab`, `TabResult`), validators, serialize/deserialize |
| Extension | `mini_kio/browser_connector/extension/background.js` (249 lines) | Chrome MV3 service worker: WebSocket connect, tab command handlers, heartbeat, auto-reconnect |
| Extension manifest | `mini_kio/browser_connector/extension/manifest.json` | MV3 manifest with `tabs` and `activeTab` permissions |
| Config flags | `kio_final/mini_kio/core/config.py` | `BROWSER_CONNECTOR_ENABLED`, `BROWSER_CONNECTOR_MOCK`, `BROWSER_CONNECTOR_PORT` |
| Integration | `kio_final/mini_kio/core/command_router.py` | Routing for open/close/focus/list_tabs via connector |

### Transport

- **Protocol**: WebSocket RFC 6455
- **Library**: `websockets` 15.0.1
- **Address**: `ws://127.0.0.1:9877`
- **Framing**: UTF-8 JSON text frames
- **Port config**: `BROWSER_CONNECTOR_PORT` env var (default `9877`)
- **Heartbeat**: Ping/pong every 15 seconds (prevents Chrome MV3 service worker eviction)

### Authentication

Bootstrap flow (implemented in `connector._handle_ws()` and `background.js`):

1. Extension connects to WebSocket with empty token `{"type":"connect","token":""}`
2. Connector detects empty token → sends `{"type":"set_token","token":"<256-bit-hex>"}`
3. Extension saves token to `chrome.storage.local`, schedules reconnect (3s)
4. Extension reconnects with saved token → connector validates → `{"type":"connected"}`
5. Token is `secrets.token_hex(32)` — 256 bits of entropy, regenerated per `Connector()` instance

### Ownership Model

- Only tabs created via `open_tab` (confirmed by extension success response) enter `TabRegistry`
- Ownership tracked by Chrome `tab_id` (integer)
- Close/focus operations resolve targets via `registry.resolve()` using: exact URL → domain match → text match in URL or title
- `list_tabs` returns ALL browser tabs with `is_owned` flag computed from local registry
- Unsolicited `tab_closed` / `tab_updated` messages from extension update registry
- Registry is memory-only; cleared on KIO restart (correct by design — Chrome tab IDs invalidate)

### Tab Lifecycle

```
User: "open youtube"
  → command_router.py connector check
  → connector.open_tab("https://youtube.com")
  → _dispatch() → WebSocket → extension handleOpenTab()
  → chrome.tabs.create({url: "https://youtube.com"})
  → extension returns {success: true, tab_id: 42, url: "https://youtube.com"}
  → connector _process_response() → registry.add(OwnedTab(...))
  → return TabResult(success=True)

User: "close youtube"
  → command_router.py connector check
  → connector.close_tab("youtube")
  → _tab_from_target("youtube") → registry.resolve() → OwnedTab(tab_id=42)
  → _dispatch() → WebSocket → extension handleCloseTab()
  → chrome.tabs.remove(42)
  → extension returns {success: true}
  → connector _process_response() → registry.remove(42)

User: "focus youtube"
  → command_router.py connector check
  → connector.focus_tab("youtube")
  → _tab_from_target("youtube") → registry.resolve() → OwnedTab(tab_id=42)
  → _dispatch() → WebSocket → extension handleFocusTab()
  → chrome.windows.update + chrome.tabs.update → tab activated

User: "list tabs"
  → command_router.py connector check
  → connector.list_tabs()
  → _dispatch() → WebSocket → extension handleListTabs()
  → chrome.tabs.query({}) → returns ALL tabs
  → extension returns {tabs: [{tab_id, url, title, window_id}, ...]}
  → connector marks each with is_owned → returns TabResult with tabs[]
```

### Open Behavior

**Current**: `open_tab` always creates a new tab in Chrome. There is no deduplication check, no reuse policy, and no focus-existing behavior.

| Aspect | Implementation |
|--------|---------------|
| Duplicate check | None — every call creates a new tab |
| URL validation | `protocol.py` validates `http://` or `https://` scheme, max 2048 chars |
| Result | `TabResult(success, tab, message)` |
| Fallback | If connector disconnected, falls through to existing `webbrowser.open()` path |

### Close/Focus Behavior

- Resolves target via `_tab_from_target()` using registry lookup chain: `tab_id` integer → exact URL → domain match → text match
- Returns error `"no owned tab matching: {target}"` if not found
- Falls through to existing close path (`close_app`) if connector not connected

### Mock Mode

- `BROWSER_CONNECTOR_MOCK=true` env var enables mock mode
- `MockExtension` generates synthetic tab responses (no WebSocket, no Chrome)
- All 36 original mock tests remain passing
- Default: `BROWSER_CONNECTOR_MOCK=false` (real transport)

### Test Coverage

82 tests total:
- 36 mock-mode tests (original)
- 46 real-transport tests (reality tests with simulated WebSocket interactions)
- Test file: `tests/test_connector.py`

### Current Limitations

1. **No deduplication policy** — `open_tab` always creates a new tab
2. **No `duplicate_mode`** — `skip`/`focus`/`new` not implemented
3. **No URL normalization** — "youtube.com" and "https://youtube.com" are treated as different URLs
4. **No focus-existing** — can't focus an already-open tab instead of creating a new one
5. **No reconnect registry sync** — on extension reconnect, registry is not refreshed from Chrome
6. **Memory-only registry** — tab ownership is lost on KIO restart (acceptable — Chrome tab IDs invalidate)
7. **Single-instance only** — no protection against multiple KIO instances on same port
8. **No multi-extension support** — only one Chrome extension connection at a time
9. **No transport encryption** — not needed for loopback, but not hardened for any other deployment

---

## 4. Planned But Not Implemented

The following features have been discussed in design documents but are **NOT implemented** in the current codebase. They remain future considerations.

| Feature | Description | Design Reference | Status |
|---------|-------------|-----------------|--------|
| `duplicate_mode` | Policy for duplicate URLs: `skip` (silently return), `focus` (activate existing tab), `new` (create anyway) | `ARCHITECTURE_REVIEW.md` companion doc | **Not Implemented** |
| Smart open behavior | Check registry before opening; if URL exists and mode allows, reuse instead of creating | Design discussion | **Not Implemented** |
| URL deduplication | Normalize URLs (strip trailing slashes, `www.` prefix, protocol normalization) before comparison | Design discussion | **Not Implemented** |
| `reuse_existing_tab` | Instead of `open_tab`, activate existing tab with matching URL | Design discussion | **Not Implemented** |
| `focus_existing_tab` | Focus an already-open tab by URL/domain/title match | V1_SPEC.md §3.4 implemented in `focus_tab()`, but not integrated with `open_tab` | **Partially Implemented** (focus command works, but `open_tab` doesn't auto-focus on duplicates) |
| Reconnect registry sync | On extension reconnect, call `list_tabs` to resync owned tab URLs | `FAILURE_ANALYSIS.md §2` | **Not Implemented** |
| Reconnect backoff | Exponential backoff for reconnect attempts (3s → 6s → 12s → 30s max) | `FAILURE_ANALYSIS.md §2` — current code uses fixed 3s | **Not Implemented** |
| Origin validation | Validate WebSocket `Origin` header against known `chrome-extension://` ID | `V1_SPEC.md §6.1` | **Not Implemented** |
| Port fallback | Auto-retry with port 9878, 9879 if 9877 is in use | `FAILURE_ANALYSIS.md §3` | **Not Implemented** |
| Native messaging | Secure token delivery via Chrome native messaging host instead of bootstrap | `V1_SPEC.md §2.1` references `native_host.py` | **Not Implemented** (no `native_host.py` exists) |

### Implementation Status Summary

| Area | Current | Future |
|------|---------|--------|
| **Open behavior** | Always creates new tab | `duplicate_mode` with skip/focus/new policies |
| **Duplicate detection** | None | URL normalization + registry lookup before open |
| **Focus on open** | Separate `focus` command only | Optional focus behavior in `open_tab` |
| **Registry sync** | On command only | On reconnect + periodic sync |
| **Reconnect** | Fixed 3s interval | Exponential backoff |
| **Security hardening** | Token auth only | Origin validation + native messaging |

---

## 5. Final Consistency Review

### Does documentation now match runtime?

**YES** — after this update, `ARCHITECTURE_REVIEW.md` is the canonical description. Four documents (`AUTH_FLOW.md`, `MOCK_MODE_AUDIT.md`, `REAL_TRANSPORT_IMPLEMENTATION_REPORT.md`, `TRANSPORT_PROTOCOL_AUDIT.md`) already accurately describe runtime. The remaining deprecated documents contain minor drift (line counts, method names) and one moderate drift (FORENSIC_AUDIT.md's stale mock-mode conclusion). All drift is documented in §1.

### Are there any remaining references to obsolete V0 architecture?

**NO.** The V0 architecture (content script, filterUrl, DOM scraping, window.location.href) was never fully implemented in any version of this codebase. No file in the repository references:
- `content.js`
- `filterUrl`
- `window.location.href` (in connector context)
- `duplicate_mode`
- Content script architecture

The grep across all `.md` files confirmed zero hits for these terms. The current architecture has always been V1 (WebSocket bridge, background.js, no content script).

### Are there any undocumented runtime behaviors?

**YES** — the following runtime behaviors are not described in any document:

1. **`_asyncio_exception_handler`** — installed in `_run_event_loop()` at `connector.py:271`, catches and logs asyncio internal errors (task crashes, orphaned futures). Documented in §3 now.

2. **Thread exception hook** — `_install_thread_excepthook()` at `connector.py:46-51` installs a global `threading.excepthook` to log thread crashes. Not described in any prior document.

3. **`unsolicited message handlers`** — `_handle_ws()` at `connector.py:516-525` handles `tab_closed` and `tab_updated` messages sent by the extension without a pending command. These maintain registry consistency when the user manually closes or navigates tabs.

4. **Mock mode detail** — `MockExtension` uses a single hardcoded tab response for `list_tabs` (always returns `[{"tab_id": 1, "url": "https://example.com", "title": "Example"}]`) and uses auto-incrementing synthetic `tab_id` values for `open_tab`. Not described in any prior document.

### Architecture Consistency Verdict

```
Status:  CONSISTENT (after this update)
Drift:   0 critical, 1 major (historical — FORENSIC_AUDIT.md stale mock conclusion)
         9 minor (line counts, method names, single-vs-multi-instance close/focus descriptions)
         3 none (remaining documents match runtime exactly)
Fix:     FORENSIC_AUDIT.md should be updated if mock-mode conclusion is reused as reference.
         Other minor drift items are acceptable for planning/discussion documents that represent
         design intent rather than implementation description.

The canonical architecture description in §3 of this document now reflects runtime reality.
No code changes are required — this is a documentation synchronization task only.
```
