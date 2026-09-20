# KIO Phase 4 — Step 7: AI Reasoning Provider Wiring

## Decision
**Decision A: IMPLEMENT** — Wire the existing KIO LLM stack (ask_llm/ask_llm_sync/LLMGateway) into the ai_reasoning adapter inside execute_capability().

## Summary
| Metric | Value |
|--------|-------|
| Implementation LOC | ~62 (adapter handler + APP_CAPABILITIES registration) |
| Tests | 19/19 pass |
| Templates unlocked | 26 FULL + 6 PARTIAL (from BLOCKED: 20 → 0) |
| New LLM frameworks added | 0 (reuses existing ask_llm_sync) |
| Security boundaries | Preserved (ExecutionBoundary, SecurityBridge, CredentialBridge untouched) |

## Problem
Before this step, all 52 ai_reasoning actions were mapped in StepRunner._ACTION_MAP → "execute_capability", but execute_capability() had no handler for `app_name == "ai_reasoning"`. This made ai_reasoning the single largest internal routing gap — 26 templates were BLOCKED purely because of this missing handler.

## Architecture
The ai_reasoning adapter is a thin bridge between the YAML template system and the existing LLM infrastructure:

```
YAML step → StepRunner._ACTION_MAP → execute_capability("ai_reasoning::action::{json}")
                                        ↓
                                  Parse target string
                                        ↓
                                  Build prompt from inputs
                                        ↓
                                  Route task tier (reasoning/summarize/analysis)
                                        ↓
                                  ask_llm_sync(prompt, task=...)
                                        ↓
                                  LLMGateway → provider chain (Gemini→Groq→HF→...)
                                        ↓
                                  Parse JSON response (strip fences if needed)
                                        ↓
                                  Return structured dict
```

### Key Design Decisions

1. **Task-tier routing** (not just "call LLM"):
   - classify/detect/validate → task="reasoning" → preferred provider: Gemini
   - summarize → task="summarize" → preferred provider: Groq (fast)
   - analyze/extract/compose/research → task="analysis" → preferred provider: Gemini

2. **JSON response parsing**: All 46 templates require structured JSON output. The adapter:
   - Sends a system prompt requesting JSON-only response
   - Strips markdown fences (` ```json ... ``` `) if present
   - Parses as JSON; on failure, wraps raw text in `{"text": content}`

3. **No schema validation**: Templates define their own output fields. The adapter returns whatever JSON the LLM produces. Schema validation is a future concern.

4. **Graceful degradation**: If LLM returns None/non-JSON, returns structured error. Never crashes.

## What Changed

### `mini_kio/core/app_operator.py`

1. **APP_CAPABILITIES** (line ~3176): Added `"ai_reasoning"` with 52 action names
2. **execute_capability()** (line ~3534): Added ai_reasoning handler block (~50 LOC)

### `tests/test_ai_reasoning_routing.py` (NEW)
19 tests across 6 groups:
- A: Capability registration (3 tests)
- B: StepRunner routing (2 tests)
- C: execute_capability routing (5 tests)
- D: Task-tier routing (3 tests)
- E: Security: no secrets in output (2 tests)
- F: Regression: existing handlers unchanged (4 tests)

## Template Re-evaluation

### Before Step 7
| Status | Count | |
|--------|-------|-|
| FULL | 5 | |
| PARTIAL | 38 | |
| BLOCKED | 20 | |

### After Step 7
| Status | Count | Delta |
|--------|-------|-------|
| FULL | 31 | +26 |
| PARTIAL | 32 | -6 |
| BLOCKED | 0 | -20 |

### Templates Now FULL (31)
These templates had ai_reasoning as their ONLY missing internal router:
- ai.classify_and_route, ai.extract_to_structured, ai.transcribe_summarize
- artifacts.data_to_xlsx, artifacts.meeting_to_report, artifacts.multiformat_report
- artifacts.research_to_docx, artifacts.research_to_pdf, artifacts.research_to_pptx
- business.email_autoresponder_approval
- communication.chat_assistant, communication.escalation_alert, communication.notify, communication.workflow_failure_alert
- data.csv_pii_scrub, data.file_extract_to_csv, data.form_intake, data.json_transform
- development.scaffold_project
- files.document_summarize, files.download_folder_organizer, files.duplicate_detector, files.invoice_extract_to_sheet
- monitoring.inbox_monitor
- productivity.calendar_to_status, productivity.ecosystem_briefing, productivity.email_label_ai, productivity.email_to_calendar, productivity.meeting_prep, productivity.weekly_review
- research.daily_brief

### Templates Now PARTIAL (32)
These templates have internal routing but still depend on external capabilities:
- **browser** (5): page_change_monitor, price_monitor, structured_extract, competitor_monitor, web_scrape_to_report
- **media** (4): image_generate, voice_assistant, drive_to_social, content_repurpose
- **github** (8): ci_failure_alert, dependency_monitor, github_issue_triage, issue_to_implementation, pr_review_prep, release_changelog, repo_backup, repo_health_report
- **knowledge** (8): enrich_records, rag_answer, api_poll_to_store, data/webhook_to_store, rss_news_monitor, security_scan_alert, website_uptime, youtube_summary
- **mcp_tool** (8): crm_followup, lead_intake_crm, support_ticket_triage, knowledge_base_sync, record_sync, email_to_task, morning_briefing
- **Combined** (1): morning_briefing (knowledge + mcp_tool), lead_intake_crm (knowledge + mcp_tool)

### Templates BLOCKED: 0
All internal routing gaps eliminated.

## What Was Skipped
- **Schema validation**: No JSON schema enforcement for LLM outputs. Templates must tolerate variable field names.
- **Streaming**: ask_llm_sync is synchronous. Async streaming for long outputs is a future concern.
- **Multimodal**: image_generate still PARTIAL (needs media capability, not ai_reasoning alone).
- **Persistent context/memory**: Templates needing conversation history across steps remain PARTIAL.

## Remaining External Gaps
| Capability | Templates | Unlocked by |
|------------|-----------|-------------|
| browser | 5 | Browser automation provider |
| media | 4 | Media processing provider |
| github | 8 | GitHub API integration |
| knowledge | 8 | Knowledge base/RAG provider |
| mcp_tool | 8 | MCP tool registry |

## Verification
```
python -m pytest tests/test_ai_reasoning_routing.py -v
# 19/19 pass

python -m pytest tests/test_p1_contract_fix.py tests/test_workflow_routing.py -v
# 30/30 pass (regression)
```

## LOC Budget
| Item | LOC |
|------|-----|
| APP_CAPABILITIES addition | 12 |
| execute_capability() handler | 50 |
| **Total implementation** | **62** |
| Tests | 130 |
| **Total** | **192** |
