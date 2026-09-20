# KIO Stabilization Report — Session 2026-09-12 (console window + artifacts)

**Branch**: `kio-restoration-safety-20260823`
**Base SHA at session start**: `f46e21c44119568a1470eee75bcd60f96b19a35c`
**Status**: **REPAIRS VERIFIED OFFLINE — LIVE VALIDATION NOT YET RUN**
**Scope obeyed**: no Pipecat, no workflows/routines, no n8n, no Docker install,
no premature Telegram validation, no speculative packages.

This report supersedes the previous "CONDITIONALLY STABLE — LIVE VALIDATION
PENDING" verdict. The Blocker A (console window) issue is now root-caused and
fixed; previously it was only worked around per-call-site.

---

## 1. Blocker A — the unwanted KIO console window (FIXED, root-caused)

### 1.1 What was wrong

KIO itself runs console-less (`launch_kio.vbs` → `python.exe` with window style
0, or a hidden launcher). On Windows, a **console-subsystem child started from a
console-less parent gets a brand-new visible console window** unless
`CREATE_NO_WINDOW` is passed. This was verified empirically on this machine
(`tools/_probe_console_window.py`), spawning `cmd.exe` from `pythonw.exe` and
enumerating visible top-level windows:

| Child spawn options | Visible console window |
|---------------------|------------------------|
| no flags | **YES** |
| `capture_output=True` (piped stdio) | **YES** |
| `creationflags=0x00100000` (`CREATE_BREAKAWAY_FROM_JOB`) | **YES** |
| `creationflags=0x08000000` (`CREATE_NO_WINDOW`) | no ✅ |

Two conclusions, both of which contradict assumptions baked into the codebase:

1. Redirecting stdout/stderr does **not** suppress the window, so every
   unflagged `subprocess.run(..., capture_output=True)` helper call
   (`tasklist`, `where`, `powershell`, `nvidia-smi`, `git`) was popping a real
   console window while KIO ran.
2. `0x00100000` is **not** `CREATE_NO_WINDOW`; it is
   `CREATE_BREAKAWAY_FROM_JOB`, which does not suppress a window.

### 1.2 The specific defect

`mini_kio/core/providers/terminal_provider.py` — the provider the pipeline uses
for `run_command`:

```python
subprocess.Popen(args, creationflags=0x00100000)   # visible console window
```

It also never captured output and never waited, so it reported
`success: True, exit_code: 0` with an empty message **regardless of what the
command actually did** — a fake-success source as well as a window source.

### 1.3 The fix (systemic, not a workaround)

New shared helper `mini_kio/core/win_spawn.py`:

```python
subprocess.run(cmd, capture_output=True, **no_window())   # CREATE_NO_WINDOW on win32
```

Applied to every internal helper spawn reachable in the current direct
capability scope:

| File | Sites |
|------|-------|
| `core/providers/terminal_provider.py` | `cmd.exe`, now also captures output + real exit code |
| `core/app_operator.py` | `Get-StartApps`, `taskkill`, `where` ×2, `tasklist` |
| `core/operational_health.py` | `nvidia-smi` GPU probe |
| `core/kio_diagnostics.py` | `tasklist` fallback |
| `core/routing_utils.py` | connector `taskkill` |
| `core/system_operator.py` | `shutdown /s`, `shutdown /r`, `rundll32` lock |
| `core/mcp/servers/mcp_git_server.py` | `git` |
| `core/mcp/servers/mcp_docker_server.py` | `docker` |
| `desktop/__init__.py` | `WindowManager` powershell probes ×2 |
| `media/providers/spotify_provider.py` | Spotify `tasklist` probe |

### 1.4 Verification

`tools/audit_spawn_flags.py` (AST walk over `mini_kio/`):

```
spawn sites scanned: 44
exempt (documented GUI/non-Windows launchers): 11
uncovered (no CREATE_NO_WINDOW): 0
```

The 11 exemptions are deliberate and documented in the script: visible GUI
launchers (`explorer.exe` — a user-requested action must stay visible) and
non-Windows tools (`xdg-open`, `open`, `osascript`, `notify-send`, `pkill`)
which are never reached on win32.

`tools/verify_no_console_window.py` (runs itself under `pythonw.exe`, samples
top-level windows every 5 ms while exercising real spawn paths):

```
parent_has_console: false
TerminalProvider.run_command('dir')      → 0 windows
WindowManager.list_windows()             → 0 windows
app_operator._uwp_start_apps()           → 0 windows
kio_diagnostics tasklist fallback        → 0 windows
operational_health._system_metrics()     → 0 windows
GitMCPServer._git(...)                   → 0 windows
mcp_docker._run_docker(['version'])      → 0 windows
terminal allowlist rejects 'rm -rf /'    → 0 windows
total_windows_created: 0   →  PASS
```

Terminal output is now real: `run_command('dir')` → `success: True`,
`exit_code: 0`, 364 lines of real stdout.

**Blocker B is untouched by this fix**: user-requested visible actions still go
through `os.startfile()` / `explorer.exe` and remain visible. The spawn audit
explicitly whitelists them so a future "console-window" fix cannot silently
turn them into hidden background actions.

---

## 2. "Duplicate KIO runtime" — investigated and **DISPROVED** (one runtime)

The live process table looked like two runtimes:

```
PID 12996  python.exe -u kio_bot.py   (parent 10684, exited)
PID 13112  python.exe -u kio_bot.py   (child of 12996, +0.22 s, identical argv)
PID 13112  owns 127.0.0.1:9877 and wrote runtime_ready.flag
```

It is **not** a duplicate. The two entries are the Python 3.14 **venv
redirector** and the base interpreter it execs:

| PID | image (`exe`) | size | role |
|-----|---------------|------|------|
| 12996 | `.venv/Scripts/python.exe` | 255 200 B | venv redirector shim |
| 13112 | `C:\Python314\python.exe` | 106 208 B | real interpreter, owns the runtime |

Proved by launching a trivial venv run and inspecting its children: every
`.venv/Scripts/python.exe` run spawns a `C:\Python314\python.exe` child with the
same argv. Corroborated by the ownership guard: a second `python -u kio_bot.py`
run prints

```
[RUNTIME_OWNER] another KIO runtime already owns the service
[LIFECYCLE] startup refused: another KIO runtime is active
```

and exits, so a genuine second runtime cannot start while one is live. Gate
item 0.3 ("exactly one KIO runtime") is therefore **satisfied**.

### 2.1 Still pending: the live runtime is running PRE-FIX code

The running instance was started before this session's edits, so none of the
fixes are live yet. A restart is required, and this session could not perform
it: `taskkill` returns `Access is denied` for both PIDs, i.e. the running KIO
was started **elevated** (a normal-integrity shell cannot terminate it).

Restart procedure (needs an Administrator shell, or Task Manager → end the
two `python.exe` entries whose command line is `-u kio_bot.py`):

```bat
cscript //nologo launch_kio.vbs      ::  hidden-window launcher, starts one runtime
```

Then confirm: one `kio_bot.py` runtime (the redirector pair counts as one),
`runtime_ready.flag` names the new interpreter PID, and 127.0.0.1:9877 is
listening again.

### 2.2 `live_telegram_test.py::start_kio()` window risk (fixed)

The live-test harness spawned KIO with `subprocess.Popen([sys.executable, "-u",
kio_bot.py])` and **no** creation flags. That harness is not the runtime, but if
it is ever run without an attached console it would pop exactly the window this
session set out to eliminate. It now passes `no_window()`, matching
`launch_bot.py`.

---

## 3. Phase 4 — artifacts (major priority)

### 3.1 PDF was a fake capability — now real

Before this session, `artifact_operator` had **no PDF path at all**: the kind
map sent "pdf" to the DOCX branch, so *"create a PDF version of the report"*
wrote a `.docx` and reported success. There is no stdlib PDF writer in the
stack, so PDF is now produced through the **installed Microsoft Word**
(`Word.Application` COM → `ExportAsFixedFormat(..., 17)`), in a bounded worker
thread with `DispatchEx` (never hijacks a user-visible Word window) and
`Visible=False`. If Word is unavailable the request **fails with an explicit
message** instead of writing a `.docx`.

### 3.2 Spreadsheet fallback destroyed real content

`validate_spreadsheet_content()` only recognised pipe rows that *start* with
`|`, so the unpadded form the model actually returns
(`Capability | Provider | Verified`) was judged "not tabular" and replaced by
`deterministic_spreadsheet_content()` — the generic `Item/Quantity/Cost`
filler. Fixed in `artifact_contract.py` (recognise any row with ≥2 `|`) and in
`_parse_spreadsheet_rows` (parse unpadded pipe rows). The user's explicit rule
"do not use generic filler text" now holds for real tables.

### 3.3 CSV was written verbatim, producing a one-column file

`content = raw_content.strip(); path.write_text(content)` meant a pipe or
markdown table became `A|B|C` inside a `.csv`. `.csv`/`.tsv` now normalise
through `_parse_spreadsheet_rows` + the `csv` module into real delimited data.

### 3.4 Verification — 8/8 with independent readers

`tools/verify_artifacts.py` generates each format through the real
`create_artifact` entry point and re-opens the file with its own native library
(python-docx / openpyxl / python-pptx / stdlib `csv`), never with KIO's own
verifier:

| Kind | Generated | Independently verified |
|------|-----------|------------------------|
| DOCX | `Kio_Architecture_Report_Overview.docx` | 10 paragraphs, **1 table**, 3 headings, first heading "KIO Architecture" |
| PDF | `Kio_Architecture_Report_PDF.pdf` | header `%PDF-1.7`, `%%EOF` present, 1 page, 174 010 bytes |
| XLSX | `Kio_Capability_Inventory_Spreadsheet.xlsx` | 1 sheet, 8 rows × 3 cols, 24 non-empty cells, header `Capability/Provider/Verified` |
| PPTX | `Kio_Overview_Presentation.pptx` | 9 slides, 189 words, 9 notes slides |
| CSV | `Kio_Validation_Cases_Overview.csv` | parses to 8 rows × 3 cols, header `Capability/Provider/Verified` |
| TXT | `Kio_Validation_Notes_Overview.txt` | 113 words, 773 chars |
| MD | `Kio_Architecture_Summary_Overview.md` | 4 markdown headings, 37 words |
| HTML | `Kio_Architecture_Page_Overview.html` | `<!DOCTYPE`, `<html>`, `<title>`, 112 words |

### 3.6 Media — "audio but no visible YouTube/browser state" (root cause found)

Architecture check first: **no media provider uses a hidden Playwright
browser.** `YouTubeProvider.play()` and `BrowserProvider` both drive
`connector.open_tab()` — i.e. the real, visible Chrome through the extension.
`_ACTIVE_PROVIDERS` is `{youtube, browser, local}` (Spotify is not an active
provider). So the playback path is the visible-browser path by design, and the
"hidden substitute" was not a different provider.

The real cause was in the extension itself
(`browser_connector/extension/background.js`):

```js
await chrome.windows.update(tab.windowId, { focused: true });
```

**Focusing a minimized window does not restore it.** If the user's Chrome was
minimized, the YouTube tab was created, playback started (audio) and the window
stayed minimized — playback with no visible browser state, exactly the symptom
reported. Fixed with an `ensureWindowVisible(windowId)` helper used by
`handleOpenTab`, `handleFocusTab` and `handleNavigateTab`: it restores the
window only when `state === "minimized"` (a maximized/fullscreen window is a
deliberate user choice and is never resized), then focuses it.

Status: JS syntax checked (`node --check`). **Not verified live** — the
unpacked extension must be reloaded in Chrome and the play sequence re-run
before this can be called verified.

### 3.5 Known deviation — slide-count fidelity (open item)

*"Create a five-slide PowerPoint"* with a five-slide seed produced a **9-slide**
deck: the presentation design engine inserts title/section slides.
`create_presentation()` takes no target slide count, so an explicit "five-slide"
request is not honoured. Recorded as an open deviation, **not** as a pass.

---

## 4. Regression status

`pytest tests/test_execution_fabric.py tests/test_gap_closure_v3.py`:
**13 failed, 167 passed** (89.9 s) — the same failure identities observed before
this session's edits. Each failing assertion was inspected and sits outside the
diff: desktop `type` classification (`'run_command' != 'type'`), `run vscode`
classified as `FILE` rather than `DESKTOP_OPEN`, WebP/UWP camera discovery,
DOCX fixture content without a table, PPTX fixture assertions, and casual
fragment routing. None involve subprocess creation flags, the artifact PDF
path, spreadsheet validation or CSV normalisation.

These are pre-existing and are **not** fixed here — fixing the classifier
family is a separate unit of work and was out of this session's scope.

---

## 5. Files changed this session

| File | Change |
|------|--------|
| `mini_kio/core/win_spawn.py` | **new** — `no_window()` / `CREATE_NO_WINDOW` helper + rationale |
| `mini_kio/core/providers/terminal_provider.py` | real `CREATE_NO_WINDOW` run, captured output, true exit code |
| `mini_kio/core/app_operator.py` | 5 helper spawns flagged |
| `mini_kio/core/operational_health.py`, `kio_diagnostics.py`, `routing_utils.py`, `system_operator.py` | helper spawns flagged |
| `mini_kio/core/mcp/servers/mcp_git_server.py`, `mcp_docker_server.py` | helper spawns flagged |
| `mini_kio/desktop/__init__.py`, `media/providers/spotify_provider.py` | helper spawns flagged |
| `mini_kio/core/artifact_operator.py` | **PDF kind** (`_PDF_KINDS`, `verify_pdf`, `_docx_to_pdf`), CSV/TSV normalisation, unpadded pipe rows |
| `mini_kio/core/artifact_contract.py` | unpadded pipe rows accepted as tabular data |
| `mini_kio/core/pipeline/__init__.py` | `pdf` → `pdf` in `_ARTIFACT_KIND_MAP` |
| `tools/audit_spawn_flags.py`, `tools/verify_no_console_window.py`, `tools/verify_artifacts.py`, `tools/_probe_console_window.py` | **new** verification harnesses |
| `KIO_REQUIRED_DEPENDENCIES.md`, `KIO_INSTALL_MANIFEST.json` | PDF/Word requirement documented |
| `POST_REPAIR_LIVE_VALIDATION_PLAN.md` | **new** — the one-shot live gate |

## 6. What is still NOT verified

- Live Telegram behaviour (not run — by instruction).
- Visible browser / Chrome-extension / new-tab semantics.
- Visible VS Code open for a created project.
- Clipboard, filesystem, memory forget on the live path.
- Media architecture: root cause found and fixed in the extension (§3.6), but
  the fix needs an extension reload + one live check to be called verified.
- MCP readiness beyond the git/docker probes exercised above.
- Only one KIO runtime: **verified** (§2 — the two PIDs are one runtime).
- The running runtime is still on pre-fix code; restart needs elevation (§2.1).
- 650 MB ceiling on a live run.
