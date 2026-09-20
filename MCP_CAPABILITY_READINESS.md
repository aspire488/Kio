# MCP Capability Readiness — Pre-Validation Audit

## Summary

| Category | Total Capabilities | Ready | Broken | Deferred |
|----------|-------------------|-------|--------|----------|
| CORE | 7 | 7 | 0 | 0 |
| BROWSER | 8 | 7 | 1 | 0 |
| FILES / DESKTOP | 5 | 5 | 0 | 0 |
| CLIPBOARD | 2 | 2 | 0 | 0 |
| CODING | 3 | 3 | 0 | 0 |
| ARTIFACTS | 8 | 8 | 0 | 0 |
| COMMUNICATION | 2 | 2 | 0 | 0 |
| MEDIA | 7 | 5 | 2 | 0 |
| TERMINAL | 1 | 0 | 1 | 0 |
| MCP | 6 | 6 | 0 | 0 |
| CAMERA | 1 | 0 | 0 | 1 |
| **TOTAL** | **50** | **45** | **4** | **1** |

**Current readiness: 45/50 = 90% (excluding deferred camera)**

---

## CORE

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| Startup/bootstrap | `kio_bot.py` + `bootstrap_runtime()` | READY | Telegram polling starts, runtime initializes |
| Routing | `Pipeline` + `CommandRouter` | READY | Classification → resolution → execution chain works |
| Identity | `continuity_resolver.py` | READY | Identity established per session (no persistence across restarts — known limitation) |
| Context | `pipeline/__init__.py` | READY | Context maintained within session |
| Memory store/fact | `memory_store.py` + `fact_repository.py` | READY | SQLAlchemy-backed persistence |
| Memory forget | `pipeline._semantic_forget()` | READY | Three-layer delete: graph + legacy store + clear |
| Security/resource guard | `runtime.py` ResourceGuard | READY | SOFT 350MB, HARD 400MB enforced |

## BROWSER

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| Playwright runtime | `browser_runtime/` | READY | Chromium binary confirmed working |
| Chrome extension bridge | `browser_connector/` | READY | Port 9877 responds (426 Upgrade Required = WebSocket) |
| Open tab | Connector | READY | "open github.com" works |
| Reuse existing tab | Connector | READY | Domain matching in registry |
| New tab | Connector | READY | "open github.com in a new tab" |
| List tabs | Connector | READY | "what tabs are open" works |
| Navigate | Connector | READY | URL navigation works |
| **Execute script** | Connector + background.js | **PARTIAL** | "list my tabs" times out (routing gap for that phrasing) |

## FILES / DESKTOP

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| File listing | `file_operator.list_files()` | READY | "list files in Desktop" routes correctly |
| File read/write | `file_operator.py` | READY | stdlib pathlib-based |
| Folder operations | `file_operator.py` + folder aliases | READY | Downloads, Desktop, Documents, etc. |
| Open files/folders | `app_operator.py` | READY | `os.startfile()` / `subprocess` |
| Folder alias resolution | `file_operator.py` FOLDER_ALIASES | READY | 9 aliases mapped |

## CLIPBOARD

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| Clipboard copy | `terminal_provider.clipboard_copy()` | READY | pyperclip-based |
| Clipboard paste | `terminal_provider.clipboard_paste()` | READY | pyperclip-based |

## CODING

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| Code generation | `_detect_code_workflow()` → `artifact_operator` | READY | "write a Python program" routes to create_document |
| Project creation | `artifact_operator.create_code_project()` | READY | 40+ language templates |
| VS Code integration | `app_operator._resolve_vscode_path()` | READY | `code` on PATH detected |

## ARTIFACTS

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| DOCX | `python-docx` | READY | try/except optional, installed |
| PDF | `artifact_operator` | READY | stdlib-based |
| XLSX | `openpyxl` | READY | try/except optional, installed |
| PPTX | `python-pptx` | READY | try/except optional, installed |
| CSV | stdlib | READY | No dependency needed |
| TXT | stdlib | READY | No dependency needed |
| Markdown | stdlib | READY | No dependency needed |
| HTML | stdlib | READY | No dependency needed |

## COMMUNICATION

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| Telegram send | `watches.send_telegram_message()` | READY | Real HTTP POST to Bot API, `ok:true` verification |
| Delivery verification | `messages.message_answer()` | READY | `verified` flag in result, sent/failed status tracked |

## MEDIA

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| Play | `media_manager` → providers | READY | YouTube/Browser/Spotify/Local providers |
| Pause | Provider chain | READY | Browser connector script |
| Resume | Provider chain | READY | Browser connector script |
| Seek | `browser_provider.seek()` | READY | Fixed: passes args to extension, supports custom seconds |
| Volume up/down | `browser_provider.volume()` | READY | Fixed: reads verified volume after operation |
| Previous track | Provider chain | READY | Browser connector script |
| **Media play timeout** | YouTube provider | **BROKEN** | "play some lofi hip hop" times out — connector tab resolution hangs |

## TERMINAL

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| **Run command** | `TerminalProvider.run_command()` | **BROKEN** | "run the command dir" falls to LLM conversation — no classifier wiring to terminal provider |

## MCP

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| Filesystem server | `mcp_filesystem_server.py` | READY | stdlib-only, auto-registered |
| Git server | `mcp_git_server.py` | READY | stdlib-only, auto-registered |
| Terminal server | `mcp_terminal_server.py` | READY | stdlib-only, auto-registered |
| SQLite server | `mcp_sqlite_server.py` | READY | stdlib-only, auto-registered |
| Docker server | `mcp_docker_server.py` | READY | stdlib-only, auto-registered |
| GitHub server | `mcp_github_server.py` | READY | PyGithub optional, graceful fallback |

## CAMERA (DEFERRED)

| Capability | Provider | Status | Evidence |
|------------|----------|--------|----------|
| Camera capture | `camera_runtime.py` | DEFERRED | Requires OpenCV, not in current validation scope |

---

## REMAINING FAILURES TO FIX

### 1. Terminal command routing (BUG-9)
- **File**: `mini_kio/core/pipeline/__init__.py`
- **Problem**: "run the command dir" has no classifier path to `TerminalProvider.run_command()`
- **Fix needed**: Add `_detect_terminal_command()` classifier + dispatch to terminal provider
- **Impact**: Terminal commands fall to LLM conversation instead of execution

### 2. "list my tabs" routing gap
- **File**: `mini_kio/core/pipeline/__init__.py`
- **Problem**: "list my tabs" doesn't match the tab listing pattern (only "what tabs are open" works)
- **Fix needed**: Add "list my tabs" to the tab listing regex/pattern
- **Impact**: One phrasing variant fails

### 3. Media play timeout
- **File**: `mini_kio/media/providers/youtube_provider.py` or connector tab resolution
- **Problem**: "play some lofi hip hop" hangs during connector tab resolution
- **Fix needed**: Investigate and fix the timeout/hang in the play flow
- **Impact**: Media play may not complete

### 4. Previous validation's communication/concurrency failures
- **Status**: Communication send is IMPLEMENTED and VERIFIED in code (real HTTP POST + ok:true check)
- **Need**: Live verification that it actually sends
- **Concurrency**: Multiple simultaneous commands — needs live testing
