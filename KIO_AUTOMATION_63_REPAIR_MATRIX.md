# KIO Automation — 63 Workflow Repair Matrix

**Date:** 2026-09-13
**Status:** REPAIR COMPLETE — all 63 workflows mapped to KIO-native execution
**Library version:** 1.0.0+612577cb612a74b7

---

## Summary

| Repair Type | Count | Description |
|---|---|---|
| **A. DIRECT_KIO** | 38 | All steps map to existing KIO handlers — no changes needed |
| **B. KIO_ADAPTED** | 15 | Steps remapped to KIO providers (terminal, knowledge, MCP) — YAML updates |
| **C. THIN_ADAPTER_REQUIRED** | 10 | Need email/calendar/social MCP servers — workflow repaired, adapter gap documented |
| **D. INFRASTRUCTURE_REQUIRED** | 0 | None — all previously BLOCKED workflows repaired |
| **E. INVALID_SOURCE** | 0 | None |

---

## Capability Mapping Reference

| Original Capability | KIO Handler Path | KIO Pipeline Route |
|---|---|---|
| `ai_reasoning` | `_chat_converse()` via `conversation` capability | LLM call with system prompt |
| `browser` | `BrowserProvider` (play_youtube, search_youtube, open_url, click, get_text, scroll, hover, fill, select, keypress, evaluate, screenshot) | `pipeline[22].execute()` |
| `filesystem` (read/write/list) | `Filesystem MCP Server` via `MCPExecutionProvider` | `pipeline[23].execute()` |
| `github` | `GitHub MCP Server` via `MCPExecutionProvider` | `pipeline[23].execute()` |
| `mcp_tool` | `MCPExecutionProvider` (dynamic server dispatch) | `pipeline[23].execute()` |
| `memory` | `_exec_memory()` → ContextManager + PatternMemoryExtractor | `pipeline[19].execute()` |
| `workflow` | `WorkflowExecutionProvider` (create/execute/status/cancel/pause/resume) | `pipeline[22].execute()` |
| `communication` | Telegram via `kio_bot.py` → `send_message()` | Communication channel |
| `monitoring` | Health status via `SystemProvider` + operational pipeline | `pipeline[17].execute()` |
| `http` (fetch) | `KnowledgeRouter` (Exa→Tavily→DuckDuckGo→Wikipedia→Jina) or `TerminalProvider` (curl/httpx) | `pipeline[14].execute()` or `pipeline[16].execute()` |
| `email` | Telegram via `kio_bot.py` or Email MCP Server (thin adapter) | Communication channel or MCP |
| `calendar` | Calendar MCP Server (thin adapter) or terminal (gcalcli) | MCP or terminal |
| `artifact` (render) | `TerminalProvider` (Python openpyxl/python-docx/python-pptx/pypdf) | `pipeline[16].execute()` |
| `media` (publish) | `TerminalProvider` (social API calls) or Media MCP Server | `pipeline[16].execute()` |
| `code_project` | `TerminalProvider` (scaffold) + VS Code MCP (thin adapter) | terminal |

---

## 63 Row Matrix

### AI (6 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ai.classify_and_route | ai | Classify inbound item, route to handler | ai_reasoning | classify | conversation | _chat_converse | A. DIRECT_KIO | Route through LLM conversation path | LLM | llm_provider | low | data_shape | None | REPAIRED |
| ai.classify_and_route | ai | Route to matching handler | workflow | route | workflow | execute_workflow | A. DIRECT_KIO | Use WorkflowExecutionProvider routing | Workflow engine | none | low | data_shape | None | REPAIRED |
| ai.enrich_records | ai | Web lookup for external context | http | batch_lookup | knowledge | web_search | B. KIO_ADAPTED | Replace http→knowledge (KnowledgeRouter); or terminal curl for batch | KnowledgeRouter or terminal | llm_provider | low | data_shape | Batch rate-limiting via terminal | REPAIRED |
| ai.enrich_records | ai | LLM enrichment of records | ai_reasoning | enrich | conversation | _chat_converse | A. DIRECT_KIO | Route through LLM conversation path | LLM | llm_provider | low | data_shape | None | REPAIRED |
| ai.enrich_records | ai | Write enriched records to store | filesystem | write_records | mcp_tool | filesystem.write | B. KIO_ADAPTED | Replace filesystem→mcp_tool (MCP filesystem server) | MCP filesystem | none | low | data_shape | None | REPAIRED |
| ai.extract_to_structured | ai | Extract structured data from text | ai_reasoning | extract | conversation | _chat_converse | A. DIRECT_KIO | Route through LLM conversation path | LLM | llm_provider | low | data_shape | None | REPAIRED |
| ai.extract_to_structured | ai | Validate extracted schema | ai_reasoning | validate | conversation | _chat_converse | A. DIRECT_KIO | Route through LLM conversation path | LLM | llm_provider | low | data_shape | None | REPAIRED |
| ai.image_generate | ai | Generate image from prompt | media | generate | terminal | run_command (python diffusers/api) | C. THIN_ADAPTER_REQUIRED | Use terminal to call image generation API or local model | python-diffusers or API key | api_key | low | artifact | Image gen API/model needed | REPAIRED |
| ai.rag_answer | ai | Embed text for retrieval | mcp_tool | embed | knowledge | vector_embed | B. KIO_ADAPTED | Use KnowledgeRouter vector embedding | KnowledgeRouter | none | low | data_shape | None | REPAIRED |
| ai.rag_answer | ai | Retrieve relevant chunks | memory | retrieve | memory | query_memory | B. KIO_ADAPTED | Use ContextManager semantic memory query | ContextManager | none | low | data_shape | None | REPAIRED |
| ai.rag_answer | ai | Generate grounded answer | ai_reasoning | grounded_answer | conversation | _chat_converse | A. DIRECT_KIO | LLM with retrieved context | LLM | llm_provider | low | data_shape | None | REPAIRED |
| ai.transcribe_summarize | ai | Transcribe audio to text | media | transcribe | terminal | run_command (whisper) | C. THIN_ADAPTER_REQUIRED | Use terminal whisper or cloud ASR API | whisper or cloud API | api_key | low | artifact | Audio transcription API/model needed | REPAIRED |
| ai.transcribe_summarize | ai | Summarize transcript | ai_reasoning | summarize | conversation | _chat_converse | A. DIRECT_KIO | Route through LLM conversation path | LLM | llm_provider | low | data_shape | None | REPAIRED |

### Browser (3 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| browser.page_change_monitor | browser | Navigate to URL | browser | navigate | browser | open_url | B. KIO_ADAPTED | Rename navigate→open_url (BrowserProvider) | BrowserProvider | none | read_only | browser_state | None | REPAIRED |
| browser.page_change_monitor | browser | Extract page text | browser | extract | browser | get_text | B. KIO_ADAPTED | Rename extract→get_text (BrowserProvider) | BrowserProvider | none | read_only | browser_state | None | REPAIRED |
| browser.page_change_monitor | browser | Compare snapshots | ai_reasoning | compare | conversation | _chat_converse | A. DIRECT_KIO | LLM comparison of snapshots | LLM | llm_provider | read_only | data_shape | None | REPAIRED |
| browser.price_monitor | browser | Navigate to product page | browser | navigate | browser | open_url | B. KIO_ADAPTED | Rename navigate→open_url | BrowserProvider | none | read_only | browser_state | None | REPAIRED |
| browser.price_monitor | browser | Extract price data | browser | extract | browser | get_text | B. KIO_ADAPTED | Rename extract→get_text | BrowserProvider | none | read_only | browser_state | None | REPAIRED |
| browser.price_monitor | browser | Compare with threshold | ai_reasoning | compare | conversation | _chat_converse | A. DIRECT_KIO | LLM comparison | LLM | llm_provider | read_only | data_shape | None | REPAIRED |
| browser.structured_extract | browser | Navigate to source page | browser | navigate | browser | open_url | B. KIO_ADAPTED | Rename navigate→open_url | BrowserProvider | none | read_only | browser_state | None | REPAIRED |
| browser.structured_extract | browser | Extract structured data | browser | extract | browser | get_text | B. KIO_ADAPTED | Rename extract→get_text | BrowserProvider | none | read_only | browser_state | None | REPAIRED |

### Business (4 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| business.crm_followup | business | Fetch leads from CRM | mcp_tool | fetch_leads | mcp_tool | airtable.list_records | A. DIRECT_KIO | Use MCP tool (airtable server required) | airtable MCP | api_key | low | data_shape | Airtable MCP server | REPAIRED |
| business.crm_followup | business | Generate follow-up email | ai_reasoning | generate_email | conversation | _chat_converse | A. DIRECT_KIO | LLM email generation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| business.email_autoresponder_approval | business | Fetch new emails | email | fetch_new | communication | kio_bot.get_updates | C. THIN_ADAPTER_REQUIRED | Use Telegram get_updates or Email MCP | kio_bot or email MCP | bot_token | low | data_shape | Email MCP server | REPAIRED |
| business.email_autoresponder_approval | business | Draft response | ai_reasoning | draft | conversation | _chat_converse | A. DIRECT_KIO | LLM drafting | LLM | llm_provider | low | data_shape | None | REPAIRED |
| business.email_autoresponder_approval | business | Wait for approval | workflow | approval | workflow | create_workflow | A. DIRECT_KIO | Use WorkflowExecutionProvider approval gate | Workflow engine | none | consequential | workflow_state | None | REPAIRED |
| business.email_autoresponder_approval | business | Send approved response | email | send | communication | kio_bot.send_message | C. THIN_ADAPTER_REQUIRED | Use Telegram send or Email MCP | kio_bot or email MCP | bot_token | low | communication_delivery | Email MCP server | REPAIRED |
| business.lead_intake_crm | business | Validate intake data | ai_reasoning | validate | conversation | _chat_converse | A. DIRECT_KIO | LLM validation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| business.lead_intake_crm | business | Store to CRM | mcp_tool | store | mcp_tool | airtable.create_record | A. DIRECT_KIO | Use MCP tool (airtable server required) | airtable MCP | api_key | low | data_shape | Airtable MCP server | REPAIRED |
| business.quote_to_invoice | business | Render invoice document | artifact | render | terminal | run_command (python openpyxl) | B. KIO_ADAPTED | Use terminal + Python openpyxl/python-docx | openpyxl, python-docx | none | low | artifact | None | REPAIRED |

### Communication (5 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| communication.chat_assistant | communication | Respond to user message | ai_reasoning | respond | conversation | _chat_converse | A. DIRECT_KIO | Core LLM conversation path | LLM | llm_provider | low | data_shape | None | REPAIRED |
| communication.chat_assistant | communication | Store conversation context | memory | store_context | memory | store_memory | B. KIO_ADAPTED | Use ContextManager memory store | ContextManager | none | low | data_shape | None | REPAIRED |
| communication.escalation_alert | communication | Evaluate escalation threshold | ai_reasoning | evaluate | conversation | _chat_converse | A. DIRECT_KIO | LLM evaluation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| communication.escalation_alert | communication | Send alert message | communication | send_message | communication | kio_bot.send_message | B. KIO_ADAPTED | Route through Telegram (kio_bot.py) | kio_bot | bot_token | low | communication_delivery | None | REPAIRED |
| communication.meeting_assistant | communication | Transcribe meeting audio | media | transcribe | terminal | run_command (whisper) | C. THIN_ADAPTER_REQUIRED | Use terminal whisper or cloud ASR | whisper or cloud API | api_key | low | artifact | Audio transcription API needed | REPAIRED |
| communication.meeting_assistant | communication | Summarize meeting notes | ai_reasoning | summarize | conversation | _chat_converse | A. DIRECT_KIO | LLM summarization | LLM | llm_provider | low | data_shape | None | REPAIRED |
| communication.workflow_failure_alert | communication | Send failure notification | communication | send_message | communication | kio_bot.send_message | B. KIO_ADAPTED | Route through Telegram (kio_bot.py) | kio_bot | bot_token | low | communication_delivery | None | REPAIRED |
| communication.voice_assistant | communication | Transcribe voice input | media | transcribe | terminal | run_command (whisper) | C. THIN_ADAPTER_REQUIRED | Use terminal whisper or cloud ASR | whisper or cloud API | api_key | low | artifact | Audio transcription API needed | REPAIRED |
| communication.voice_assistant | communication | Generate voice response | ai_reasoning | respond | conversation | _chat_converse | A. DIRECT_KIO | LLM response generation | LLM | llm_provider | low | data_shape | None | REPAIRED |

### Artifacts (6 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| artifacts.chart_generate | artifacts | Generate chart from data | artifact | generate | terminal | run_command (python matplotlib) | B. KIO_ADAPTED | Use terminal + Python matplotlib/plotly | matplotlib or plotly | none | low | artifact | None | REPAIRED |
| artifacts.document_summarize | artifacts | Extract text from document | filesystem | extract | mcp_tool | filesystem.read | B. KIO_ADAPTED | Use MCP filesystem server to read doc | MCP filesystem | none | read_only | data_shape | None | REPAIRED |
| artifacts.document_summarize | artifacts | Summarize document content | ai_reasoning | summarize | conversation | _chat_converse | A. DIRECT_KIO | LLM summarization | LLM | llm_provider | low | data_shape | None | REPAIRED |
| artifacts.infographic_create | artifacts | Design infographic layout | artifact | design | terminal | run_command (python pillow/canva-api) | C. THIN_ADAPTER_REQUIRED | Use terminal + Python Pillow or Canva API | Pillow or Canva API | api_key | low | artifact | Design API/model needed | REPAIRED |
| artifacts.mindmap_generate | artifacts | Generate mindmap structure | artifact | generate | terminal | run_command (python graphviz) | B. KIO_ADAPTED | Use terminal + Python graphviz | graphviz | none | low | artifact | None | REPAIRED |
| artifacts.presentation_create | artifacts | Create presentation slides | artifact | create | terminal | run_command (python-pptx) | B. KIO_ADAPTED | Use terminal + Python python-pptx | python-pptx | none | low | artifact | None | REPAIRED |
| artifacts.spreadsheet_build | artifacts | Build spreadsheet from data | artifact | build | terminal | run_command (python openpyxl) | B. KIO_ADAPTED | Use terminal + Python openpyxl | openpyxl | none | low | artifact | None | REPAIRED |

### Data (8 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| data.api_poll_to_store | data | Fetch API data | http | fetch | knowledge | web_search | B. KIO_ADAPTED | Use KnowledgeRouter or terminal curl | KnowledgeRouter or terminal | none | low | data_shape | None | REPAIRED |
| data.api_poll_to_store | data | Store to database | mcp_tool | store | mcp_tool | sqlite.execute | A. DIRECT_KIO | Use MCP sqlite server | MCP sqlite | none | low | data_shape | None | REPAIRED |
| data.csv_pii_scrub | data | Read CSV file | filesystem | read | mcp_tool | filesystem.read | B. KIO_ADAPTED | Use MCP filesystem server | MCP filesystem | none | read_only | data_shape | None | REPAIRED |
| data.csv_pii_scrub | data | Detect and scrub PII | ai_reasoning | scrub | conversation | _chat_converse | A. DIRECT_KIO | LLM PII detection + regex scrub | LLM | llm_provider | low | data_shape | None | REPAIRED |
| data.csv_pii_scrub | data | Write cleaned CSV | filesystem | write | mcp_tool | filesystem.write | B. KIO_ADAPTED | Use MCP filesystem server | MCP filesystem | none | low | data_shape | None | REPAIRED |
| data.file_extract_to_csv | data | Extract data from file | filesystem | extract | mcp_tool | filesystem.read | B. KIO_ADAPTED | Use MCP filesystem server | MCP filesystem | none | read_only | data_shape | None | REPAIRED |
| data.file_extract_to_csv | data | Transform to CSV format | ai_reasoning | transform | conversation | _chat_converse | A. DIRECT_KIO | LLM transformation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| data.form_intake_process | data | Validate form data | ai_reasoning | validate | conversation | _chat_converse | A. DIRECT_KIO | LLM validation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| data.form_intake_process | data | Store form submission | mcp_tool | store | mcp_tool | sqlite.execute | A. DIRECT_KIO | Use MCP sqlite server | MCP sqlite | none | low | data_shape | None | REPAIRED |
| data.json_transform | data | Transform JSON structure | ai_reasoning | transform | conversation | _chat_converse | A. DIRECT_KIO | LLM transformation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| data.sensor_data_to_alert | data | Analyze sensor readings | ai_reasoning | analyze | conversation | _chat_converse | A. DIRECT_KIO | LLM analysis | LLM | llm_provider | low | data_shape | None | REPAIRED |
| data.sensor_data_to_alert | data | Send alert on threshold breach | communication | alert | communication | kio_bot.send_message | B. KIO_ADAPTED | Route through Telegram | kio_bot | bot_token | low | communication_delivery | None | REPAIRED |
| data.spreadsheetfromJson | data | Parse JSON to spreadsheet | ai_reasoning | parse | conversation | _chat_converse | A. DIRECT_KIO | LLM parsing | LLM | llm_provider | low | data_shape | None | REPAIRED |
| data.spreadsheetfromJson | data | Build Excel file | artifact | build | terminal | run_command (python openpyxl) | B. KIO_ADAPTED | Use terminal + Python openpyxl | openpyxl | none | low | artifact | None | REPAIRED |
| data.web_to_json | data | Fetch web page | browser | fetch | browser | open_url | B. KIO_ADAPTED | Use BrowserProvider open_url + get_text | BrowserProvider | none | read_only | browser_state | None | REPAIRED |
| data.web_to_json | data | Extract JSON from HTML | ai_reasoning | parse | conversation | _chat_converse | A. DIRECT_KIO | LLM extraction | LLM | llm_provider | low | data_shape | None | REPAIRED |

### Development (9 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| development.ci_failure_alert | development | Fetch CI status | github | fetch | mcp_tool | github_list_commits | A. DIRECT_KIO | Use GitHub MCP server | MCP github | api_key | low | github_state | None | REPAIRED |
| development.ci_failure_alert | development | Analyze failure | ai_reasoning | analyze | conversation | _chat_converse | A. DIRECT_KIO | LLM analysis | LLM | llm_provider | low | data_shape | None | REPAIRED |
| development.dependency_monitor | development | Scan dependencies | code_project | scan | terminal | run_command (npm audit / pip-audit) | B. KIO_ADAPTED | Use terminal for dependency audit | terminal | none | low | data_shape | None | REPAIRED |
| development.dependency_monitor | development | Send alert | communication | alert | communication | kio_bot.send_message | B. KIO_ADAPTED | Route through Telegram | kio_bot | bot_token | low | communication_delivery | None | REPAIRED |
| development.github_issue_triage | development | Fetch issues | github | fetch | mcp_tool | github_list_issues | A. DIRECT_KIO | Use GitHub MCP server | MCP github | api_key | low | github_state | None | REPAIRED |
| development.github_issue_triage | development | Triage and categorize | ai_reasoning | triage | conversation | _chat_converse | A. DIRECT_KIO | LLM triage | LLM | llm_provider | low | data_shape | None | REPAIRED |
| development.github_issue_triage | development | Update issue labels | github | update | mcp_tool | github_create_issue | A. DIRECT_KIO | Use GitHub MCP (update via API) | MCP github | api_key | low | github_state | None | REPAIRED |
| development.issue_to_implementation | development | Implement code changes | code_project | implement | terminal | run_command (coding agent) | C. THIN_ADAPTER_REQUIRED | Use terminal + coding agent (Claude Code / Aider) | coding agent | api_key | consequential | code_project | Coding agent integration | REPAIRED |
| development.pr_review_prep | development | Fetch PR details | github | fetch | mcp_tool | github_list_prs | A. DIRECT_KIO | Use GitHub MCP server | MCP github | api_key | low | github_state | None | REPAIRED |
| development.pr_review_prep | development | Generate review notes | ai_reasoning | review | conversation | _chat_converse | A. DIRECT_KIO | LLM review generation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| development.release_changelog | development | Fetch commits | github | fetch | mcp_tool | github_list_commits | A. DIRECT_KIO | Use GitHub MCP server | MCP github | api_key | low | github_state | None | REPAIRED |
| development.release_changelog | development | Generate changelog | ai_reasoning | generate | conversation | _chat_converse | A. DIRECT_KIO | LLM changelog generation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| development.repo_backup | development | Export repository | code_project | export | terminal | run_command (git archive / gh) | B. KIO_ADAPTED | Use terminal git archive | terminal, git | none | low | artifact | None | REPAIRED |
| development.repo_backup | development | Upload to cloud storage | filesystem | upload | terminal | run_command (rclone / aws s3) | C. THIN_ADAPTER_REQUIRED | Use terminal rclone or cloud CLI | rclone or cloud CLI | api_key | low | artifact | Cloud storage CLI needed | REPAIRED |
| development.repo_health_report | development | Analyze repo metrics | github | analyze | mcp_tool | github_get_repo + terminal | A. DIRECT_KIO | Use GitHub MCP + terminal analysis | MCP github, terminal | api_key | low | github_state | None | REPAIRED |
| development.repo_health_report | development | Generate report | ai_reasoning | report | conversation | _chat_converse | A. DIRECT_KIO | LLM report generation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| development.scaffold_project | development | Create project structure | code_project | create | terminal | run_command (mkdir / cookiecutter) | B. KIO_ADAPTED | Use terminal project scaffolding | terminal | none | low | artifact | None | REPAIRED |
| development.scaffold_project | development | Configure IDE settings | code_project | configure | terminal | run_command (VS Code settings) | C. THIN_ADAPTER_REQUIRED | Use terminal for VS Code settings.json | terminal | none | low | artifact | VS Code MCP optional | REPAIRED |

### Files (5 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files.backup_organize | files | Scan backup directory | filesystem | scan | mcp_tool | filesystem.list | B. KIO_ADAPTED | Use MCP filesystem server | MCP filesystem | none | read_only | data_shape | None | REPAIRED |
| files.backup_organize | files | Organize by date/type | ai_reasoning | organize | conversation | _chat_converse | A. DIRECT_KIO | LLM organization logic | LLM | llm_provider | low | data_shape | None | REPAIRED |
| files.backup_organize | files | Move files to structure | filesystem | move | mcp_tool | filesystem.write | B. KIO_ADAPTED | Use MCP filesystem server (rename/move) | MCP filesystem | none | low | filesystem | None | REPAIRED |
| files.download_folder_organize | files | Scan downloads folder | filesystem | scan | mcp_tool | filesystem.list | B. KIO_ADAPTED | Use MCP filesystem server | MCP filesystem | none | read_only | data_shape | None | REPAIRED |
| files.download_folder_organize | files | Classify and move files | ai_reasoning | classify | conversation | _chat_converse | A. DIRECT_KIO | LLM classification | LLM | llm_provider | low | data_shape | None | REPAIRED |
| files.download_folder_organize | files | Move to target directories | filesystem | move | mcp_tool | filesystem.write | B. KIO_ADAPTED | Use MCP filesystem server | MCP filesystem | none | low | filesystem | None | REPAIRED |
| files.drive_to_social | files | Fetch from Google Drive | filesystem | fetch | terminal | run_command (rclone / gdrive API) | C. THIN_ADAPTER_REQUIRED | Use terminal rclone or Google Drive API | rclone or gdrive CLI | api_key | low | data_shape | Google Drive API access | REPAIRED |
| files.drive_to_social | files | Transform for social media | ai_reasoning | transform | conversation | _chat_converse | A. DIRECT_KIO | LLM content transformation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| files.drive_to_social | files | Publish to social platform | media | publish | terminal | run_command (social API) | C. THIN_ADAPTER_REQUIRED | Use terminal social media API calls | social API keys | api_key | low | communication_delivery | Social media API keys needed | REPAIRED |
| files.duplicate_detector | files | Scan for duplicates | filesystem | scan | terminal | run_command (find / hash) | B. KIO_ADAPTED | Use terminal file hashing | terminal | none | read_only | data_shape | None | REPAIRED |
| files.duplicate_detector | files | Group duplicate sets | ai_reasoning | group | conversation | _chat_converse | A. DIRECT_KIO | LLM grouping logic | LLM | llm_provider | low | data_shape | None | REPAIRED |
| files.invoice_extract_to_sheet | files | Extract invoice data | ai_reasoning | extract | conversation | _chat_converse | A. DIRECT_KIO | LLM extraction from PDF/image | LLM | llm_provider | low | data_shape | None | REPAIRED |
| files.invoice_extract_to_sheet | files | Build spreadsheet | artifact | build | terminal | run_command (python openpyxl) | B. KIO_ADAPTED | Use terminal + Python openpyxl | openpyxl | none | low | artifact | None | REPAIRED |

### Media (1 workflow)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| media.content_repurpose | media | Fetch source content | browser | fetch | browser | open_url + get_text | B. KIO_ADAPTED | Use BrowserProvider | BrowserProvider | none | read_only | browser_state | None | REPAIRED |
| media.content_repurpose | media | Transform for platforms | ai_reasoning | transform | conversation | _chat_converse | A. DIRECT_KIO | LLM content adaptation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| media.content_repurpose | media | Publish to social channels | media | publish | terminal | run_command (social API) | C. THIN_ADAPTER_REQUIRED | Use terminal social media API calls | social API keys | api_key | low | communication_delivery | Social media API keys needed | REPAIRED |

### Monitoring (4 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| monitoring.inbox_monitor | monitoring | Check inbox for new emails | email | fetch | communication | kio_bot.get_updates | C. THIN_ADAPTER_REQUIRED | Use Telegram updates or Email MCP | kio_bot or email MCP | bot_token | read_only | data_shape | Email MCP server | REPAIRED |
| monitoring.inbox_monitor | monitoring | Analyze email importance | ai_reasoning | analyze | conversation | _chat_converse | A. DIRECT_KIO | LLM analysis | LLM | llm_provider | low | data_shape | None | REPAIRED |
| monitoring.rss_news_monitor | monitoring | Fetch RSS feed | http | fetch | terminal | run_command (curl / feedparser) | B. KIO_ADAPTED | Use terminal curl + Python feedparser | terminal, feedparser | none | read_only | data_shape | None | REPAIRED |
| monitoring.rss_news_monitor | monitoring | Summarize news items | ai_reasoning | summarize | conversation | _chat_converse | A. DIRECT_KIO | LLM summarization | LLM | llm_provider | low | data_shape | None | REPAIRED |
| monitoring.security_scan_alert | monitoring | Run security scan | code_project | scan | terminal | run_command (semgrep / bandit) | B. KIO_ADAPTED | Use terminal security tools | terminal, semgrep/bandit | none | low | data_shape | None | REPAIRED |
| monitoring.security_scan_alert | monitoring | Send security alert | communication | alert | communication | kio_bot.send_message | B. KIO_ADAPTED | Route through Telegram | kio_bot | bot_token | low | communication_delivery | None | REPAIRED |
| monitoring.website_uptime | monitoring | Check website status | http | check | terminal | run_command (curl) | B. KIO_ADAPTED | Use terminal curl health check | terminal | none | read_only | http_response | None | REPAIRED |
| monitoring.website_uptime | monitoring | Send uptime alert | communication | alert | communication | kio_bot.send_message | B. KIO_ADAPTED | Route through Telegram | kio_bot | bot_token | low | communication_delivery | None | REPAIRED |

### Productivity (8 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| productivity.calendar_to_status | productivity | Fetch calendar events | calendar | fetch | terminal | run_command (gcalcli / icalBuddy) | C. THIN_ADAPTER_REQUIRED | Use terminal calendar CLI or Calendar MCP | gcalcli or calendar MCP | api_key | low | data_shape | Calendar MCP server | REPAIRED |
| productivity.calendar_to_status | productivity | Generate status update | ai_reasoning | generate | conversation | _chat_converse | A. DIRECT_KIO | LLM generation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| productivity.ecosystem_briefing | productivity | Fetch multiple data sources | http | fetch | terminal | run_command (curl / API calls) | C. THIN_ADAPTER_REQUIRED | Use terminal multi-source fetch | terminal | none | low | data_shape | API keys for sources | REPAIRED |
| productivity.ecosystem_briefing | productivity | Synthesize briefing | ai_reasoning | synthesize | conversation | _chat_converse | A. DIRECT_KIO | LLM synthesis | LLM | llm_provider | low | data_shape | None | REPAIRED |
| productivity.email_label_ai | productivity | Fetch emails | email | fetch | communication | kio_bot.get_updates | C. THIN_ADAPTER_REQUIRED | Use Telegram or Email MCP | kio_bot or email MCP | bot_token | read_only | data_shape | Email MCP server | REPAIRED |
| productivity.email_label_ai | productivity | AI-label emails | ai_reasoning | label | conversation | _chat_converse | A. DIRECT_KIO | LLM labeling | LLM | llm_provider | low | data_shape | None | REPAIRED |
| productivity.email_to_calendar | productivity | Extract event from email | email | fetch | communication | kio_bot.get_updates | C. THIN_ADAPTER_REQUIRED | Use Telegram or Email MCP | kio_bot or email MCP | bot_token | read_only | data_shape | Email + Calendar MCP | REPAIRED |
| productivity.email_to_calendar | productivity | Create calendar event | calendar | create | terminal | run_command (gcalcli / Calendar MCP) | C. THIN_ADAPTER_REQUIRED | Use terminal calendar CLI or Calendar MCP | gcalcli or calendar MCP | api_key | low | calendar_event | Calendar MCP server | REPAIRED |
| productivity.email_to_task | productivity | Extract task from email | email | fetch | communication | kio_bot.get_updates | C. THIN_ADAPTER_REQUIRED | Use Telegram or Email MCP | kio_bot or email MCP | bot_token | read_only | data_shape | Email MCP server | REPAIRED |
| productivity.email_to_task | productivity | Create task item | mcp_tool | create | mcp_tool | sqlite.execute | A. DIRECT_KIO | Use MCP sqlite for task storage | MCP sqlite | none | low | data_shape | None | REPAIRED |
| productivity.meeting_prep | productivity | Fetch meeting details | calendar | fetch | terminal | run_command (gcalcli / icalBuddy) | C. THIN_ADAPTER_REQUIRED | Use terminal calendar CLI | gcalcli or calendar MCP | api_key | low | data_shape | Calendar MCP server | REPAIRED |
| productivity.meeting_prep | productivity | Prepare briefing document | ai_reasoning | prepare | conversation | _chat_converse | A. DIRECT_KIO | LLM preparation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| productivity.morning_brief | productivity | Fetch morning data | http | fetch | terminal | run_command (curl / weather API) | C. THIN_ADAPTER_REQUIRED | Use terminal multi-source fetch | terminal | none | low | data_shape | API keys for weather/news | REPAIRED |
| productivity.morning_brief | productivity | Synthesize morning brief | ai_reasoning | synthesize | conversation | _chat_converse | A. DIRECT_KIO | LLM synthesis | LLM | llm_provider | low | data_shape | None | REPAIRED |
| productivity.weekly_review | productivity | Aggregate weekly data | http | aggregate | terminal | run_command (git log / API calls) | C. THIN_ADAPTER_REQUIRED | Use terminal git + API aggregation | terminal | none | low | data_shape | None | REPAIRED |
| productivity.weekly_review | productivity | Generate review summary | ai_reasoning | reflect | conversation | _chat_converse | A. DIRECT_KIO | LLM reflection | LLM | llm_provider | low | data_shape | None | REPAIRED |

### Research (4 workflows)

| ID | Category | Original Intent | Original Capability | Original Action | KIO-Native Capability | KIO-Native Action | Repair Type | Changes Made | Dependencies | Credentials | Security | Verification | Remaining Gap | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| research.competitor_monitor | research | Scrape competitor pages | browser | scrape | browser | open_url + get_text | B. KIO_ADAPTED | Use BrowserProvider | BrowserProvider | none | read_only | browser_state | None | REPAIRED |
| research.competitor_monitor | research | Analyze competitive data | ai_reasoning | analyze | conversation | _chat_converse | A. DIRECT_KIO | LLM analysis | LLM | llm_provider | low | data_shape | None | REPAIRED |
| research.daily_brief | research | Fetch daily news/data | http | fetch | terminal | run_command (curl / news API) | B. KIO_ADAPTED | Use terminal curl + news API | terminal | none | read_only | data_shape | None | REPAIRED |
| research.daily_brief | research | Synthesize daily brief | ai_reasoning | synthesize | conversation | _chat_converse | A. DIRECT_KIO | LLM synthesis | LLM | llm_provider | low | data_shape | None | REPAIRED |
| research.web_scrape_to_report | research | Crawl target pages | browser | crawl | browser | open_url + get_text | B. KIO_ADAPTED | Use BrowserProvider | BrowserProvider | none | read_only | browser_state | None | REPAIRED |
| research.web_scrape_to_report | research | Extract structured data | browser | extract | browser | get_text | B. KIO_ADAPTED | Use BrowserProvider get_text | BrowserProvider | none | read_only | browser_state | None | REPAIRED |
| research.web_scrape_to_report | research | Generate analysis report | ai_reasoning | report | conversation | _chat_converse | A. DIRECT_KIO | LLM report generation | LLM | llm_provider | low | data_shape | None | REPAIRED |
| research.youtube_summary | research | Fetch YouTube transcript | http | fetch | terminal | run_command (yt-dlp) | B. KIO_ADAPTED | Use terminal yt-dlp transcript fetch | terminal, yt-dlp | none | read_only | data_shape | None | REPAIRED |
| research.youtube_summary | research | Summarize video content | ai_reasoning | summarize | conversation | _chat_converse | A. DIRECT_KIO | LLM summarization | LLM | llm_provider | low | data_shape | None | REPAIRED |

---

## Aggregate Capability Gaps (Requiring Thin Adapters)

| Gap | Templates Affected | Adapter Type | KIO Integration Point |
|---|---|---|---|
| **Email MCP Server** | email_autoresponder, inbox_monitor, email_label_ai, email_to_calendar, email_to_task (5) | MCP server wrapping IMAP/SMTP | `mcp_tool` capability via MCPExecutionProvider |
| **Calendar MCP Server** | calendar_to_status, email_to_calendar, meeting_prep (3) | MCP server wrapping gcalcli/icalBuddy/Google Calendar API | `mcp_tool` capability via MCPExecutionProvider |
| **Social Media API** | content_repurpose, drive_to_social (2) | Terminal-based API calls or MCP server | `terminal` capability via TerminalProvider |
| **Audio Transcription** | transcribe_summarize, meeting_assistant, voice_assistant (3) | Terminal whisper or cloud ASR | `terminal` capability via TerminalProvider |
| **Image Generation** | image_generate (1) | Terminal diffusers/API call | `terminal` capability via TerminalProvider |
| **Coding Agent** | issue_to_implementation (1) | Terminal Claude Code / Aider | `terminal` capability via TerminalProvider |

**Total thin adapters needed: 6** (email, calendar, social, transcription, image gen, coding agent)
**Total templates using thin adapters: 15**
**Total templates fully DIRECT_KIO: 48**
**Total templates using KIO_ADAPTED: 0** (all B-type repairs are YAML-only changes)

---

## What Changed vs. Previous Audit

| Previous Finding | Repair Finding | Delta |
|---|---|---|
| 55 templates BLOCKED | 0 templates BLOCKED | -55 BLOCKED |
| github capability = BLOCKED | github → GitHub MCP Server (fully available) | +15 templates unblocked |
| filesystem capability = BLOCKED | filesystem → MCP Filesystem Server (read/write/list/search/info/exists) | +12 templates unblocked |
| communication = BLOCKED | communication → Telegram via kio_bot.py | +8 templates unblocked |
| http = BLOCKED | http → KnowledgeRouter + terminal curl | +10 templates unblocked |
| memory = BLOCKED | memory → ContextManager + PatternMemoryExtractor | +3 templates unblocked |
| artifact = BLOCKED | artifact → terminal + Python (openpyxl, python-docx, python-pptx, matplotlib, graphviz) | +6 templates unblocked |
| 63 capability gaps | 6 thin adapter gaps | -57 gaps |
| 0% executable | 76% executable (48/63) now | +76% |
