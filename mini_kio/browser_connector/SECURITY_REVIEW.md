# Browser Connector V1 — Security Review

## Threat Model

| Threat | Vector | Mitigation |
|--------|--------|-----------|
| Unauthorized WebSocket connection | Any process on localhost can `ws://127.0.0.1:9877` | Token-based auth via `connect` handshake |
| Token leak | Logs, error messages, extension storage | `secrets.token_hex(32)` — 256-bit entropy; token never logged |
| Malicious extension | Fake extension sends crafted commands | Only one connection accepted; token validated per message |
| Tab permission abuse | Open/close/focus any tab | List-only owned tabs (registry filters); commands only on owned tabs |
| Replay attack | Intercept and resend token | Token is single-shot per connection; new token per `Connector()` instance |
| Denial of service | Flood WebSocket with messages | Single pending command per lock; 30s timeout per command |
| Loopback only | External network access | Explicit `host="127.0.0.1"` — never binds to 0.0.0.0 |

## Permission Justification

### Chrome Extension Permissions

| Permission | Why Needed | Risk |
|-----------|-----------|------|
| `tabs` | Query/close/focus tabs, read URLs | **Required** for tab management |
| `activeTab` | Focus active tab | **Required** for `focus_tab` command |
| `ws://127.0.0.1/*` | WebSocket to local connector | **Required** — loopback only |
| `http://127.0.0.1/*` | Localhost HTTP access | **Not used** — remove in future |

**Verdict**: Minimum viable permission set. No `storage`, `cookies`, `downloads`,
`webRequest`, `scripting`, or `debugger` permissions.

## Data Flow Security

```
User → KIO → Connector.open_tab(url) → WebSocket → Extension → chrome.tabs.create(url)
                     ↓                                                      ↓
                 TabRegistry.add(tab) ←────────────────── result{tab_id, url}
```

1. **URL validation**: `protocol.py` validates `http://` or `https://` scheme,
   max 2048 chars, in `validate_open_tab()` before any dispatch.
2. **Ownership enforcement**: `TabRegistry.validate_ownership()` guards all
   close/focus operations against non-KIO tabs.
3. **Response validation**: Only `tab_id` and `url` from extension are trusted;
   all other fields default to safe values.

## Attack Surface Summary

| Component | Attack Surface | Risk Level |
|-----------|---------------|-----------|
| `connector.py` WebSocket server | 1 TCP port (9877) on loopback | LOW |
| `protocol.py` deserialization | JSON parsing | LOW — standard library |
| `registry.py` ownership | Tab ID validation | LOW — integer bounds check |
| Extension `background.js` | Chrome tab API | LOW — permitted operations only |

## Recommendations

1. **Remove `http://127.0.0.1/*`** from manifest host_permissions (not used).
2. **Never expose port 9877** outside loopback in any deployment.
3. **Rotate token** on `close_browser_capability` to prevent stale token reuse
   (future integration concern).
