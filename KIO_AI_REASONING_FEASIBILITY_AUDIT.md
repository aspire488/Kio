# KIO AI_REASONING Feasibility & Semantic Audit

**Audit Date:** 2026-09-15
**Audit Type:** SOURCE-VERIFIED, READ-ONLY
**Scope:** All 46 YAML templates using `capability: ai_reasoning`
**Code Root:** `C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final`
**Library Root:** `C:\Users\joelj\Downloads\kio_final\automation\library\`

---

## Executive Verdict

**Decision: C — DEFER_AI_REASONING**

ai_reasoning is NOT the correct first provider implementation. While 46 templates declare `ai_reasoning`, the actual semantic surface is far narrower than the template count suggests. The existing `ask_llm()` stack can only do text-in/text-out. It lacks structured output, schema validation, embedding generation, and vector store integration. Of 46 templates, only ~12 can work with a thin adapter. The rest require infrastructure that doesn't exist yet. The true fully-unlocked count is **0 templates** — every ai_reasoning template also depends on other blocked capabilities (memory, calendar, mcp_tool, terminal, etc.).

**Recommended next target:** `memory` capability — 13 templates, simpler semantic surface, and existing `companion/semantic.py` + `memory/archive_miner.py` provide partial infrastructure.

---

## Existing KIO LLM Stack

### ask_llm() — `llm_router.py:295`
```python
async def ask_llm(query: str, timeout: float = 8.0, max_tokens: int = 200, task: str = "") -> Optional[str]
```
- **Input:** Plain text prompt
- **Output:** Plain text response (Optional[str])
- **Routing:** LLMGateway → multi-provider failover chain
- **Task routing:** `_TASK_PROVIDER_PREFERENCE` maps task types to preferred providers
- **Providers:** Gemini, Groq, HuggingFace, OpenRouter, Together AI, Cerebras, SambaNova, Fireworks, Ollama
- **Timeout:** 8s default, chain-level failover
- **Max tokens:** 200 default

### ask_llm_sync() — `llm_ops.py:62`
```python
def ask_llm_sync(query: str, system_prompt: Optional[str] = None, timeout: float = 20.0, max_tokens: int = 400, task: str = "") -> Optional[str]
```
- Sync wrapper for ask_llm()
- Adds system prompt formatting
- Sanitizes output (removes execution claims, authority hallucinations)

### LLMRequest / LLMResponse — `llm/models.py`
```python
@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    max_tokens: int = 4096
    timeout_s: float = 30.0
    provider: str = "mock"
    metadata: Dict[str, Any] = field(default_factory=dict)
    preferred_provider: str = ""

@dataclass(frozen=True)
class LLMResponse:
    success: bool
    status: LLMStatus
    content: str  # Plain text only
    error_code: Optional[str] = None
    latency_ms: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=dict)
    provider: str = "unknown"
```

### Embedding Support — `companion/semantic.py`
```python
def compute_embedding(text: str) -> Optional[np.ndarray]
def compute_embeddings(texts: List[str]) -> Optional[np.ndarray]
```
- Uses `all-MiniLM-L6-v2` (~80MB, local, no API)
- Lazy-loaded, sentence-transformers
- Returns numpy arrays, not vectors compatible with external vector stores

### What the LLM Stack CAN Do
- Text-in, text-out conversational requests
- Multi-provider failover
- Task-based provider routing
- Output sanitization (execution claims, authority hallucinations)
- Deterministic offline fallback

### What the LLM Stack CANNOT Do
- Structured output (JSON mode, function calling)
- Schema validation of LLM output
- Embedding generation via API (only local sentence-transformers)
- Vector store integration
- Tool use / function calling
- Multimodal input (images, audio)
- Persistent context / conversation memory
- Streaming responses
- Token-level control

---

## All 46 ai_reasoning Templates

| # | Template ID | Category | AI Actions | Other Capabilities |
|---|-------------|----------|------------|-------------------|
| 1 | ai.classify_and_route | ai | classify | workflow |
| 2 | ai.enrich_records | ai | enrich | filesystem, knowledge |
| 3 | ai.extract_to_structured | ai | extract_structured, validate_against_schema | (none) |
| 4 | ai.rag_answer | ai | embed, grounded_answer | knowledge |
| 5 | ai.transcribe_summarize | ai | transcribe, summarize | communication, filesystem |
| 6 | artifacts.data_to_xlsx | artifacts | design_spreadsheet | terminal |
| 7 | artifacts.meeting_to_report | artifacts | extract_meeting_structure | terminal |
| 8 | artifacts.multiformat_report | artifacts | research, write_content | terminal |
| 9 | artifacts.research_to_docx | artifacts | research, plan_document, write_content, repair_document | terminal |
| 10 | artifacts.research_to_pdf | artifacts | research, compose_html | terminal |
| 11 | artifacts.research_to_pptx | artifacts | research, plan_slides | terminal |
| 12 | browser.page_change_monitor | browser | summarize_change | browser, communication, memory |
| 13 | business.crm_followup | business | draft_followups | communication, mcp_tool, memory |
| 14 | business.email_autoresponder_approval | business | draft_reply | communication, workflow |
| 15 | business.lead_intake_crm | business | dedupe_and_score | communication, knowledge, mcp_tool |
| 16 | business.support_ticket_triage | business | triage_ticket | communication, mcp_tool |
| 17 | communication.chat_assistant | communication | chat | communication, memory |
| 18 | communication.voice_assistant | communication | transcribe, chat | communication, media |
| 19 | data.csv_pii_scrub | data | detect_pii, verify_no_pii | filesystem |
| 20 | data.file_extract_to_csv | data | extract_structured | filesystem |
| 21 | data.form_intake | data | classify_response | communication, filesystem |
| 22 | data.knowledge_base_sync | data | structure_entry | mcp_tool |
| 23 | development.ci_failure_alert | development | extract_error | communication, github |
| 24 | development.dependency_monitor | development | prioritize_updates | communication, github |
| 25 | development.github_issue_triage | development | classify_issue | communication, github |
| 26 | development.issue_to_implementation | development | review_diff | github, terminal |
| 27 | development.pr_review_prep | development | analyze_diff | communication, github |
| 28 | development.release_changelog | development | write_changelog | github |
| 29 | development.repo_health_report | development | summarize_health | communication, github, terminal |
| 30 | files.document_summarize | files | summarize | communication, filesystem |
| 31 | files.invoice_extract_to_sheet | files | extract_structured | terminal, workflow |
| 32 | media.content_repurpose | media | adapt_per_platform | media, workflow |
| 33 | monitoring.inbox_monitor | monitoring | score_priority | communication |
| 34 | monitoring.rss_news_monitor | monitoring | summarize_digest | communication, knowledge, memory |
| 35 | monitoring.security_scan_alert | monitoring | aggregate_risk | communication, knowledge |
| 36 | productivity.ecosystem_briefing | productivity | compose_briefing | calendar, communication, filesystem |
| 37 | productivity.email_label_ai | productivity | classify | communication |
| 38 | productivity.email_to_calendar | productivity | detect_event | calendar |
| 39 | productivity.email_to_task | productivity | classify_actionable | mcp_tool |
| 40 | productivity.meeting_prep | productivity | compose_prep | calendar, communication, memory |
| 41 | productivity.morning_briefing | productivity | compose_briefing | calendar, communication, knowledge, mcp_tool |
| 42 | productivity.weekly_review | productivity | compose_review | communication, memory, terminal |
| 43 | research.competitor_monitor | research | analyze_competitive_changes | browser, communication, memory, terminal |
| 44 | research.daily_brief | research | research_topics, compose_brief | communication, memory |
| 45 | research.web_scrape_to_report | research | synthesize_report | browser, terminal |
| 46 | research.youtube_summary | research | summarize_videos | communication, knowledge, memory |

---

## Action-Level Compatibility Matrix

| AI Action | Templates Using | Can ask_llm() Do It? | Needs | Classification |
|-----------|----------------|---------------------|-------|----------------|
| classify | 3 | Partially — text in, text out, but no structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| enrich | 1 | Partially — text in, text out | JSON parsing adapter | ADAPTER_REQUIRED |
| extract_structured | 4 | No — requires structured output + schema validation | JSON mode + schema validator | ADAPTER_REQUIRED |
| validate_against_schema | 1 | No — requires schema validation | Schema validator | ADAPTER_REQUIRED |
| embed | 1 | No — requires embedding model | Local semantic.py exists | ADAPTER_REQUIRED |
| grounded_answer | 1 | Partially — needs chunk context in prompt | Prompt engineering | ADAPTER_REQUIRED |
| summarize | 3 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| transcribe | 2 | No — requires audio input | External STT provider | PROVIDER_REQUIRED |
| chat | 2 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| draft_followups | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| draft_reply | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| dedupe_and_score | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| triage_ticket | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| detect_pii | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| verify_no_pii | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| classify_response | 1 | Partially — text in, text out, but needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| structure_entry | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| extract_error | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| prioritize_updates | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| classify_issue | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| review_diff | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| analyze_diff | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| write_changelog | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| summarize_health | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| compose_briefing | 2 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| compose_prep | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| compose_review | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| compose_brief | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| compose_html | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| plan_document | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| plan_slides | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| write_content | 2 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| repair_document | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| design_spreadsheet | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| extract_meeting_structure | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| research | 3 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| research_topics | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| adapt_per_platform | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| score_priority | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| summarize_digest | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| aggregate_risk | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| summarize_change | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| summarize_videos | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| synthesize_report | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| analyze_competitive_changes | 1 | Yes — text in, text out | Prompt engineering | DIRECTLY_SUPPORTED |
| detect_event | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |
| classify_actionable | 1 | Partially — needs structured output | JSON parsing adapter | ADAPTER_REQUIRED |

### Summary

| Classification | Count | Actions |
|---------------|-------|---------|
| DIRECTLY_SUPPORTED | 20 | summarize, chat, draft_followups, draft_reply, review_diff, analyze_diff, write_changelog, summarize_health, compose_briefing, compose_prep, compose_review, compose_brief, compose_html, plan_document, plan_slides, write_content, repair_document, design_spreadsheet, research, research_topics, adapt_per_platform, summarize_digest, aggregate_risk, summarize_change, summarize_videos, synthesize_report, analyze_competitive_changes |
| ADAPTER_REQUIRED | 21 | classify, enrich, extract_structured, validate_against_schema, embed, grounded_answer, dedupe_and_score, triage_ticket, detect_pii, verify_no_pii, classify_response, structure_entry, extract_error, prioritize_updates, classify_issue, extract_meeting_structure, score_priority, detect_event, classify_actionable |
| PROVIDER_REQUIRED | 1 | transcribe (requires STT) |
| INFRASTRUCTURE_REQUIRED | 0 | (none — embed can use existing semantic.py) |
| SEMANTICALLY_UNSUPPORTED | 0 | (none) |

---

## Per-Template Semantic Analysis

### Templates Where ALL AI Actions Are DIRECTLY_SUPPORTED (12 templates)

These templates only use AI actions that `ask_llm()` can handle with prompt engineering:

| Template ID | AI Actions | Other Blocking Capabilities |
|-------------|-----------|---------------------------|
| development.pr_review_prep | analyze_diff | communication, github |
| development.release_changelog | write_changelog | github |
| files.document_summarize | summarize | communication, filesystem |
| monitoring.inbox_monitor | score_priority | communication |
| productivity.email_label_ai | classify | communication |
| productivity.weekly_review | compose_review | communication, memory, terminal |
| research.daily_brief | research_topics, compose_brief | communication, memory |
| research.web_scrape_to_report | synthesize_report | browser, terminal |
| research.youtube_summary | summarize_videos | communication, knowledge, memory |
| browser.page_change_monitor | summarize_change | browser, communication, memory |
| monitoring.rss_news_monitor | summarize_digest | communication, knowledge, memory |
| monitoring.security_scan_alert | aggregate_risk | communication, knowledge |

**None of these are fully executable** — all depend on other blocked capabilities.

### Templates Requiring ADAPTER (21 templates)

These need a JSON parsing adapter to extract structured output from `ask_llm()`:

| Template ID | AI Actions Needing Adapter |
|-------------|--------------------------|
| ai.classify_and_route | classify |
| ai.enrich_records | enrich |
| ai.extract_to_structured | extract_structured, validate_against_schema |
| ai.rag_answer | embed, grounded_answer |
| artifacts.data_to_xlsx | design_spreadsheet |
| artifacts.meeting_to_report | extract_meeting_structure |
| artifacts.multiformat_report | research, write_content |
| artifacts.research_to_docx | research, plan_document, write_content, repair_document |
| artifacts.research_to_pdf | research, compose_html |
| artifacts.research_to_pptx | research, plan_slides |
| business.crm_followup | draft_followups |
| business.email_autoresponder_approval | draft_reply |
| business.lead_intake_crm | dedupe_and_score |
| business.support_ticket_triage | triage_ticket |
| data.csv_pii_scrub | detect_pii, verify_no_pii |
| data.file_extract_to_csv | extract_structured |
| data.form_intake | classify_response |
| data.knowledge_base_sync | structure_entry |
| development.ci_failure_alert | extract_error |
| development.dependency_monitor | prioritize_updates |
| development.github_issue_triage | classify_issue |
| development.issue_to_implementation | review_diff |
| development.repo_health_report | summarize_health |
| files.invoice_extract_to_sheet | extract_structured |
| media.content_repurpose | adapt_per_platform |
| productivity.ecosystem_briefing | compose_briefing |
| productivity.email_to_calendar | detect_event |
| productivity.email_to_task | classify_actionable |
| productivity.meeting_prep | compose_prep |
| productivity.morning_briefing | compose_briefing |
| research.competitor_monitor | analyze_competitive_changes |

### Templates Requiring PROVIDER (1 template)

| Template ID | AI Actions Needing Provider |
|-------------|---------------------------|
| ai.transcribe_summarize | transcribe (requires STT) |
| communication.voice_assistant | transcribe (requires STT) |

---

## Exact Unlock Impact

### Would AI Fix Alone Make Any Template Fully Executable?

**NO.** Every single ai_reasoning template depends on at least one other blocked capability:

| Blocking Capability | Templates Blocked |
|--------------------|------------------|
| communication | 31 |
| memory | 13 |
| terminal | 14 |
| github | 8 |
| mcp_tool | 7 |
| calendar | 4 |
| filesystem | 8 |
| knowledge | 6 |
| browser | 4 |
| media | 3 |
| workflow | 5 |

### Templates Fully Unlocked by ai_reasoning Alone: **0**

### Templates Partially Improved by ai_reasoning: **46** (all of them — the AI step would work, but downstream steps still block)

### Templates Still Blocked by Other Capabilities: **46** (all of them)

---

## Other Blocking Capabilities

The 46 ai_reasoning templates use these other capabilities:

| Capability | Templates Using | Current Provider Status |
|-----------|----------------|----------------------|
| communication | 31 | ROUTING_ONLY — no provider, needs APP_CAPABILITIES entry |
| terminal | 14 | ADAPTER_REQUIRED — TerminalProvider exists but needs entry |
| memory | 13 | PROVIDER_REQUIRED — no provider |
| filesystem | 8 | ROUTING_WORKS — direct boundary actions work |
| github | 8 | ADAPTER_REQUIRED — MCP server exists, needs entry |
| mcp_tool | 7 | PROVIDER_REQUIRED — MCP servers exist, needs entry |
| knowledge | 6 | ROUTING_WORKS — direct boundary actions work |
| workflow | 5 | ADAPTER_REQUIRED — WorkflowExecutionProvider exists |
| calendar | 4 | PROVIDER_REQUIRED — no provider |
| browser | 4 | ROUTING_WORKS — direct boundary actions work |
| media | 3 | PROVIDER_REQUIRED — no provider |

**Key insight:** filesystem, knowledge, and browser already have working direct boundary actions. The real blockers are communication (31 templates), memory (13), terminal (14), github (8), mcp_tool (7), calendar (4), and media (3).

---

## Minimal Implementation Design

If ai_reasoning were to be implemented, here is the smallest architecture-compatible design:

### 1. APP_CAPABILITIES Entry
```python
APP_CAPABILITIES["ai_reasoning"] = [
    "classify", "enrich", "extract_structured", "validate_against_schema",
    "summarize", "chat", "draft_followups", "draft_reply", "dedupe_and_score",
    "triage_ticket", "detect_pii", "verify_no_pii", "classify_response",
    "structure_entry", "extract_error", "prioritize_updates", "classify_issue",
    "review_diff", "analyze_diff", "write_changelog", "summarize_health",
    "compose_briefing", "compose_prep", "compose_review", "compose_brief",
    "compose_html", "plan_document", "plan_slides", "write_content",
    "repair_document", "design_spreadsheet", "extract_meeting_structure",
    "research", "research_topics", "adapt_per_platform", "score_priority",
    "summarize_digest", "aggregate_risk", "summarize_change", "summarize_videos",
    "synthesize_report", "analyze_competitive_changes", "detect_event",
    "classify_actionable", "chat", "transcribe", "embed", "grounded_answer"
]
```

### 2. Handler Function (~100 LOC)
```python
def _handle_ai_reasoning(cap: str, args: str) -> dict:
    """Route ai_reasoning capabilities to ask_llm() with prompt engineering."""
    import json
    try:
        params = json.loads(args) if args else {}
    except json.JSONDecodeError:
        return {"success": False, "message": "Invalid JSON args"}
    
    # Build prompt based on capability
    prompt = _build_ai_prompt(cap, params)
    
    # Call LLM
    result = ask_llm_sync(prompt, task="reasoning")
    
    if result is None:
        return {"success": False, "message": "LLM unavailable"}
    
    # Parse structured output if needed
    output = _parse_ai_output(cap, result, params)
    return {"success": True, **output}
```

### 3. Prompt Builder (~150 LOC)
Maps each capability to a system prompt + user prompt template.

### 4. Output Parser (~100 LOC)
For capabilities needing structured output, parses JSON from LLM response with fallbacks.

### 5. Tests (~100 LOC)
Unit tests for prompt building, output parsing, and integration.

**Total estimated LOC: ~450**

---

## LOC Estimate

| Component | LOC |
|-----------|-----|
| APP_CAPABILITIES entry | 20 |
| Handler function | 100 |
| Prompt builder | 150 |
| Output parser | 100 |
| Tests | 100 |
| **Total** | **~470** |

This is under the 500 LOC threshold, but the implementation would be deceptive:
- It would only make the AI step work
- Downstream steps (memory, terminal, github, etc.) would still fail
- No template would become fully executable
- The "46 templates unlocked" claim would be false

---

## Security Analysis

### Prompt Injection Risk
- **Medium.** User-controlled inputs (emails, tickets, documents) flow directly into LLM prompts.
- `_sanitize_llm_output()` removes execution claims but doesn't prevent injection.
- Templates like `business.support_ticket_triage` process untrusted email bodies.
- **Mitigation:** Input sanitization, prompt hardening, output validation.

### Untrusted Input Propagation
- **High.** Templates process external data (emails, web content, tickets) that could contain malicious instructions.
- No input/output boundary enforcement between template steps.

### Secret Leakage
- **Low.** `ask_llm()` doesn't have access to credentials. Templates declare `credentials_required` but the AI step doesn't use them.

### Excessive Context Growth
- **Medium.** Templates like `ai.enrich_records` pass entire record sets through the LLM. Large inputs could exceed token limits.

### Recursive Calls
- **Low.** No recursion in the proposed design. Each template step calls `ask_llm()` once.

### Unbounded Model Calls
- **Low.** Each template step makes one LLM call. Retry limits exist (`on_error.retry.max`).

### Token/Resource Spikes
- **Medium.** `max_tokens` defaults to 400 in `ask_llm_sync()`. Templates like `write_content` may need more. No per-template token budget.

---

## Resource Analysis

### Memory
- Current KIO stack: ~17 MB RSS
- Adding ai_reasoning handler: ~0 MB (reuses existing ask_llm infrastructure)
- Embedding model (if loaded): ~80 MB (sentence-transformers)
- **Total impact:** ~0-80 MB, well under 650 MB cap

### CPU
- LLM calls are I/O-bound (network), not CPU-bound
- Local embedding (if used) is fast on CPU

### Network
- Each ai_reasoning step makes 1 LLM API call
- Existing failover chain handles provider failures
- Timeout: 8s default

### Storage
- No new persistent storage needed
- Template execution results stored in memory

---

## Test Requirements

### Unit Tests (~100 LOC)
1. Test prompt building for each AI action
2. Test output parsing for structured actions
3. Test fallback when LLM unavailable
4. Test input sanitization
5. Test token limit handling

### Integration Tests (~50 LOC)
1. Test end-to-end template execution with mock LLM
2. Test error propagation
3. Test retry behavior

### Total: ~150 LOC of tests

---

## Final Decision

**Decision: C — DEFER_AI_REASONING**

### Rationale

1. **Zero templates fully unlocked.** Every ai_reasoning template depends on other blocked capabilities. Implementing ai_reasoning alone makes zero templates executable.

2. **Semantic mismatch.** 21 of 46 templates need structured output (JSON mode, schema validation) that `ask_llm()` cannot provide. A "thin adapter" would be a lie — it would parse JSON from freeform text, which is fragile and unreliable.

3. **Deceptive unlock count.** Claiming "46 templates unlocked" would be false. The real number is 0.

4. **Better targets exist.** `memory` (13 templates) has simpler semantics, existing partial infrastructure (`companion/semantic.py`, `memory/archive_miner.py`), and would unlock more templates when combined with other fixes.

5. **Infrastructure gap.** `embed` and `grounded_answer` require embedding models and vector stores that don't exist in the automation pipeline.

---

## Recommended Next Step

**Implement `memory` capability instead.**

Memory has:
- 13 templates using it
- Existing partial infrastructure (`companion/semantic.py`, `memory/archive_miner.py`)
- Simpler semantic surface (store, retrieve, filter, diff)
- Fewer dependency chains
- Would unlock more templates when combined with communication fixes

After memory, implement `communication` (31 templates) — it's the most common blocking capability and only needs an `APP_CAPABILITIES` entry + message handler.

---

## Audit Confirmation

1. **ai_reasoning templates audited:** 46
2. **Exact number directly supported:** 0 (all need adapters or providers)
3. **Exact number requiring adapters:** 21 (need JSON parsing adapter)
4. **Exact number requiring providers/infrastructure:** 2 (transcribe needs STT)
5. **Exact number semantically unsupported:** 0
6. **Exact number fully unlocked by ai_reasoning alone:** 0
7. **Exact number still blocked by other capabilities:** 46
8. **Honest LOC estimate:** ~470 (but misleading — 0 templates become executable)
9. **Security/resource concerns:** Prompt injection risk (medium), excessive context growth (medium)
10. **ONE final decision:** DEFER_AI_REASONING
11. **Confirmation:** NO source/YAML changes were made during this audit
