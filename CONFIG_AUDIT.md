# Config Audit — Telegram Startup Blocker

## TELEGRAM_TOKEN

| Field | Value |
|-------|-------|
| Present in .env | Yes (line 9) |
| Format | `[REDACTED — rotate immediately]` (46 chars, botID:hash) |
| Loaded by `config.py` | Yes (`os.getenv("TELEGRAM_TOKEN", "").strip()`) |
| Loaded by `kio_bot.py` | Yes (`from mini_kio.core.config import TELEGRAM_TOKEN`) |
| Malformed | No — correct format |
| Secret value | Redacted from repository |
| Rotation required | Yes — secret was exposed |

## TELEGRAM_PROXY

| Field | Value |
|-------|-------|
| Present in .env | No (was absent before fix) |
| Fallback HTTPS_PROXY | Not set |
| Fallback https_proxy | Not set |
| Result | `None` |

## PROXY

| Source | Value |
|--------|-------|
| Env `HTTPS_PROXY` | (not set) |
| Env `HTTP_PROXY` | (not set) |
| Env `ALL_PROXY` | (not set) |
| WinHTTP proxy | Direct access (no proxy) |

## CUSTOM ENDPOINT

| Field | Value |
|-------|-------|
| Base URL override | None (uses default `https://api.telegram.org/bot`) |
| Local mode | False |
| Custom transport | None |

## RUNTIME BOOTSTRAP

The runtime bootstrap (`runtime.py:bootstrap_runtime()`) checks `TELEGRAM_TOKEN` and calls `start_runtime_channel(runtime, "telegram", run_bot)` only if token is non-empty.

## ROOT CAUSE SUMMARY

- Token: EXPOSED — value removed from repository; rotate via BotFather
- Proxy: NONE
- Custom endpoint: NONE
- **Network: api.telegram.org resolves to unreachable IP `49.44.79.236` (ISP DNS poisoning).**
- **Correct Bot API IP `149.154.166.110` is also blocked at network level.**
