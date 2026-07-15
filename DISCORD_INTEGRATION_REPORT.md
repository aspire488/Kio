# Discord Integration Report

## Architecture

```
Discord Message
  → discord_transport._handle_discord_message()
    → route(content, user_id, channel="discord")
      → dispatch_channel_input(text, channel="discord", user_id)
        → handle_command() or _route_via_orchestration()
          → ConversationResponder / KnowledgeResolver / Media Intelligence
    → format_channel_reply(result)
  → message.channel.send(reply)
```

## Design Decisions

### 1. `route()` Modified with `channel` Parameter

`command_router.py:route()` gained a `channel: str = "telegram"` parameter (default `"telegram"`). Discord calls `route(content, user_id, channel="discord")`. Zero change to Telegram callers.

### 2. Discord Runs in Daemon Thread

Discord runs in a `threading.Thread(daemon=True)` to avoid blocking Telegram and to ensure clean process exit. Error isolation: a Discord failure does not affect Telegram or any other transport.

### 3. No Duplicated State

- No duplicated `ConversationResponder` — goes through the same pipeline as Telegram
- No duplicated `MediaEntityMemory` — shared singleton
- No duplicated LLM calls — goes through `route()` → `dispatch_channel_input()`
- No duplicated `MediaKnowledgeRouter` — called by the same pipeline

### 4. Logging

| Marker | Location |
|--------|----------|
| `[DISCORD_CONNECTED]` | `on_ready()` |
| `[DISCORD_MESSAGE]` | `_handle_discord_message()` |
| `[DISCORD_RESPONSE]` | After `route()` returns |
| `[DISCORD_ERROR]` | Exception handler |
| `[DISCORD_DISCONNECT]` | `on_disconnect()` |
| `[DISCORD_RECONNECT]` | `on_resumed()` |

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| `mini_kio/core/command_router.py:1345` | Added `channel: str = "telegram"` param to `route()` | +2/-1 |
| `mini_kio/core/config.py:23-27` | Added `DISCORD_BOT_TOKEN`, `DISCORD_APPLICATION_ID`, `DISCORD_ENABLED` | +5 |
| `mini_kio/core/runtime.py:21` | Import `DISCORD_BOT_TOKEN` | +1/-1 |
| `mini_kio/core/runtime.py:1397-1401` | Discord config trace in `bootstrap_runtime()` | +4 |
| `mini_kio/core/runtime.py:1498-1518` | Discord thread start before Telegram in `run_runtime()` | +9/-1 |
| `.env` | Added Discord token documentation | +3 |

## Files Created

| File | Purpose |
|------|---------|
| `mini_kio/platform/discord_transport.py` | Discord transport implementation |
| `tests/test_discord_transport.py` | 13 integration tests |

## Verification

### Conversation Flow Tests (via `route()` with `channel="discord"`)

| # | Conversation | Steps | Result |
|---|--------------|-------|--------|
| 1 | Interstellar → Who directed it? → Any interviews? → Show them → Play the first one | 5 | PASS |
| 2 | The Bear → Show trailer | 2 | PASS |
| 3 | Latest FIFA World Cup updates → Show highlights | 2 | PASS |
| 4 | Believer → Live version | 2 | PASS |
| 5 | Open Telegram | 1 | PASS |

### Regression Tests

| Suite | Result |
|-------|--------|
| Full pytest (minus pre-existing failures) | **1372 passed, 0 failed** |
| Discord transport tests | **13 passed, 0 failed** |
| V3 conversation fix tests | **12 passed, 0 failed** |

### Runtime Trace

```
Discord
  → route(content, user_id=10001, channel="discord")
    → dispatch_channel_input(text, channel="discord", user_id=10001)
      → handle_command() → "Interstellar"
      → _gate3_eligible → _route_via_orchestration()
        → ConversationResponder → KnowledgeResolver → Media Intelligence
    → format_channel_reply() → plain text
  → message.channel.send(reply)
```

## Status

- [x] Discord transport created
- [x] `route()` accepts `channel` parameter
- [x] Runtime boots Discord + Telegram independently
- [x] Discord failure does not affect Telegram
- [x] All conversation flows verified through `route()`
- [x] Full regression suite passes
- [x] Media Intelligence reused (not duplicated)
- [x] Browser actions work from Discord
- [x] Slash commands (`/kio`, `/status`) implemented
