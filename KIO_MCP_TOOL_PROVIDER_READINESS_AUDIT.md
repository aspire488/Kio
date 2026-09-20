# KIO mcp_tool Provider Readiness Audit

**Date:** 2026-09-15
**Auditor:** opencode (read-only)
**Scope:** All YAML templates using `capability: mcp_tool` and the runtime infrastructure that must execute them.

---

## 1. Executive Verdict

**Rating: D — Partial skeleton exists; templates are BLOCKED at routing, not just at runtime.**

The `mcp_tool` capability is **declared** throughout the YAML library (7 templates, 10 step-level usages) and **registered** in the capability resolver, step runner action map, and status checker. However, all `mcp_tool` steps fail at the routing layer before any provider is reached. The routing gap is structural: `app_operator.execute_capability()` (the handler all mcp_tool steps are dispatched to) does not recognize `"mcp_tool"` as a valid app name in `APP_CAPABILITIES`, so every mcp_tool step returns `"mcp_tool does not support '<action>'"` immediately.

There is no standalone `mcp_tool` provider in the ProviderRegistry, no MCP server registered for Notion/Airtable/Linear/HubSpot/Salesforce/Todoist/Google Tasks, and the step runner's `_call_boundary` never calls the existing `execute_mcp_tool()` function that *would* work if invoked directly.

**Bottom line:** 0 of 7 templates can execute. 10 of 10 mcp_tool steps are dead on arrival.

---

## 2. Template Inventory

### Templates declaring `capability: mcp_tool`

| # | Template ID | File | Category | mcp_tool Steps | Actions Used | Other Capabilities |
|---|-------------|------|----------|----------------|-------------|-------------------|
| 1 | `data.knowledge_base_sync` | `library/data/knowledge_base_sync.yaml` | data | 2 | `create_page`, `get_page` | ai_reasoning |
| 2 | `business.support_ticket_triage` | `library/business/support_ticket_triage.yaml` | business | 1 | `upsert_ticket` | ai_reasoning, communication |
| 3 | `data.record_sync` | `library/data/record_sync.yaml` | data | 2 | `list_changed`, `upsert` | memory |
| 4 | `business.lead_intake_crm` | `library/business/lead_intake_crm.yaml` | business | 2 | `crm_upsert`, `crm_get` | ai_reasoning, knowledge, communication |
| 5 | `business.crm_followup` | `library/business/crm_followup.yaml` | business | 1 | `find_stale_leads` | ai_reasoning, communication, memory |
| 6 | `productivity.email_to_task` | `library/productivity/email_to_task.yaml` | productivity | 1 | `create_task` | ai_reasoning |
| 7 | `productivity.morning_briefing` | `library/productivity/morning_briefing.yaml` | productivity | 1 | `due_tasks` | ai_reasoning, knowledge, communication |

**Total mcp_tool steps across all templates: 10**
**Unique mcp_tool actions: 10** (`create_page`, `get_page`, `upsert_ticket`, `list_changed`, `upsert`, `crm_upsert`, `crm_get`, `find_stale_leads`, `create_task`, `due_tasks`)

### MCP Servers Required per Template

| Template | mcp_servers_required |
|----------|---------------------|
| knowledge_base_sync | notion, airtable |
| support_ticket_triage | linear |
| record_sync | notion, airtable |
| lead_intake_crm | airtable |
| crm_followup | airtable |
| email_to_task | filesystem |
| morning_briefing | filesystem |

---

## 3. Provider Analysis

### 3.1 Step Runner Action Map (`step_runner.py:243-253`)

All 10 mcp_tool actions are mapped to `"execute_capability"`:

```python
("mcp_tool", "call"): "execute_capability",
("mcp_tool", "create_page"): "execute_capability",
("mcp_tool", "create_task"): "execute_capability",
("mcp_tool", "crm_get"): "execute_capability",
("mcp_tool", "crm_upsert"): "execute_capability",
("mcp_tool", "due_tasks"): "execute_capability",
("mcp_tool", "find_stale_leads"): "execute_capability",
("mcp_tool", "get_page"): "execute_capability",
("mcp_tool", "list_changed"): "execute_capability",
("mcp_tool", "upsert"): "execute_capability",
("mcp_tool", "upsert_ticket"): "execute_capability",
```

The target is built as: `f"mcp_tool::{step_action}::{json.dumps(inputs)}"`

### 3.2 Routing Gap: `app_operator.execute_capability()`

The `execute_capability` handler in `app_operator.py:3177-3476` splits the target on `::`, extracts `app_name = "mcp_tool"` and `cap = "create_page"` (etc.), then looks up:

```python
caps = APP_CAPABILITIES.get(app_name, [])
if cap not in caps:
    return {"success": False, "message": f"{app_name} does not support '{cap}'."}
```

**`APP_CAPABILITIES` (`app_operator.py:3163-3175`) does not contain `"mcp_tool"`.** It only defines: chrome, edge, firefox, brave, comet, spotify, vlc, youtube, vscode, telegram, capcut.

**Result:** Every mcp_tool step returns `"mcp_tool does not support '<action>'"` immediately. The error is structural, not runtime.

### 3.3 Capability Resolver (`capability_resolver.py:26`)

```python
"mcp_tool": ["mcp_tool"],
```

Maps to provider name `"mcp_tool"`. The resolver checks if a provider named `"mcp_tool"` exists in `ProviderRegistry`. No such provider is registered — the MCP providers are registered under names like `"mcp_filesystem"`, `"mcp_git"`, etc. (prefixed with `mcp_`), but not as bare `"mcp_tool"`.

**Blocking reason:** `"MCP server not connected"` (`capability_resolver.py:107`)

### 3.4 Status Checker (`status.py:150-157`)

```python
def _check_mcp(self) -> dict[str, Any]:
    try:
        from mini_kio.core.config import MCP_RUNTIME_ENABLED
        if MCP_RUNTIME_ENABLED:
            return {"available": True, "reason": "MCP runtime enabled"}
    except Exception:
        pass
    return {"available": False, "reason": "MCP runtime not enabled"}
```

This only checks if `MCP_RUNTIME_ENABLED` is truthy. It does NOT verify that specific MCP servers (notion, airtable, linear, etc.) are connected. Even with the flag enabled, the specific servers needed by templates are not registered.

### 3.5 Existing MCP Infrastructure

| Component | File | Status |
|-----------|------|--------|
| MCPClient (JSON-RPC stdio) | `core/mcp/client.py` | ✅ Implemented |
| MCPServerRegistry | `core/mcp/registry.py` | ✅ Implemented |
| MCPExecutionProvider | `core/mcp/provider.py` | ✅ Implemented |
| register_all_mcp_servers() | `core/mcp/__init__.py` | ✅ Implemented |
| execute_mcp_tool() | `core/execution_boundary.py:1445-1467` | ✅ Implemented (unused by step runner) |
| Local MCP servers | `core/mcp/servers/` | filesystem, git, terminal, sqlite, docker, github, postgres, redis |
| External MCP servers | Notion, Airtable, Linear, HubSpot, etc. | ❌ **Not implemented** |

### 3.6 Available MCP Servers (from `mcp/servers/__init__.py`)

```
filesystem, git, terminal, sqlite, docker, github, postgres, redis
```

**None of the servers required by the YAML templates are available:**
- ❌ `notion` — not implemented
- ❌ `airtable` — not implemented
- ❌ `linear` — not implemented
- ❌ `hubspot` — not implemented
- ❌ `salesforce` — not implemented
- ❌ `todoist` — not implemented
- ❌ `google_tasks` — not implemented

The `email_to_task.yaml` and `morning_briefing.yaml` templates require `filesystem` MCP server (which IS available), but the specific mcp_tool actions they use (`create_task`, `due_tasks`) are not tools exposed by the filesystem MCP server.

---

## 4. Capability Matrix

| Capability | Provider | Availability | Blocks Templates |
|------------|----------|-------------|-----------------|
| `mcp_tool` | None registered | ❌ Never available | All 7 templates |
| `ai_reasoning` | LLM provider | ⚠️ Depends on config | 5 templates |
| `communication` | Telegram/Discord/Slack | ⚠️ Depends on config | 4 templates |
| `knowledge` | Knowledge/memory | ⚠️ Partial | 2 templates |
| `memory` | In-memory store | ✅ Always available | 3 templates |
| `calendar` | Calendar provider | ❌ Not implemented | 1 template |
| `filesystem` (MCP) | MCP filesystem server | ✅ Available | 2 templates (server available, actions not) |

---

## 5. Per-Template Analysis

### 5.1 `data.knowledge_base_sync` (NOTION/AIRTABLE KB ENTRY)

**mcp_tool steps:** `create_page` (step `create`), `get_page` (step `verify`)
**Required MCP servers:** notion, airtable
**Other blocking capabilities:** ai_reasoning (LLM-dependent)

**Routing outcome:** `app_operator.execute_capability` → `"mcp_tool does not support 'create_page'"` → BLOCKED
**Provider check:** No `"mcp_tool"` provider in registry → BLOCKED

**Verdict:** FULLY BLOCKED by mcp_tool alone. The first non-ai_reasoning step is step 2 (`create`), which is mcp_tool. Even if LLM works, template dies at step 2.

### 5.2 `business.support_ticket_triage` (SUPPORT TICKETING)

**mcp_tool step:** `upsert_ticket` (step `ticket`)
**Required MCP servers:** linear
**Other blocking capabilities:** ai_reasoning, communication

**Routing outcome:** BLOCKED (same routing gap)
**Additional blockers:** ai_reasoning (LLM), communication (Slack/Telegram)

**Verdict:** FULLY BLOCKED by mcp_tool. Step 2 (`ticket`) is the first mcp_tool step; it runs after step 1 (`classify`, ai_reasoning). Even with LLM working, step 2 fails.

### 5.3 `data.record_sync` (TWO-SYSTEM RECORD SYNC)

**mcp_tool steps:** `list_changed` (step `read_a`), `upsert` (step `write_b`)
**Required MCP servers:** notion, airtable
**Other blocking capabilities:** memory (always available)

**Routing outcome:** BLOCKED
**Note:** Step 1 (`read_a`) is mcp_tool — template fails at the very first step.

**Verdict:** FULLY BLOCKED by mcp_tool. The first step is mcp_tool; the template cannot even start data sync.

### 5.4 `business.lead_intake_crm` (LEAD INTAKE → CRM)

**mcp_tool steps:** `crm_upsert` (step `upsert`), `crm_get` (step `verify`)
**Required MCP servers:** airtable
**Other blocking capabilities:** ai_reasoning, knowledge, communication

**Routing outcome:** BLOCKED
**Note:** Steps 1-2 are knowledge + ai_reasoning; mcp_tool starts at step 3. Template could partially execute steps 1-2 but dies at step 3.

**Verdict:** FULLY BLOCKED by mcp_tool. Partial progress possible (validate, dedupe/score), but no CRM write occurs.

### 5.5 `business.crm_followup` (STALE LEAD FOLLOW-UP)

**mcp_tool step:** `find_stale_leads` (step `find`)
**Required MCP servers:** airtable
**Other blocking capabilities:** ai_reasoning, communication, memory

**Routing outcome:** BLOCKED
**Note:** Step 1 (`find`) is mcp_tool — template fails at the very first step.

**Verdict:** FULLY BLOCKED by mcp_tool. Template cannot even discover stale leads.

### 5.6 `productivity.email_to_task` (EMAIL → TASK)

**mcp_tool step:** `create_task` (step `add`)
**Required MCP servers:** filesystem (listed, but `create_task` is not a filesystem tool)
**Other blocking capabilities:** ai_reasoning

**Routing outcome:** BLOCKED
**Note:** Step 1 (`classify`) is ai_reasoning; step 2 (`add`) is mcp_tool. Partial progress possible (classify email), but task creation fails.

**Verdict:** FULLY BLOCKED by mcp_tool. Classification works; task creation does not.

### 5.7 `productivity.morning_briefing` (MORNING BRIEF)

**mcp_tool step:** `due_tasks` (step `tasks`)
**Required MCP servers:** filesystem (listed, but `due_tasks` is not a filesystem tool)
**Other blocking capabilities:** ai_reasoning, knowledge, communication

**Routing outcome:** BLOCKED
**Note:** Step 1 (`cal`, calendar) and step 3 (`weather`, knowledge) are not mcp_tool. Step 2 (`tasks`) is mcp_tool. Template could partially execute calendar + weather + compose but tasks section would be empty/failed.

**Verdict:** PARTIALLY BLOCKED by mcp_tool. Calendar, weather, and composition could work, but the tasks component fails. Briefing would be incomplete.

---

## 6. Security Analysis

| Risk | Status | Notes |
|------|--------|-------|
| Unregistered server execution | N/A | No mcp_tool server is reachable |
| Credential exposure | N/A | Templates declare `credentials_required` but no MCP credential flow exists |
| Permission escalation | LOW | `execute_mcp_tool()` in execution_boundary.py accepts `server_id` parameter, but is never called from step_runner |
| Idempotency keys | ✅ Present | All 7 templates declare idempotency keys |
| Consequential classification | ✅ Present | 6 of 7 templates are `security_classification: consequential` with `user_confirmation_required: true` |

---

## 7. LOC Estimate for Provider Implementation

| Component | Description | Est. LOC | Complexity |
|-----------|-------------|----------|------------|
| `mcp_notion_server.py` | Notion MCP server (JSON-RPC stdio) | 300-400 | High |
| `mcp_airtable_server.py` | Airtable MCP server | 250-350 | High |
| `mcp_linear_server.py` | Linear MCP server | 200-300 | Medium |
| `mcp_hubspot_server.py` | HubSpot CRM MCP server | 250-350 | High |
| `mcp_todoist_server.py` | Todoist task MCP server | 150-200 | Medium |
| `mcp_google_tasks_server.py` | Google Tasks MCP server | 200-300 | High |
| `app_operator.py` routing fix | Add `"mcp_tool"` to `APP_CAPABILITIES` or bypass it | 30-50 | Low |
| `step_runner.py` routing fix | Route mcp_tool actions to `execute_mcp_tool()` instead of `execute_capability` | 40-60 | Low |
| `capability_resolver.py` fix | Register MCP servers as `"mcp_tool"` provider | 20-30 | Low |
| **Total** | | **1,240-1,740** | |

### Minimal Viable Fix (Routing Only, No New Servers)

To make the *existing* MCP infrastructure work for the step_runner path:

1. **`app_operator.py`**: Add `"mcp_tool": ["create_page", "get_page", "upsert_ticket", ...]` to `APP_CAPABILITIES`, and route those calls to `execute_mcp_tool()` from `execution_boundary.py`. **~40 LOC.**

2. **`step_runner.py`**: Alternative — change the `_call_boundary` method to route `(mcp_tool, *)` actions directly to `execute_mcp_tool()` instead of `execute_capability`. **~20 LOC.**

3. **`mcp/servers/__init__.py`**: Register stub servers for notion, airtable, linear, etc. (even if just returning "not implemented"). **~100 LOC.**

**Minimum viable routing fix: ~160 LOC** (makes the plumbing work, but actual Notion/Airtable/Linear integration requires 1,000+ more LOC for the real MCP server implementations).

---

## 8. Comparison with Other Capabilities

| Capability | Routing Path | Provider Exists | Templates Functional |
|------------|-------------|-----------------|---------------------|
| `ai_reasoning` | execute_capability → ProviderRegistry (LLM) | ✅ Yes | ~40 templates |
| `browser` | Direct boundary actions (browser_goto, etc.) | ✅ Yes | ~15 templates |
| `filesystem` | Direct boundary actions (write_csv, etc.) | ✅ Yes | ~20 templates |
| `communication` | execute_capability → ProviderRegistry | ✅ Yes | ~10 templates |
| `github` | execute_capability → ProviderRegistry | ✅ Yes | ~5 templates |
| `knowledge` | Dedicated boundary actions (web_search, etc.) | ✅ Yes | ~8 templates |
| `memory` | Always available (in-memory) | ✅ Yes | ~12 templates |
| `calendar` | execute_capability → ProviderRegistry | ❌ No | 1 template |
| `email` | execute_capability → ProviderRegistry | ⚠️ Partial | 2 templates |
| **`mcp_tool`** | **execute_capability → APP_CAPABILITIES (broken)** | **❌ No** | **0 templates** |

---

## 9. Final Decision

### Recommendation: **D — Routing skeleton exists but is structurally broken; no MCP server implementations for required services.**

**Rationale:**
- The YAML templates are well-designed and use `mcp_tool` consistently for external service integration (CRM, ticketing, knowledge bases, task stores).
- The step runner action map correctly registers all 10 mcp_tool actions.
- The capability resolver and status checker include mcp_tool awareness.
- **However**, the routing is fundamentally broken: `app_operator.execute_capability()` does not recognize `"mcp_tool"` as a valid app name, so all mcp_tool steps fail at the routing layer before any provider is reached.
- Even if routing were fixed, no MCP server implementations exist for Notion, Airtable, Linear, HubSpot, Salesforce, Todoist, or Google Tasks.
- The existing MCP servers (filesystem, git, terminal, sqlite) do not expose the tools needed by these templates.
- The 7 blocked templates represent 10 unique mcp_tool actions across data sync, CRM, ticketing, task management, and knowledge management use cases.

### What Would Move This to A/B/C

| Rating | Condition |
|--------|-----------|
| **C** | Fix the routing gap (add `mcp_tool` to `APP_CAPABILITIES` or bypass it), register Notion + Airtable MCP servers with real implementations. ~1,500 LOC. |
| **B** | Above + Linear + HubSpot + Todoist + Google Tasks servers, with credential management and error handling. ~2,500 LOC. |
| **A** | Above + full test coverage, runtime proven status for all 7 templates, security audit of MCP server permissions. ~3,500 LOC. |

---

## 10. Audit Confirmation

| Item | Status |
|------|--------|
| All YAML templates with `capability: mcp_tool` found | ✅ 7 templates, 10 steps |
| All `_ACTION_MAP` entries for mcp_tool found | ✅ 11 entries (line 243-253) |
| APP_CAPABILITIES checked for mcp_tool | ✅ Not present (confirmed gap) |
| capability_resolver mapping checked | ✅ Maps to `["mcp_tool"]` (no provider) |
| status.py _check_mcp checked | ✅ Only checks MCP_RUNTIME_ENABLED flag |
| MCP server implementations inventoried | ✅ 8 servers, none match template requirements |
| execute_mcp_tool() existence confirmed | ✅ Exists in execution_boundary.py (unused by step runner) |
| Routing gap identified and confirmed | ✅ app_operator.execute_capability() rejects "mcp_tool" |
| Per-template blocking analysis complete | ✅ 6 fully blocked, 1 partially blocked |
| Security classification reviewed | ✅ All consequential except morning_briefing |
| LOC estimate provided | ✅ 160 LOC minimum fix, 1,240-1,740 for full implementation |

---

*Audit completed 2026-09-15. Read-only; no files modified.*
