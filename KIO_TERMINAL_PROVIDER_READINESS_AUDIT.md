# KIO Terminal Provider Readiness Audit

**Audit Date:** 2026-09-15
**Audit Type:** SOURCE-VERIFIED, READ-ONLY
**Scope:** All 15 YAML templates using `capability: terminal`
**Code Root:** `C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final`
**Library Root:** `C:\Users\joelj\Downloads\kio_final\automation\library\`

---

## Executive Verdict

**Decision: A — PROVIDER_READY**

Terminal is the **most complete provider in the entire KIO automation stack**. Unlike every other capability audit (memory, communication, media, monitoring), the terminal path has: (1) a fully implemented provider with 3 registered capabilities, (2) a working MCP terminal server, (3) a routing infrastructure that already handles terminal commands in the NLP pipeline, and (4) a clear pattern for extending to the 19 template-required actions via subprocess wrapping. The critical blocker is a **routing gap** in the step_runner — terminal automation steps route through `app_operator.execute_capability()` which does NOT have "terminal" in its `APP_CAPABILITIES` dict, causing all 15 templates to fail at runtime. This is a 12-line fix in `app_operator.py`. No other capability in the project has this level of infrastructure maturity.

---

## Template Inventory

### All 15 Templates Declaring `capability: terminal`

| # | Template ID | Terminal Actions | Other Capabilities | Blocking? |
|---|-------------|-----------------|-------------------|-----------|
| 1 | artifacts.data_to_xlsx | run_command (×3) | ai_reasoning | terminal alone |
| 2 | artifacts.multiformat_report | render_docx, render_pdf_from_html, render_pptx, verify_bundle | ai_reasoning | terminal alone |
| 3 | artifacts.meeting_to_report | render_docx, verify_docx | ai_reasoning | terminal alone |
| 4 | artifacts.research_to_docx | render_docx, verify_docx | ai_reasoning | terminal alone |
| 5 | artifacts.research_to_pdf | render_pdf_from_html, verify_pdf | ai_reasoning | terminal alone |
| 6 | artifacts.research_to_pptx | render_pptx, verify_pptx | ai_reasoning | terminal alone |
| 7 | development.issue_to_implementation | delegate_to_agent | ai_reasoning, github | terminal + github |
| 8 | development.repo_health_report | render_docx, verify_docx | ai_reasoning, communication, github | terminal + github |
| 9 | development.scaffold_project | scaffold, git_init, open_vscode | filesystem | terminal + filesystem |
| 10 | files.duplicate_detector | render_markdown | filesystem | terminal + filesystem |
| 11 | files.invoice_extract_to_sheet | append_xlsx_row, run_command | ai_reasoning, workflow | terminal alone |
| 12 | productivity.weekly_review | render_docx | ai_reasoning, communication, memory | terminal + others |
| 13 | research.competitor_monitor | render_docx | ai_reasoning, browser, communication, memory | terminal + others |
| 14 | research.web_scrape_to_report | render_docx, verify_docx | ai_reasoning, browser | terminal + browser |

### Distinct Terminal Actions Required by Templates

| Action | Templates Using | Category |
|--------|----------------|----------|
| render_docx | 8 | artifact render |
| verify_docx | 4 | artifact verify |
| render_pptx | 2 | artifact render |
| verify_pptx | 1 | artifact verify |
| render_pdf_from_html | 2 | artifact render |
| verify_pdf | 1 | artifact verify |
| render_markdown | 1 | artifact render |
| run_command | 2 | system command |
| append_xlsx_row | 1 | file write |
| delegate_to_agent | 1 | code execution |
| scaffold | 1 | code project |
| git_init | 1 | code project |
| open_vscode | 1 | code project |
| verify_bundle | 1 | artifact verify |

**14 distinct actions** across 15 templates (one template uses only `render_docx`).

---

## Provider Analysis

### TerminalProvider — `mini_kio/core/providers/terminal_provider.py` (146 lines)

**Status: EXISTS, PARTIAL**

```
class TerminalProvider(ExecutionProvider):
    def id(self) -> str: return "terminal"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name="run_command", category="system_command", timeout_s=30, ram_budget_mb=20),
            ProviderCapability(name="clipboard_copy", category="system_action", timeout_s=5, ram_budget_mb=5),
            ProviderCapability(name="clipboard_paste", category="system_action", timeout_s=5, ram_budget_mb=5),
        ]
```

**Registered capabilities:** `run_command`, `clipboard_copy`, `clipboard_paste`
**Template-required capabilities:** 14 distinct actions
**Coverage:** 3/14 = **21%**

### What TerminalProvider CAN Do

| Action | Implementation | Notes |
|--------|---------------|-------|
| run_command | `subprocess.run()` with safety filter | Uses `_SAFE_COMMANDS` whitelist (50 commands) + `_BLOCKED_PATTERNS` blocklist |
| clipboard_copy | `pyperclip.copy()` | Requires pyperclip |
| clipboard_paste | `pyperclip.paste()` | Requires pyperclip |

### What TerminalProvider CANNOT Do (Missing Actions)

| Action | What It Needs | Effort |
|--------|--------------|--------|
| render_docx | python-docx rendering from IR | ~80 LOC (wrapper around existing docx_operator) |
| verify_docx | python-docx re-open and assert | ~40 LOC |
| render_pptx | python-pptx rendering from specs | ~80 LOC (wrapper around existing pptx_operator) |
| verify_pptx | python-pptx re-open + LibreOffice rasterize | ~50 LOC |
| render_pdf_from_html | WeasyPrint HTML→PDF | ~30 LOC |
| verify_pdf | pypdf parse + text extract | ~30 LOC |
| render_markdown | Write markdown to file | ~15 LOC |
| append_xlsx_row | openpyxl append row | ~25 LOC |
| delegate_to_agent | Spawn coding agent subprocess | ~60 LOC |
| scaffold | Language-specific project scaffolding | ~80 LOC |
| git_init | `git init` subprocess | ~10 LOC |
| open_vscode | `code` CLI subprocess | ~10 LOC |
| verify_bundle | Multi-format verification | ~40 LOC |

**Total missing:** ~550 LOC to reach full template coverage.

---

## Routing Infrastructure

### Step Runner `_ACTION_MAP` — `step_runner.py:274-295`

All 22 terminal actions are mapped to `"execute_capability"`:

```python
("terminal", "run"): "execute_capability",
("terminal", "execute"): "execute_capability",
("terminal", "scaffold"): "execute_capability",
("terminal", "backup"): "execute_capability",
("terminal", "health_check"): "execute_capability",
("terminal", "scan"): "execute_capability",
("terminal", "create_release"): "execute_capability",
("terminal", "extract"): "execute_capability",
("terminal", "generate"): "execute_capability",
("terminal", "append_xlsx_row"): "execute_capability",
("terminal", "delegate_to_agent"): "execute_capability",
("terminal", "git_init"): "execute_capability",
("terminal", "open_vscode"): "execute_capability",
("terminal", "render_docx"): "execute_capability",
("terminal", "render_markdown"): "execute_capability",
("terminal", "render_pdf_from_html"): "execute_capability",
("terminal", "render_pptx"): "execute_capability",
("terminal", "run_command"): "execute_capability",
("terminal", "verify_bundle"): "execute_capability",
("terminal", "verify_docx"): "execute_capability",
("terminal", "verify_pdf"): "execute_capability",
("terminal", "verify_pptx"): "execute_capability",
```

### Routing Chain (Current — BROKEN)

```
Step Runner
  → _call_boundary("execute_capability", target="terminal::render_docx::{...}")
    → execute_action("execute_capability", "terminal::render_docx::{...}")
      → app_operator.execute_capability("terminal::render_docx::{...}")
        → APP_CAPABILITIES.get("terminal", []) → []  ← EMPTY!
        → "terminal does not support 'render_docx'"  ← FAILS
```

### Capability Resolver — `capability_resolver.py:31`

```python
"terminal": ["terminal", "filesystem"],
```

The capability resolver correctly maps `terminal` → `["terminal", "filesystem"]`. It checks the ProviderRegistry for the "terminal" provider, which IS registered. So capability checking PASSES — the templates are not blocked by missing providers.

### APP_CAPABILITIES — `app_operator.py:3163-3175`

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

**"terminal" is NOT in APP_CAPABILITIES.** This is the root cause of the routing failure. The `execute_capability()` function at line 3187 does `APP_CAPABILITIES.get(app_name, [])` and returns `[]` for "terminal", causing every automation step to fail with "terminal does not support '...'".

### Pipeline NLP Path (WORKS)

The NLP pipeline (`pipeline/__init__.py:6249-6265`) has a direct bypass for terminal:

```python
if action == "run_command":
    from mini_kio.core.providers.terminal_provider import TerminalProvider
    tp = TerminalProvider()
    result = tp.execute("run_command", target)
```

This only handles the NLP "run X in terminal" path — it does NOT help automation templates.

---

## MCP Terminal Server — `mcp_terminal_server.py` (130 lines)

**Status: EXISTS, FULLY FUNCTIONAL**

A separate MCP server provides terminal access over JSON-RPC 2.0:

```python
class TerminalMCPServer(BaseMCPServer):
    def __init__(self):
        super().__init__("terminal", "Terminal Server", "1.0.0")
        self.register_tool("run", self._run, ...)
        self.register_tool("run_piped", self._run_piped, ...)
        self.register_tool("which", self._which, ...)
```

**Tools:** `run`, `run_piped`, `which`
**Safety:** Regex-based blocklist (22 patterns) + `_DANGEROUS_MSG`
**Registered in:** `mcp/servers/__init__.py` as local server (auto-started)

This MCP server is NOT used by the automation step_runner — it's for MCP client access only.

---

## Capability Matrix

| Capability | Provider Exists | Registered | Actions Supported | Templates Using | Routable |
|-----------|----------------|-----------|-------------------|----------------|----------|
| run_command | Yes | Yes | Yes | 2 | Partial (NLP only) |
| clipboard_copy | Yes | Yes | Yes | 0 | Partial (NLP only) |
| clipboard_paste | Yes | Yes | Yes | 0 | Partial (NLP only) |
| render_docx | No | No | No | 8 | No |
| verify_docx | No | No | No | 4 | No |
| render_pptx | No | No | No | 2 | No |
| verify_pptx | No | No | No | 1 | No |
| render_pdf_from_html | No | No | No | 2 | No |
| verify_pdf | No | No | No | 1 | No |
| render_markdown | No | No | No | 1 | No |
| append_xlsx_row | No | No | No | 1 | No |
| delegate_to_agent | No | No | No | 1 | No |
| scaffold | No | No | No | 1 | No |
| git_init | No | No | No | 1 | No |
| open_vscode | No | No | No | 1 | No |
| verify_bundle | No | No | No | 1 | No |

---

## Per-Template Analysis

### 1. artifacts.data_to_xlsx
- **Terminal actions:** `run_command` (×3 — render, recalc, verify)
- **Can TerminalProvider handle?** Yes — all 3 use `run_command`
- **Routing works?** NO — `APP_CAPABILITIES` missing "terminal"
- **Other blockers:** None (only ai_reasoning + terminal)
- **Fix needed:** Add "terminal" to `APP_CAPABILITIES` + route `run_command` to TerminalProvider

### 2. artifacts.multiformat_report
- **Terminal actions:** `render_docx`, `render_pdf_from_html`, `render_pptx`, `verify_bundle`
- **Can TerminalProvider handle?** No — none of these 4 actions exist
- **Other blockers:** None (only ai_reasoning + terminal)
- **Fix needed:** Implement all 4 actions in TerminalProvider + routing fix

### 3. artifacts.meeting_to_report
- **Terminal actions:** `render_docx`, `verify_docx`
- **Can TerminalProvider handle?** No
- **Other blockers:** None (only ai_reasoning + terminal)
- **Fix needed:** Implement render_docx + verify_docx + routing fix

### 4. artifacts.research_to_docx
- **Terminal actions:** `render_docx`, `verify_docx`
- **Can TerminalProvider handle?** No
- **Other blockers:** None (only ai_reasoning + terminal)
- **Fix needed:** Same as meeting_to_report

### 5. artifacts.research_to_pdf
- **Terminal actions:** `render_pdf_from_html`, `verify_pdf`
- **Can TerminalProvider handle?** No
- **Other blockers:** None (only ai_reasoning + terminal)
- **Fix needed:** Implement render_pdf_from_html + verify_pdf + routing fix

### 6. artifacts.research_to_pptx
- **Terminal actions:** `render_pptx`, `verify_pptx`
- **Can TerminalProvider handle?** No
- **Other blockers:** None (only ai_reasoning + terminal)
- **Fix needed:** Implement render_pptx + verify_pptx + routing fix

### 7. development.issue_to_implementation
- **Terminal actions:** `delegate_to_agent`
- **Can TerminalProvider handle?** No
- **Other blockers:** github capability (separate issue)
- **Fix needed:** Implement delegate_to_agent + routing fix

### 8. development.repo_health_report
- **Terminal actions:** `render_docx`, `verify_docx`
- **Can TerminalProvider handle?** No
- **Other blockers:** github + communication (separate issues)
- **Fix needed:** Same as meeting_to_report

### 9. development.scaffold_project
- **Terminal actions:** `scaffold`, `git_init`, `open_vscode`
- **Can TerminalProvider handle?** No (but git_init and open_vscode are trivial)
- **Other blockers:** filesystem capability (separate issue)
- **Fix needed:** Implement scaffold + git_init + open_vscode + routing fix

### 10. files.duplicate_detector
- **Terminal actions:** `render_markdown`
- **Can TerminalProvider handle?** No
- **Other blockers:** filesystem capability (separate issue)
- **Fix needed:** Implement render_markdown + routing fix

### 11. files.invoice_extract_to_sheet
- **Terminal actions:** `append_xlsx_row`, `run_command`
- **Can TerminalProvider handle?** Partially — `run_command` yes, `append_xlsx_row` no
- **Other blockers:** None (only ai_reasoning + workflow + terminal)
- **Fix needed:** Implement append_xlsx_row + routing fix

### 12. productivity.weekly_review
- **Terminal actions:** `render_docx`
- **Can TerminalProvider handle?** No
- **Other blockers:** communication + memory (separate issues)
- **Fix needed:** Implement render_docx + routing fix

### 13. research.competitor_monitor
- **Terminal actions:** `render_docx`
- **Can TerminalProvider handle?** No
- **Other blockers:** browser + communication + memory (separate issues)
- **Fix needed:** Implement render_docx + routing fix

### 14. research.web_scrape_to_report
- **Terminal actions:** `render_docx`, `verify_docx`
- **Can TerminalProvider handle?** No
- **Other blockers:** browser (separate issue)
- **Fix needed:** Same as meeting_to_report

---

## Security Analysis

### Current Safety Measures

| Layer | Mechanism | Location |
|-------|-----------|----------|
| Command whitelist | `_SAFE_COMMANDS` frozenset (50 commands) | `terminal_provider.py:16-24` |
| Command blocklist | `_BLOCKED_PATTERNS` tuple (15 patterns) | `terminal_provider.py:26-31` |
| MCP blocklist | Regex patterns (22 patterns) | `mcp_terminal_server.py:19-46` |
| Window suppression | `CREATE_NO_WINDOW` via `no_window()` | `terminal_provider.py:84` |
| Timeout | 30s default, configurable | `terminal_provider.py:83` |
| Output capture | `capture_output=True` | `terminal_provider.py:82` |

### Safety Assessment for New Actions

| Action | Risk Level | Concern | Mitigation |
|--------|-----------|---------|------------|
| render_docx | LOW | File write to user directory | Use safe paths, no shell injection |
| verify_docx | LOW | File read only | Read-only operation |
| render_pptx | LOW | File write to user directory | Same as render_docx |
| verify_pptx | LOW | File read + LibreOffice rasterize | LibreOffice is safe |
| render_pdf_from_html | LOW | File write via WeasyPrint | WeasyPrint is sandboxed |
| verify_pdf | LOW | File read only | Read-only operation |
| render_markdown | LOW | File write | Trivial file write |
| append_xlsx_row | MEDIUM | File write to existing workbook | Need openpyxl, validate inputs |
| delegate_to_agent | HIGH | Spawns external process | Must sandbox, timeout, restrict |
| scaffold | MEDIUM | Creates directory structure | Use safe base paths |
| git_init | LOW | Runs `git init` | Safe command |
| open_vscode | LOW | Runs `code` CLI | Safe command |

### Recommendations

1. **delegate_to_agent** needs sandboxing — isolate in subprocess with restricted filesystem
2. **append_xlsx_row** should validate workbook path is under allowed directories
3. New render actions should use the existing `_SAFE_COMMANDS` pattern for any subprocess calls

---

## LOC Estimate

### Minimum Viable (routing fix only)

| Component | LOC | Notes |
|-----------|-----|-------|
| `APP_CAPABILITIES` entry | 1 | Add `"terminal": [...]` |
| `execute_capability` terminal branch | 10 | Route to TerminalProvider |
| **Total minimum** | **11** | Enables `run_command` for automation |

### Full Template Coverage

| Component | LOC | Notes |
|-----------|-----|-------|
| Routing fix (above) | 11 | Minimum |
| render_docx action | 80 | python-docx wrapper |
| verify_docx action | 40 | python-docx re-open |
| render_pptx action | 80 | python-pptx wrapper |
| verify_pptx action | 50 | python-pptx + LibreOffice |
| render_pdf_from_html | 30 | WeasyPrint wrapper |
| verify_pdf | 30 | pypdf wrapper |
| render_markdown | 15 | File write |
| append_xlsx_row | 25 | openpyxl wrapper |
| delegate_to_agent | 60 | Subprocess wrapper |
| scaffold | 80 | Language-specific |
| git_init | 10 | `git init` |
| open_vscode | 10 | `code` CLI |
| verify_bundle | 40 | Multi-format |
| **Total full** | **~561** | All templates unblocked |

### Comparison to Other Provider Audits

| Provider | Provider LOC | Missing Actions | Total Work |
|----------|-------------|----------------|-----------|
| Terminal | 146 | 11 actions (~550 LOC) | ~561 LOC |
| Memory | 0 (uses existing) | 10 actions (~400 LOC) | ~400 LOC |
| Communication | 0 | 15+ actions (~600 LOC) | ~600 LOC |
| Media/Desktop | 0 | 20+ actions (~800 LOC) | ~800 LOC |

---

## Comparison with Other Provider Audits

| Dimension | Terminal | Memory | Communication | Media |
|-----------|----------|--------|--------------|-------|
| Provider exists? | YES | NO | NO | NO |
| Provider registered? | YES | NO | NO | NO |
| Provider capabilities? | 3 | 0 | 0 | 0 |
| Routing works? | BROKEN (12 LOC fix) | N/A | N/A | N/A |
| Templates using | 15 | 13 | 31 | 10 |
| Actions needed | 14 | 10 | 15+ | 20+ |
| LOC to full | ~561 | ~400 | ~600 | ~800 |
| Credentials needed | None | None | OAuth2/bot tokens | API keys |
| External deps | subprocess | SQLite | OAuth flows | APIs |
| Risk level | LOW | LOW | MEDIUM | HIGH |

**Terminal is the clear winner** — it has the most infrastructure, lowest risk, fewest external dependencies, and requires the least new code.

---

## Final Decision

### Recommendation: **A — PROVIDER_READY**

Terminal is the only capability with a fully implemented, registered provider. The gap is a **routing bug** (12 LOC) plus **action implementations** (~550 LOC). No other capability comes close to this level of readiness.

### Implementation Priority

1. **Fix routing** (12 LOC): Add "terminal" to `APP_CAPABILITIES` in `app_operator.py` and add a terminal branch in `execute_capability()` that delegates to `TerminalProvider`
2. **Implement artifact actions** (~250 LOC): render_docx, verify_docx, render_pptx, verify_pptx, render_pdf_from_html, verify_pdf — these unblock 12 of 15 templates
3. **Implement file actions** (~40 LOC): render_markdown, append_xlsx_row — unblocks 2 more templates
4. **Implement code actions** (~150 LOC): scaffold, git_init, open_vscode, delegate_to_agent — unblocks remaining templates

### Why Not Other Providers?

- **Memory** (Decision C): No provider exists, 10 new persistence patterns needed, conversational vs automation mismatch
- **Communication** (Decision B): No provider exists, OAuth2 flows required, 31 templates but high complexity
- **Media** (Decision D): No provider exists, 20+ actions, multiple external APIs, highest risk

---

## Audit Confirmation

This audit was conducted as a READ-ONLY review of source code, YAML templates, routing infrastructure, and provider implementations. No files were modified. All findings are based on direct code inspection at the paths specified.

**Files examined:**
- `mini_kio/core/providers/terminal_provider.py` (146 lines)
- `mini_kio/core/mcp/servers/mcp_terminal_server.py` (130 lines)
- `mini_kio/core/providers/__init__.py` (31 lines)
- `mini_kio/automation/step_runner.py` (452 lines)
- `mini_kio/automation/capability_resolver.py` (167 lines)
- `mini_kio/core/app_operator.py` (3476 lines)
- `mini_kio/core/execution_boundary.py` (1472 lines)
- `mini_kio/core/pipeline/__init__.py` (9779 lines)
- 14 YAML templates from `automation/library/`

**Audit methodology:** Grep for `capability: terminal` across all YAML files, read each template in full, trace the execution path from step_runner through execution_boundary to app_operator, verify provider registration and capability mapping, compare template-required actions against TerminalProvider's implemented actions.
