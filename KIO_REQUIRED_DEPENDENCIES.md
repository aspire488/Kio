# KIO Required Dependencies — Source-Verified Matrix

Generated from actual `import` statements traced through every KIO source file.
No speculative dependencies. Only packages proven required by current capabilities.

---

## Classification

- **A: CORE RUNTIME** — Required for KIO to start and route commands
- **B: REQUIRED DIRECT CAPABILITIES** — Required by capabilities in the current validation scope
- **C: REQUIRED MCP INFRASTRUCTURE** — Required by MCP servers that back current capabilities
- **D: OPTIONAL CAPABILITIES** — Not in current validation scope
- **E: DEVELOPMENT/ENGINEERING TOOLS** — Not needed at runtime
- **F: FUTURE / DEFERRED** — Not yet wired
- **G: UNNECESSARY** — Not imported by any KIO code

---

## A. CORE RUNTIME

| Package | PyPI Name | Imported By | Import Style | Installed? |
|---------|-----------|-------------|--------------|------------|
| `psutil` | `psutil` | `runtime.py`, `execution_boundary.py` | Lazy (inside functions) | YES |
| `dotenv` | `python-dotenv` | `config.py`, `kio_bot.py` | Top-level | YES |
| `telegram` | `python-telegram-bot` | `kio_bot.py` | Top-level | YES |

**Core runtime total: 3 packages. All installed.**

---

## B. REQUIRED DIRECT CAPABILITIES (Current Validation Scope)

### BROWSER

| Package | PyPI Name | Imported By | Import Style | Installed? |
|---------|-----------|-------------|--------------|------------|
| `playwright` | `playwright` | `browser_runtime/` | Lazy | YES |
| `websockets` | `websockets` | `browser_connector/connector.py` | Top-level | YES |
| Chromium binary | (playwright install) | `browser_runtime/` | Binary | YES |

**Browser total: 2 packages + 1 binary. All installed.**

### FILES / DESKTOP

| Package | PyPI Name | Imported By | Import Style | Installed? |
|---------|-----------|-------------|--------------|------------|
| (stdlib `os`, `pathlib`, `subprocess`) | — | `file_operator.py`, `app_operator.py` | Top-level | YES |
| `pyperclip` | `pyperclip` | `terminal_provider.py` | Lazy (clipboard) | YES |

**Files/Desktop total: 1 third-party package. Installed.**

### CLIPBOARD

| Package | PyPI Name | Imported By | Import Style | Installed? |
|---------|-----------|-------------|--------------|------------|
| `pyperclip` | `pyperclip` | `terminal_provider.py`, `desktop/__init__.py` | Lazy | YES |

**Clipboard total: 1 package. Installed.**

### ARTIFACTS

| Package | PyPI Name | Imported By | Import Style | Installed? |
|---------|-----------|-------------|--------------|------------|
| `openpyxl` | `openpyxl` | `artifact_operator.py` | try/except optional | YES |
| `docx` | `python-docx` | `artifact_operator.py` | try/except optional | YES |
| `pptx` | `python-pptx` | `artifact_operator.py` | try/except optional | YES |
| `win32com.client` | `pywin32` | `artifact_operator.py` | try/except optional | YES |
| `pythoncom` | `pywin32` | `artifact_operator.py` | try/except optional | YES |
| `csv`, `io`, `tempfile` | (stdlib) | `artifact_operator.py` | Top-level | YES |

**Artifacts total: 4 packages (pywin32 provides 2 modules) + stdlib. All installed.**

#### PDF — no pip package, but a system application is required

`create_artifact(..., artifact="pdf")` produces a **real** PDF by building the
Word document and exporting it through the installed Word application
(`Word.Application` COM → `ExportAsFixedFormat(..., 17)`).

| Requirement | Kind | Status |
|-------------|------|--------|
| `pywin32` | pip package | Installed (`pywin32 312`) |
| Microsoft Word | **system application** | Installed (`HKLM\SOFTWARE\Classes\Word.Application`) |

If Word is unavailable the PDF request **fails with an explicit message** rather
than silently writing a `.docx`. There is no stdlib Office-free PDF writer in
this stack; one was not added because Word is present on the target machine.

*Added 2026-09-12 — before this, `artifact="pdf"` fell through to the DOCX
branch, so “create a PDF” wrote a `.docx` while reporting success.*

### COMMUNICATION (Telegram)

| Package | PyPI Name | Imported By | Import Style | Installed? |
|---------|-----------|-------------|--------------|------------|
| `telegram` | `python-telegram-bot` | `kio_bot.py` | Top-level | YES |
| (stdlib `urllib.request`) | — | `monitoring/watches.py` | Lazy (HTTP POST to Bot API) | YES |

**Communication total: 1 third-party package. Installed.**

### MEDIA

| Package | PyPI Name | Imported By | Import Style | Installed? |
|---------|-----------|-------------|--------------|------------|
| (uses connector + stdlib urllib) | — | `media/providers/*.py` | — | — |

**Media total: 0 third-party packages required. All media providers use browser connector + stdlib urllib.**

### MEMORY / SEMANTIC

| Package | PyPI Name | Imported By | Import Style | Installed? |
|---------|-----------|-------------|--------------|------------|
| `sqlalchemy` | `SQLAlchemy` | `backend/db.py`, `backend/models.py`, `repositories/` | Top-level | YES |

**Memory total: 1 package. Installed.**

### KNOWLEDGE / SEARCH

| Package | PyPI Name | Imported By | Import Style | Installed? |
|---------|-----------|-------------|--------------|------------|
| `duckduckgo_search` | `duckduckgo-search` | `external_world.py`, `retrieval_router.py`, `duckduckgo_provider.py` | Lazy | YES |

**Knowledge total: 1 package. Installed.**

### LLM PROVIDERS

| Package | PyPI Name | Imported By | Import Style | Installed? |
|---------|-----------|-------------|--------------|------------|
| `httpx` | `httpx` | `direct_providers.py`, `freellm_provider.py`, `ollama_provider.py` | Top-level | YES |

**LLM total: 1 package. Installed.**

---

## C. REQUIRED MCP INFRASTRUCTURE

All MCP servers (filesystem, git, terminal, sqlite, docker, github) use **Python stdlib only** (subprocess, json, os, pathlib, sqlite3). Zero third-party packages required.

| Server | Third-Party Deps | Installed? |
|--------|-----------------|------------|
| filesystem | None (stdlib) | YES |
| git | None (stdlib) | YES |
| terminal | None (stdlib) | YES |
| sqlite | None (stdlib `sqlite3`) | YES |
| docker | None (stdlib) | YES |
| github | `PyGithub` (optional, try/except) | NOT INSTALLED (optional) |

**MCP total: 0 required third-party packages.**

---

## D. OPTIONAL CAPABILITIES (NOT in current validation scope)

| Package | PyPI Name | Used By | In Scope? |
|---------|-----------|---------|-----------|
| `cv2` | `opencv-python` | `camera_runtime.py` (lazy) | NO — camera deferred |
| `numpy` | `numpy` | `companion/semantic.py`, `voice/_stt_worker.py` | NO — voice/companion deferred |
| `torch` | `torch` | `voice/_stt_worker.py` (lazy) | NO — voice deferred |
| `sentence-transformers` | `sentence-transformers` | `companion/semantic.py` (lazy) | NO — companion deferred |
| `telethon` | `Telethon` | NOT IMPORTED anywhere | NO — not used |

---

## E. DEVELOPMENT / ENGINEERING TOOLS (NOT needed at runtime)

None identified as required.

---

## F. FUTURE / DEFERRED

| Package | PyPI Name | Notes |
|---------|-----------|-------|
| `yt-dlp` | `yt-dlp` | NOT IMPORTED by any KIO file. In requirements.txt but unused. |
| `tiktoken` | `tiktoken` | NOT IMPORTED by any KIO file. In requirements.txt but unused. |
| `rapidfuzz` | `RapidFuzz` | NOT IMPORTED by any KIO file. In requirements.txt but unused. |
| `regex` | `regex` | NOT IMPORTED by any KIO file. In requirements.txt but unused. |
| `rich` | `rich` | NOT IMPORTED by any KIO file. In requirements.txt but unused. |
| `typer` | `typer` | NOT IMPORTED by any KIO file. In requirements.txt but unused. |
| `scikit-learn` | `scikit-learn` | NOT IMPORTED by any KIO file. In requirements.txt but unused. |
| `scipy` | `scipy` | NOT IMPORTED by any KIO file. In requirements.txt but unused. |

---

## G. UNNECESSARY — DO NOT INSTALL

| Package | Reason |
|---------|--------|
| `torch` | Only in deferred voice module. Not current scope. |
| `sentence-transformers` | Only in deferred companion module. Not current scope. |
| `transformers` | NOT IMPORTED anywhere in KIO. |
| `browser-use` | NOT part of KIO architecture. |
| `langgraph` | NOT part of KIO architecture. |
| `pydantic-ai` | NOT part of KIO architecture. |
| `letta` / `mem0` / `cognee` | NOT part of KIO architecture. |

---

## SUMMARY

| Category | Packages Required | Packages Installed | Gap |
|----------|------------------|-------------------|-----|
| A: Core Runtime | 3 | 3 | 0 |
| B: Direct Capabilities | 9 | 9 | 0 |
| C: MCP Infrastructure | 0 | 0 | 0 |
| **TOTAL REQUIRED** | **12** | **12** | **0** |

**Every required dependency for the current validation scope is already installed.**
**No pip install commands are needed.**
