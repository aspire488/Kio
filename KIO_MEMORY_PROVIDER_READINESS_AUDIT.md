# KIO Memory Provider Readiness Audit

**Audit Date:** 2026-09-15
**Audit Type:** SOURCE-VERIFIED, READ-ONLY
**Scope:** All 13 YAML templates using `capability: memory`
**Code Root:** `C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final`
**Library Root:** `C:\Users\joelj\Downloads\kio_final\automation\library\`

---

## Executive Verdict

**Decision: C — DEFER_MEMORY**

Memory is NOT the correct next provider implementation. While 13 templates declare `memory`, the actual semantic surface is far narrower than the template count suggests. The existing KIO memory infrastructure (MemoryStore, MemoryResolver) is designed for **conversational memory** (message history + facts), NOT for **automation memory** (snapshots, deduplication, state tracking, activity aggregation). Of 13 templates, only 2 can work with the existing infrastructure. The remaining 11 require entirely new persistence patterns that don't exist yet.

**Recommended next target:** `communication` capability — 31 templates depend on it, most common blocker, and only needs an `APP_CAPABILITIES` entry + message handler.

---

## Memory Templates

### All 13 Templates Declaring `capability: memory`

| # | Template ID | Memory Actions | Inputs | Outputs | Other Capabilities |
|---|-------------|---------------|--------|---------|-------------------|
| 1 | browser.page_change_monitor | diff_against_last | key, snapshot, min_pct | changed, change_pct, diff_text | ai_reasoning, browser, communication |
| 2 | browser.price_monitor | record_and_compare | key, value, target, drop_pct | triggered, previous, history | browser, communication |
| 3 | business.crm_followup | exclude_recently_contacted | leads | eligible | ai_reasoning, communication, mcp_tool |
| 4 | communication.chat_assistant | load_conversation, save_turn | user, message, reply | history, saved | ai_reasoning, communication |
| 5 | data.api_poll_to_store | filter_new | key, items | new_items | knowledge, filesystem |
| 6 | data.record_sync | apply_field_map | changes, field_map | mapped, conflicts | mcp_tool |
| 7 | monitoring.rss_news_monitor | filter_new | key, items, topics | new_items | ai_reasoning, knowledge, communication |
| 8 | monitoring.website_uptime | state_transition | key, status, ms, marker_ok, slow_ms | changed, new_state | knowledge, communication |
| 9 | productivity.meeting_prep | gather_context | attendees | history, related_mail, last_actions | ai_reasoning, communication |
| 10 | productivity.weekly_review | week_activity | window_days | completed, time_spent, highlights | ai_reasoning, communication, terminal |
| 11 | research.competitor_monitor | diff_snapshots | key, snapshots | changes | ai_reasoning, browser, communication, terminal |
| 12 | research.daily_brief | filter_new | key, items | fresh | ai_reasoning, communication |
| 13 | research.youtube_summary | filter_new | key, items | new_videos | ai_reasoning, knowledge, communication |

### Distinct Memory Actions Used

| Action | Templates Using | Semantic Pattern |
|--------|----------------|-----------------|
| filter_new | 4 | Deduplicate items by key, return only new |
| diff_against_last | 1 | Store snapshot, compare to previous, return diff |
| diff_snapshots | 1 | Store multiple snapshots, compare to previous |
| record_and_compare | 1 | Record value, compare to threshold, return triggered |
| state_transition | 1 | Track state changes, alert on transitions |
| exclude_recently_contacted | 1 | Filter by recent contact history |
| apply_field_map | 1 | Apply field mapping with conflict detection |
| load_conversation | 1 | Load conversation history for a user |
| save_turn | 1 | Save a conversation turn |
| gather_context | 1 | Gather attendee context from history |
| week_activity | 1 | Aggregate weekly activity |

---

## Existing KIO Memory Infrastructure

### MemoryStore — `memory/memory_store.py`

```python
class MemoryStore:
    def append(self, role: str, message: str) -> None
    def get_history(self) -> list[MemoryEntry]
    def last_n_messages(self, n: int) -> list[MemoryEntry]
    def first_user_message(self) -> Optional[str]
    def set_fact(self, key: str, value: str) -> None
    def get_fact(self, key: str) -> Optional[str]
    def get_all_facts(self) -> dict[str, str]
    def delete_fact(self, key: str) -> None
    def clear(self) -> None
    def count(self) -> int
    def summarize_session(self) -> str
```

**Storage:** SQLite via MemoryRepository + FactRepository
**Scope:** Session-scoped (session_id)
**Pattern:** Conversational memory (message history + key-value facts)

### MemoryResolver — `resolvers/memory_resolver.py`

Handles conversational memory queries:
- Semantic recall (topic search)
- Topic continuity (what were we discussing?)
- Fact retrieval (what's my favorite X?)
- Conversation history (first message, N messages ago, summarize)

### ContextManager — `core/context_manager.py`

Session management with memory access:
- `memory` property returns MemoryStore
- `append_message(role, content)` delegates to MemoryStore
- `get_all_facts()` delegates to FactRepository

### LivingModel — `memory/living_model.py`

Personal context, facts, preferences:
- `recall_about_topic(session_id, topic)` - search exchange history
- `personal_brief(session_id)` - personal context for LLM
- `seed_current_facts(session_id)` - seed facts from memory

### IntelligenceV2 — `memory/intelligence_v2.py`

Intelligence layer for memory analysis.

### ArchiveMiner — `memory/archive_miner.py`

Historical import from external sources.

### What the Existing Memory CAN Do
- Store and retrieve conversation messages (append, get_history, last_n_messages)
- Store and retrieve key-value facts (set_fact, get_fact, get_all_facts)
- Session-scoped isolation (session_id)
- SQLite persistence (durable across restarts)
- Deterministic fact extraction from user input (PatternMemoryExtractor)
- Conversational recall (semantic_recall, topic_continuity, fact_retrieval)

### What the Existing Memory CANNOT Do
- Store and compare snapshots (diff_against_last, diff_snapshots)
- Track value history and detect threshold crossings (record_and_compare)
- Track state changes and detect transitions (state_transition)
- Deduplicate items by key (filter_new)
- Filter by recent contact history (exclude_recently_contacted)
- Apply field mappings with conflict detection (apply_field_map)
- Gather multi-source context (gather_context)
- Aggregate activity over time windows (week_activity)
- Cross-session persistence (all memory is session-scoped)
- Named key storage (not session_id scoped)

---

## Memory Action Compatibility Matrix

| Memory Action | Templates | Can Existing Memory Do It? | Needs | Classification |
|--------------|-----------|---------------------------|-------|----------------|
| filter_new | 4 | No — no item deduplication | Named key storage + item tracking | PROVIDER_REQUIRED |
| diff_against_last | 1 | No — no snapshot storage | Snapshot storage + comparison | PROVIDER_REQUIRED |
| diff_snapshots | 1 | No — no multi-snapshot storage | Multi-snapshot storage + comparison | PROVIDER_REQUIRED |
| record_and_compare | 1 | No — no value history | Value history + threshold detection | PROVIDER_REQUIRED |
| state_transition | 1 | No — no state tracking | State storage + transition detection | PROVIDER_REQUIRED |
| exclude_recently_contacted | 1 | No — no contact history | Contact history + time-based filtering | PROVIDER_REQUIRED |
| apply_field_map | 1 | No — no field mapping | Field mapping + conflict detection | PROVIDER_REQUIRED |
| load_conversation | 1 | Yes — MemoryStore has get_history | None | DIRECTLY_SUPPORTED |
| save_turn | 1 | Yes — MemoryStore has append | None | DIRECTLY_SUPPORTED |
| gather_context | 1 | No — no multi-source context | Attendee context assembly | PROVIDER_REQUIRED |
| week_activity | 1 | No — no activity aggregation | Activity tracking + time windows | PROVIDER_REQUIRED |

### Summary

| Classification | Count | Actions |
|---------------|-------|---------|
| DIRECTLY_SUPPORTED | 2 | load_conversation, save_turn |
| ADAPTER_REQUIRED | 0 | (none) |
| PROVIDER_REQUIRED | 9 | filter_new, diff_against_last, diff_snapshots, record_and_compare, state_transition, exclude_recently_contacted, apply_field_map, gather_context, week_activity |
| EXTERNAL_INFRASTRUCTURE_REQUIRED | 0 | (none) |
| SEMANTICALLY_UNSUPPORTED | 0 | (none) |

---

## Per-Template Semantic Analysis

### Templates Where ALL Memory Actions Are DIRECTLY_SUPPORTED (1 template)

| Template ID | Memory Actions | Other Blocking Capabilities |
|-------------|---------------|---------------------------|
| communication.chat_assistant | load_conversation, save_turn | ai_reasoning, communication |

**NOT fully executable** — depends on ai_reasoning and communication.

### Templates Requiring PROVIDER (12 templates)

| Template ID | Memory Actions Needing Provider |
|-------------|-------------------------------|
| browser.page_change_monitor | diff_against_last |
| browser.price_monitor | record_and_compare |
| business.crm_followup | exclude_recently_contacted |
| data.api_poll_to_store | filter_new |
| data.record_sync | apply_field_map |
| monitoring.rss_news_monitor | filter_new |
| monitoring.website_uptime | state_transition |
| productivity.meeting_prep | gather_context |
| productivity.weekly_review | week_activity |
| research.competitor_monitor | diff_snapshots |
| research.daily_brief | filter_new |
| research.youtube_summary | filter_new |

---

## Existing Memory vs Template Contract

### Action-by-Action Contract Comparison

| Action | YAML Contract | Existing KIO Memory | Gap |
|--------|--------------|---------------------|-----|
| filter_new | Input: key, items → Output: new_items | No item deduplication | Need named key storage + seen-item tracking |
| diff_against_last | Input: key, snapshot, min_pct → Output: changed, change_pct, diff_text | No snapshot storage | Need snapshot storage + comparison logic |
| diff_snapshots | Input: key, snapshots → Output: changes | No multi-snapshot storage | Need multi-snapshot storage + diff logic |
| record_and_compare | Input: key, value, target, drop_pct → Output: triggered, previous, history | No value history | Need value history + threshold detection |
| state_transition | Input: key, status, ms, marker_ok, slow_ms → Output: changed, new_state | No state tracking | Need state storage + transition detection |
| exclude_recently_contacted | Input: leads → Output: eligible | No contact history | Need contact history + time-based filtering |
| apply_field_map | Input: changes, field_map → Output: mapped, conflicts | No field mapping | Need field mapping + conflict detection |
| load_conversation | Input: user → Output: history | MemoryStore.get_history() | **MATCH** |
| save_turn | Input: user, message, reply → Output: saved | MemoryStore.append() | **PARTIAL MATCH** — save_turn needs structured turn, append takes role+message |
| gather_context | Input: attendees → Output: history, related_mail, last_actions | No multi-source context | Need attendee context assembly |
| week_activity | Input: window_days → Output: completed, time_spent, highlights | No activity aggregation | Need activity tracking + time windows |

### Key Contract Mismatches

1. **Session-scoped vs Named-key**: All existing memory is session-scoped. Templates need named keys (e.g., URL, endpoint) that persist across sessions.

2. **Message history vs Structured state**: Existing memory stores messages. Templates need structured state (snapshots, values, states, seen-items).

3. **No time-based operations**: Existing memory has no time-based filtering, aggregation, or transition detection.

4. **No comparison logic**: Existing memory stores but doesn't compare (no diff, no threshold, no transition).

---

## Security / Privacy Analysis

### Secret Persistence
- **Low risk.** Memory actions don't handle credentials. Templates declare `credentials_required` but memory steps don't use them.

### Credential Leakage
- **Low risk.** MemoryStore doesn't expose credentials. Facts are key-value pairs without sensitive data.

### Cross-User/Session Leakage
- **Medium risk.** Current memory is session-scoped, which is good. But automation templates may need cross-session persistence (e.g., "seen items" across runs). Need to ensure proper scoping.

### Unauthorized Retrieval
- **Low risk.** MemoryStore is accessed via session_id. No cross-session access.

### Deletion Guarantees
- **Low risk.** MemoryStore has `clear()` and `delete_fact()`. But automation state (snapshots, seen-items) has no deletion mechanism.

### Forget Semantics
- **Low risk.** Conversational memory has forget (clear session). Automation state has no forget.

### Provenance
- **Low risk.** MemoryStore tracks timestamps. But automation state has no provenance tracking.

### Retention/Pruning
- **Medium risk.** Automation state (snapshots, seen-items) could grow unbounded. No pruning mechanism exists.

### Sensitive Data Handling
- **Medium risk.** Templates process external data (emails, tickets, web content). Memory could store sensitive data without classification.

### Auditability
- **Low risk.** MemoryStore has basic logging. But automation state changes are not auditable.

### Existing KIO Mechanisms That Can Enforce
- Session-scoped isolation (session_id)
- SQLite persistence (durable, queryable)
- PatternMemoryExtractor (ownership validation)
- Basic logging

---

## Resource Analysis

### Storage Footprint
- Current: ~17 MB RSS (conversation memory + facts)
- Adding automation state: ~5-20 MB per template (snapshots, seen-items, value history)
- **Total impact:** ~20-50 MB, well under 650 MB cap

### RAM Impact
- In-memory caches for automation state: ~5-10 MB
- **Total impact:** Minimal

### Indexing Impact
- SQLite indexes for named keys: ~1-2 MB
- **Total impact:** Minimal

### Retrieval Cost
- SQLite queries for named keys: <1ms
- **Total impact:** Minimal

### Pruning Cost
- Need to implement pruning for automation state
- **Total impact:** Low (periodic cleanup)

---

## Exact Unlock Impact

### Would Memory Fix Alone Make Any Template Fully Executable?

**NO.** Every single memory template depends on at least one other blocked capability:

| Blocking Capability | Templates Blocked |
|--------------------|------------------|
| communication | 10 |
| ai_reasoning | 8 |
| browser | 3 |
| terminal | 3 |
| mcp_tool | 2 |
| knowledge | 4 |
| calendar | 1 |

### Templates Fully Unlocked by Memory Alone: **0**

### Templates Partially Improved by Memory: **13** (all of them — the memory step would work, but downstream steps still block)

### Templates Still Blocked by Other Capabilities: **13** (all of them)

---

## Other Blocking Capabilities

The 13 memory templates use these other capabilities:

| Capability | Templates Using | Current Provider Status |
|-----------|----------------|----------------------|
| communication | 10 | ROUTING_ONLY — no provider, needs APP_CAPABILITIES entry |
| ai_reasoning | 8 | ADAPTER_REQUIRED — needs JSON parsing adapter |
| knowledge | 4 | ROUTING_WORKS — direct boundary actions work |
| browser | 3 | ROUTING_WORKS — direct boundary actions work |
| terminal | 3 | ADAPTER_REQUIRED — TerminalProvider exists but needs entry |
| mcp_tool | 2 | PROVIDER_REQUIRED — MCP servers exist, needs entry |
| calendar | 1 | PROVIDER_REQUIRED — no provider |

**Key insight:** communication is the most common blocker (10/13 templates). If communication were implemented, 10 templates would unblock their communication step.

---

## Minimal Implementation Design

If memory were to be implemented, here is the smallest architecture-compatible design:

### 1. APP_CAPABILITIES Entry
```python
APP_CAPABILITIES["memory"] = [
    "filter_new", "diff_against_last", "diff_snapshots",
    "record_and_compare", "state_transition", "exclude_recently_contacted",
    "apply_field_map", "load_conversation", "save_turn",
    "gather_context", "week_activity"
]
```

### 2. Handler Function (~200 LOC)
```python
def _handle_memory(cap: str, args: str) -> dict:
    """Route memory capabilities to appropriate handlers."""
    import json
    try:
        params = json.loads(args) if args else {}
    except json.JSONDecodeError:
        return {"success": False, "message": "Invalid JSON args"}
    
    # Route to specific handler
    if cap == "filter_new":
        return _handle_filter_new(params)
    elif cap == "diff_against_last":
        return _handle_diff_against_last(params)
    # ... etc
```

### 3. Per-Action Handlers (~500 LOC total)
Each action needs its own handler with:
- Named key storage (SQLite)
- Comparison logic
- Time-based operations
- State management

### 4. Schema Changes (~100 LOC)
New SQLite tables for:
- `automation_state` (key, value, timestamp)
- `automation_snapshots` (key, snapshot, timestamp)
- `automation_seen` (key, item_hash, timestamp)

### 5. Tests (~200 LOC)
Unit tests for each action handler.

**Total estimated LOC: ~1000**

This exceeds the 500 LOC threshold significantly. The implementation would be complex because:
- Need to build entire automation state infrastructure
- Need to implement 9 new action handlers
- Need schema changes
- Need pruning/retention logic

---

## LOC Estimate

| Component | LOC |
|-----------|-----|
| APP_CAPABILITIES entry | 15 |
| Handler function | 200 |
| Per-action handlers (9) | 500 |
| Schema changes | 100 |
| Pruning/retention | 100 |
| Tests | 200 |
| **Total** | **~1115** |

This significantly exceeds the 500 LOC threshold.

---

## Comparison With Remaining Phase 4 Gaps

### Communication (31 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** HIGH — only needs send_message, send_batch, send_file, debounce_messages
- **Existing infrastructure reuse:** LOW — no communication provider exists
- **Implementation size:** ~300 LOC (APP_CAPABILITIES + handler)
- **Dependencies:** Bot tokens (telegram, slack, discord)
- **Credentials:** Required (bot tokens)
- **Security risk:** LOW — message sending only
- **Resource impact:** Minimal

### Memory (13 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** LOW — existing memory is conversational, not automation
- **Existing infrastructure reuse:** MEDIUM — MemoryStore exists but wrong pattern
- **Implementation size:** ~1115 LOC (exceeds threshold)
- **Dependencies:** None
- **Credentials:** None
- **Security risk:** MEDIUM — state persistence, cross-session concerns
- **Resource impact:** Low

### GitHub (8 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** MEDIUM — MCP server exists, needs entry
- **Existing infrastructure reuse:** HIGH — MCP gateway exists
- **Implementation size:** ~200 LOC (MCP server registration)
- **Dependencies:** GitHub MCP server
- **Credentials:** Required (GitHub token)
- **Security risk:** LOW — read/write GitHub
- **Resource impact:** Minimal

### Calendar (4 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** MEDIUM — needs Google Calendar integration
- **Existing infrastructure reuse:** LOW — no calendar provider
- **Implementation size:** ~400 LOC
- **Dependencies:** Google Calendar API
- **Credentials:** Required (OAuth2)
- **Security risk:** LOW — calendar read/write
- **Resource impact:** Minimal

### Terminal (3 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** HIGH — TerminalProvider exists
- **Existing infrastructure reuse:** HIGH — TerminalProvider exists
- **Implementation size:** ~100 LOC (APP_CAPABILITIES entry)
- **Dependencies:** None
- **Credentials:** None
- **Security risk:** MEDIUM — command execution
- **Resource impact:** Minimal

### MCP Tool (2 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** HIGH — MCP gateway exists
- **Existing infrastructure reuse:** HIGH — MCP gateway exists
- **Implementation size:** ~150 LOC (MCP server registration)
- **Dependencies:** MCP servers
- **Credentials:** Varies by MCP server
- **Security risk:** LOW — tool execution via MCP
- **Resource impact:** Minimal

### AI Reasoning (46 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** LOW — needs structured output, schema validation
- **Existing infrastructure reuse:** MEDIUM — ask_llm() exists but wrong pattern
- **Implementation size:** ~470 LOC (but misleading — 0 templates become executable)
- **Dependencies:** LLM providers
- **Credentials:** Required (API keys)
- **Security risk:** MEDIUM — prompt injection
- **Resource impact:** Low

### Media (3 templates)
- **Templates potentially unlocked:** 0 (all have other dependencies)
- **Semantic compatibility:** LOW — needs STT, TTS, image generation
- **Existing infrastructure reuse:** LOW — no media provider
- **Implementation size:** ~500 LOC
- **Dependencies:** External media APIs
- **Credentials:** Required
- **Security risk:** LOW
- **Resource impact:** Low

---

## Final Decision

**Decision: C — DEFER_MEMORY**

### Rationale

1. **Zero templates fully unlocked.** Every memory template depends on other blocked capabilities. Implementing memory alone makes zero templates executable.

2. **Semantic mismatch.** 9 of 14 memory actions require entirely new persistence patterns (snapshots, deduplication, state tracking, activity aggregation) that don't exist in the current MemoryStore. The existing infrastructure is for conversational memory, not automation memory.

3. **Implementation exceeds threshold.** At ~1115 LOC, memory implementation significantly exceeds the 500 LOC threshold. This is because it requires building an entirely new automation state infrastructure.

4. **Deceptive unlock count.** Claiming "13 templates unlocked" would be false. The real number is 0.

5. **Better targets exist.** Communication (31 templates) is the most common blocker and only needs ~300 LOC. Terminal (3 templates) only needs ~100 LOC. GitHub (8 templates) only needs ~200 LOC.

---

## Recommended Next Phase 4 Action

**Implement `communication` capability instead.**

Communication has:
- 31 templates depending on it (most common blocker)
- Simpler semantic surface (send_message, send_batch, send_file, debounce_messages)
- Only needs ~300 LOC
- Would unblock communication steps in 31 templates

After communication, implement `terminal` (~100 LOC) and `github` (~200 LOC) — they're small, high-impact, and would unblock more templates.

---

## Audit Confirmation

1. **Memory templates audited:** 13
2. **Exact memory actions:** 14 (11 distinct patterns)
3. **Existing KIO memory capabilities:** Conversational memory (message history + facts)
4. **Exact directly-supported count:** 2 (load_conversation, save_turn)
5. **Exact adapter-required count:** 0
6. **Exact provider-required count:** 9
7. **Exact unsupported count:** 0
8. **Exact templates fully unlocked by memory alone:** 0
9. **Exact templates still blocked by other capabilities:** 13
10. **Honest LOC estimate:** ~1115 (exceeds 500 LOC threshold)
11. **Security/privacy findings:** Medium risk — cross-session state, unbounded growth, no pruning
12. **Resource findings:** Low impact (~20-50 MB storage, minimal RAM)
13. **ONE final recommendation:** DEFER_MEMORY, implement communication instead
14. **Confirmation:** NO source/YAML/architecture changes were made during this audit
