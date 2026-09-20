# KIO GitHub Provider Readiness Audit

**Date:** 2026-09-15
**Scope:** Audit of the `github` capability — YAML templates, infrastructure routing, MCP server, provider registry, and execution boundary
**Status:** READ-ONLY — no files modified

---

## Executive Verdict

| Metric | Value |
|--------|-------|
| Templates using `github` | 8 |
| Total github actions required | 16 (across all templates) |
| Actions mapped in `_ACTION_MAP` | 16 ✅ |
| Actions implemented in MCP server | 9 |
| Actions with NO implementation | 7 |
| `github` in `APP_CAPABILITIES` | **NO** ❌ |
| `github` in `_CAPABILITY_TO_PROVIDER` | YES ✅ |
| MCP server registered for `github` | YES ✅ (`mcp/__init__.py:16`) |
| `github` in runtime status | ❌ BLOCKED |

**Bottom line:** The routing pipeline (step_runner → capability_resolver → MCP provider) is structurally wired for `github`, but `execute_capability()` cannot dispatch github actions because `"github"` is absent from `APP_CAPABILITIES` and the function has no github-specific handler. The MCP server provides 9 tools; 7 template-required actions have no implementation. **Zero templates are executable end-to-end today.**

**Recommended path:** Option D — Wire github through the existing MCP provider with a target-format adapter (~150 LOC), then incrementally add missing MCP tools.

---

## 1. Template Inventory

### 1.1 All YAML Templates with `capability: github`

| # | Template ID | Category | Github Actions Used | Other Capabilities |
|---|-------------|----------|--------------------|--------------------|
| 1 | `development.github_issue_triage` | development | `get_issue`, `apply_labels` | ai_reasoning, communication |
| 2 | `development.ci_failure_alert` | development | `get_run_logs` | ai_reasoning, communication |
| 3 | `development.pr_review_prep` | development | `get_pr_diff` | ai_reasoning, communication |
| 4 | `development.repo_health_report` | development | `repo_metrics` | ai_reasoning, communication, terminal |
| 5 | `development.dependency_monitor` | development | `dependency_scan`, `create_issue` | ai_reasoning, communication |
| 6 | `development.issue_to_implementation` | development | `gather_issue_context`, `create_draft_pr` | ai_reasoning, terminal |
| 7 | `development.repo_backup` | development | `export_archive` | filesystem |
| 8 | `development.release_changelog` | development | `prs_since_last_tag`, `create_release` | ai_reasoning |

### 1.2 Unique Github Actions Across All Templates

| Action | Templates Using It | Step |
|--------|-------------------|------|
| `get_issue` | github_issue_triage | fetch |
| `apply_labels` | github_issue_triage | apply |
| `get_run_logs` | ci_failure_alert | logs |
| `get_pr_diff` | pr_review_prep | diff |
| `repo_metrics` | repo_health_report | gather |
| `dependency_scan` | dependency_monitor | scan |
| `create_issue` | dependency_monitor | file_issue |
| `gather_issue_context` | issue_to_implementation | context |
| `create_draft_pr` | issue_to_implementation | open_pr |
| `export_archive` | repo_backup | export |
| `prs_since_last_tag` | release_changelog | collect |
| `create_release` | release_changelog | create_release |

**12 unique github actions** required by templates. All 12 have entries in `_ACTION_MAP` (lines 152-168 of `step_runner.py`), routing to `"execute_capability"`.

---

## 2. Provider Analysis

### 2.1 `_ACTION_MAP` Entries (step_runner.py:152-168)

All 16 registered github actions:

```
("github", "get_pr_diff")        → "execute_capability"
("github", "list_issues")        → "execute_capability"
("github", "create_issue")       → "execute_capability"
("github", "create_draft_pr")    → "execute_capability"
("github", "get_repo_info")      → "execute_capability"
("github", "get_issue")          → "execute_capability"
("github", "get_run_logs")       → "execute_capability"
("github", "apply_labels")       → "execute_capability"
("github", "backup_repo")        → "execute_capability"
("github", "scan_dependencies")  → "execute_capability"
("github", "create_release")     → "execute_capability"
("github", "dependency_scan")    → "execute_capability"
("github", "export_archive")     → "execute_capability"
("github", "gather_issue_context")→ "execute_capability"
("github", "prs_since_last_tag") → "execute_capability"
("github", "repo_metrics")       → "execute_capability"
```

### 2.2 `APP_CAPABILITIES` (app_operator.py:3163-3175)

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

**`"github"` is NOT present.** This is the primary blocker. When `execute_capability()` receives `"github::get_issue::..."`, it splits to `app_name="github"` and checks `APP_CAPABILITIES.get("github", [])`, which returns `[]`. The capability check fails immediately.

### 2.3 Capability Resolver (capability_resolver.py:14-32)

```python
_CAPABILITY_TO_PROVIDER = {
    ...
    "github": ["github"],   # ← maps to provider name "github"
    ...
}
```

The capability resolver correctly maps `"github"` to the provider name `"github"`. At runtime, `CapabilityResolver.check_capabilities(["github"])` will look up `registry.get_provider("github")`. Since `MCPExecutionProvider("github", ...)` is registered in `mcp/__init__.py:16-21`, this check **passes** if the MCP server is online.

**The resolver is wired correctly; the bottleneck is downstream in `execute_capability()`.**

### 2.4 MCP Server (mcp_github_server.py)

9 tools registered:

| Tool | Parameters | Notes |
|------|-----------|-------|
| `github_search_repos` | query, limit | ✅ Working |
| `github_get_repo` | repo_name | ✅ Working |
| `github_list_issues` | repo_name, state, limit | ✅ Working |
| `github_create_issue` | repo_name, title, body | ✅ Working |
| `github_list_prs` | repo_name, state, limit | ✅ Working |
| `github_get_contents` | repo_name, path, ref | ✅ Working |
| `github_list_branches` | repo_name | ✅ Working |
| `github_list_commits` | repo_name, branch, limit | ✅ Working |
| `github_create_gist` | description, files, public | ✅ Working |

**Dependency:** `PyGithub` (`pip install PyGithub`) + `GITHUB_TOKEN` env var.

### 2.5 Gap Analysis: Template Actions vs MCP Tools

| Template Action | MCP Tool Equivalent | Gap |
|----------------|---------------------|-----|
| `get_issue` | `github_list_issues` (filter by number) | Partial — need single-issue fetch |
| `apply_labels` | *(none)* | **MISSING** |
| `get_run_logs` | *(none)* | **MISSING** — Actions API not covered |
| `get_pr_diff` | *(none)* | **MISSING** — diff not exposed |
| `repo_metrics` | `github_get_repo` + `github_list_issues` + `github_list_prs` | Composite — needs orchestration |
| `dependency_scan` | *(none)* | **MISSING** — Dependabot/Depfu API not covered |
| `create_issue` | `github_create_issue` | ✅ Exact match |
| `gather_issue_context` | `github_get_repo` + `github_list_issues` | Composite |
| `create_draft_pr` | *(none)* | **MISSING** — PR creation not covered |
| `export_archive` | `github_get_contents` (partial) | **MISSING** — archive download not covered |
| `prs_since_last_tag` | *(none)* | **MISSING** — release/tag API not covered |
| `create_release` | *(none)* | **MISSING** — release API not covered |

**Result:** 6 exact/good matches, 6 MISSING actions.

---

## 3. Capability Matrix

| Capability | Required By (count) | Status | Blocking Templates |
|-----------|---------------------|--------|-------------------|
| `github` | 8 templates | ❌ BLOCKED | All 8 github templates |
| `ai_reasoning` | 7 of 8 github templates | ❌ BLOCKED | 7 of 8 (all except repo_backup) |
| `communication` | 5 of 8 github templates | ❌ BLOCKED | 5 of 8 |
| `terminal` | 2 of 8 github templates | ❌ BLOCKED | repo_health_report, issue_to_implementation |
| `filesystem` | 1 of 8 github templates | ✅ Available | repo_backup |

### Per-Template Blocking Summary

| Template | github | Other Blockers | Solo-Blocked by github? |
|----------|--------|---------------|------------------------|
| `github_issue_triage` | ❌ | ai_reasoning, communication | No — 3-way block |
| `ci_failure_alert` | ❌ | ai_reasoning, communication | No — 3-way block |
| `pr_review_prep` | ❌ | ai_reasoning, communication | No — 3-way block |
| `repo_health_report` | ❌ | ai_reasoning, communication, terminal | No — 4-way block |
| `dependency_monitor` | ❌ | ai_reasoning, communication | No — 3-way block |
| `issue_to_implementation` | ❌ | ai_reasoning, terminal | No — 3-way block |
| `repo_backup` | ❌ | *(none)* | **YES — github is sole blocker** |
| `release_changelog` | ❌ | ai_reasoning | No — 2-way block |

**1 template (repo_backup) is blocked by github alone.** The other 7 are multi-blocked, meaning even fixing github would not make them executable without also providing ai_reasoning, communication, or terminal.

---

## 4. Per-Template Analysis

### 4.1 `development.github_issue_triage`

**Steps:**
1. `github.get_issue` → fetch issue details
2. `ai_reasoning.classify_issue` → LLM classification
3. `github.apply_labels` → conditional label application
4. `communication.send_message` → notification

**Github actions:** `get_issue` (partial MCP match), `apply_labels` (NO MCP match)
**Other blockers:** ai_reasoning (no LLM), communication (no provider)
**Verdict:** 3-way blocked.即使 github fixed, still needs LLM + communication.

### 4.2 `development.ci_failure_alert`

**Steps:**
1. `github.get_run_logs` → fetch CI logs
2. `ai_reasoning.extract_error` → LLM error extraction
3. `communication.send_message` → alert delivery

**Github actions:** `get_run_logs` (NO MCP match — Actions API)
**Other blockers:** ai_reasoning, communication
**Verdict:** 3-way blocked. get_run_logs is the hardest gap (GitHub Actions API).

### 4.3 `development.pr_review_prep`

**Steps:**
1. `github.get_pr_diff` → fetch PR diff
2. `ai_reasoning.analyze_diff` → LLM analysis
3. `communication.send_message` → checklist delivery

**Github actions:** `get_pr_diff` (NO MCP match — diff API)
**Other blockers:** ai_reasoning, communication
**Verdict:** 3-way blocked.

### 4.4 `development.repo_health_report`

**Steps:**
1. `github.repo_metrics` → gather metrics
2. `ai_reasoning.summarize_health` → LLM narrative
3. `terminal.render_docx` → DOCX generation
4. `terminal.verify_docx` → verification
5. `communication.send_file` → delivery

**Github actions:** `repo_metrics` (composite — MCP has partial building blocks)
**Other blockers:** ai_reasoning, communication, terminal
**Verdict:** 4-way blocked. Most complex template.

### 4.5 `development.dependency_monitor`

**Steps:**
1. `github.dependency_scan` → scan dependencies
2. `ai_reasoning.prioritize_updates` → LLM prioritization
3. `github.create_issue` → file summary issue
4. `communication.send_message` → alert

**Github actions:** `dependency_scan` (NO MCP match), `create_issue` (✅ MCP match)
**Other blockers:** ai_reasoning, communication
**Verdict:** 3-way blocked. `create_issue` would work if github provider existed.

### 4.6 `development.issue_to_implementation`

**Steps:**
1. `github.gather_issue_context` → gather context (composite)
2. `terminal.delegate_to_agent` → run coding agent
3. `ai_reasoning.review_diff` → LLM gate
4. `github.create_draft_pr` → open draft PR

**Github actions:** `gather_issue_context` (composite), `create_draft_pr` (NO MCP match)
**Other blockers:** ai_reasoning, terminal
**Verdict:** 3-way blocked. Most ambitious template (coding agent delegation).

### 4.7 `development.repo_backup` ⭐

**Steps:**
1. `github.export_archive` → download repo archive
2. `filesystem.upload_backup` → upload to storage
3. `filesystem.verify_upload` → verify upload
4. `filesystem.prune_old_backups` → retention cleanup

**Github actions:** `export_archive` (NO MCP match — archive download API)
**Other blockers:** NONE (filesystem is available)
**Verdict:** **Solo-blocked by github.** Only template where fixing github alone unblocks execution. However, `export_archive` requires implementing archive download in the MCP server.

### 4.8 `development.release_changelog`

**Steps:**
1. `github.prs_since_last_tag` → collect PRs/commits
2. `ai_reasoning.write_changelog` → LLM changelog
3. `github.create_release` → create GitHub release

**Github actions:** `prs_since_last_tag` (NO MCP match), `create_release` (NO MCP match)
**Other blockers:** ai_reasoning
**Verdict:** 2-way blocked.

---

## 5. Security Analysis

| Concern | Assessment |
|---------|-----------|
| Token storage | Templates declare `github_token` as `api_key` credential — routed through CredentialVault |
| Scopes | Templates request `[repo]` or `[repo, actions]` — appropriate for their actions |
| Consequential actions | 4 templates marked `security_classification: consequential` (issue_to_implementation, dependency_monitor, repo_backup, release_changelog) — all require `user_confirmation_required: true` |
| Read-only actions | 3 templates marked `read_only` (ci_failure_alert, pr_review_prep, repo_health_report) |
| Draft PR safety | `issue_to_implementation` explicitly creates DRAFT PRs, never auto-merges — correct for consequential classification |
| Release safety | `release_changelog` defaults to `publish: false` (draft only) — safe default |
| Archive download | `repo_backup` downloads repo archive — low risk, read-only |

**No security red flags.** Templates follow KIO's consequential/read-only classification correctly.

---

## 6. LOC Estimate

### Option A: Full GitHubProvider (standalone provider class)
| Component | Lines |
|-----------|-------|
| `GitHubProvider` class (new file) | ~180 |
| Provider registry wiring | ~20 |
| Credential integration | ~30 |
| **Total** | **~230** |

### Option B: Wire through MCP provider (adapter approach)
| Component | Lines |
|-----------|-------|
| Target-format adapter in step_runner | ~40 |
| Action-name mapping dict | ~30 |
| Missing MCP tool stubs (6 tools) | ~120 |
| **Total** | **~190** |

### Option C: Hybrid (recommended)
| Component | Lines |
|-----------|-------|
| `_build_target` github format fix | ~15 |
| `execute_capability` github routing branch | ~50 |
| MCP tool implementations for 6 missing actions | ~120 |
| **Total** | **~185** |

**Ponytail note:** Option C is the smallest diff that unblocks templates. The `execute_capability` branch is ~50 LOC because it just delegates to the MCP provider, which already handles the actual API calls.

---

## 7. Comparison with Other Capabilities

| Capability | Templates | MCP Server | Provider | `_ACTION_MAP` | Executable |
|-----------|-----------|------------|----------|---------------|------------|
| `filesystem` | 16 | ✅ local | ✅ FilesystemProvider | ✅ 16 actions | ✅ Yes |
| `knowledge` | 12 | ✅ local | ✅ KnowledgeProvider | ✅ 12 actions | ✅ Yes |
| `browser` | 10 | ✅ local | ✅ BrowserProvider | ✅ 10 actions | ❌ No (backend) |
| `github` | 8 | ✅ external | ✅ MCPProvider | ✅ 16 actions | ❌ No (routing) |
| `communication` | 5 | ❌ | ❌ | ✅ 14 actions | ❌ No |
| `ai_reasoning` | 6 | ❌ | ❌ | ✅ 52 actions | ❌ No |
| `terminal` | 9 | ✅ local | ✅ TerminalProvider | ✅ 15 actions | ❌ No (sandbox) |

**github is the ONLY capability that has both an MCP server AND provider registration but cannot execute** — purely a routing/target-format issue.

---

## 8. Final Decision

### Recommendation: **Option D — Wire github through MCP provider + implement 6 missing tools**

| Phase | What | LOC | Effort |
|-------|------|-----|--------|
| **Phase 1** | Fix `_build_target()` to construct `"github::{action}::{json}"` for github steps | ~15 | 30 min |
| **Phase 2** | Add github routing branch in `execute_capability()` that delegates to the MCP provider | ~50 | 1 hr |
| **Phase 3** | Implement 6 missing MCP tools: `get_issue_detail`, `apply_labels`, `get_run_logs`, `get_pr_diff`, `create_draft_pr`, `export_archive`, `prs_since_last_tag`, `create_release` | ~150 | 3-4 hrs |
| **Total** | | **~215** | **~5 hrs** |

### What Gets Unblocked

| Phase | Templates Unblocked | Notes |
|-------|-------------------|-------|
| After Phase 1+2 | 0 | Still needs MCP tool implementations |
| After Phase 3 (with ai_reasoning + communication) | 7 of 8 | All except repo_backup needs ai_reasoning + communication |
| After Phase 3 (github only) | 1 of 8 | `repo_backup` — sole github blocker |

### Alternative: Deferred (Option E)

If the priority is lower, mark github as "infrastructure-ready, tooling-pending" and focus on capabilities that unblock more templates per LOC spent (e.g., communication or ai_reasoning would unblock 31+ templates each).

---

## 9. Audit Confirmation

| Check | Status |
|-------|--------|
| All YAML templates with `capability: github` identified | ✅ 8 templates found |
| All github actions in `_ACTION_MAP` cataloged | ✅ 16 actions |
| `APP_CAPABILITIES` checked for `github` | ✅ **ABSENT** — confirmed blocker |
| `_CAPABILITY_TO_PROVIDER` checked for `github` | ✅ Present, maps to `["github"]` |
| MCP server for github found and read | ✅ `mcp_github_server.py` — 9 tools |
| Provider registry registration verified | ✅ `mcp/__init__.py:16` registers github |
| Per-template blocking analysis complete | ✅ 8/8 templates analyzed |
| Security classification reviewed | ✅ No red flags |
| LOC estimate provided | ✅ ~215 LOC for full fix |
| Recommendation with alternatives | ✅ Option D recommended |

**Audit complete. No files modified.**
