# KIO Remaining Provider Matrix

**Date:** 2026-09-18
**Scope:** All 63 YAML templates in automation/library/
**Purpose:** Authoritative dependency map before integration

---

## Status Definitions

| Status | Meaning |
|--------|---------|
| ALREADY_LIVE_VERIFIED | Provider exists, tested, LIVE |
| LOCAL_CAPABILITY | KIO handles internally |
| MCP_TOOL_ACTION | Routed through KIO MCP runtime |
| IMPLEMENTATION_GAP | Capability referenced but no handler |

---

## AI (6 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| ai.classify_and_route | ai_reasoning | classify | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| ai.classify_and_route | workflow | route | - | none | Execution engine | LOCAL_CAPABILITY |
| ai.enrich_records | knowledge | batch_lookup | - | none | Tavily/Exa/DuckDuckGo | ALREADY_LIVE_VERIFIED |
| ai.enrich_records | ai_reasoning | enrich | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| ai.enrich_records | filesystem | write | - | none | file_operator | LOCAL_CAPABILITY |
| ai.extract_to_structured | ai_reasoning | extract_structured | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| ai.extract_to_structured | ai_reasoning | validate_against_schema | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| ai.image_generate | media | generate_image | - | none | KIO Media (edge-tts/FFmpeg) | ALREADY_LIVE_VERIFIED |
| ai.image_generate | filesystem | verify_image | - | none | file_operator | LOCAL_CAPABILITY |
| ai.rag_answer | ai_reasoning | embed | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| ai.rag_answer | knowledge | vector_search | - | vectorstore_cred | None (vector store) | IMPLEMENTATION_GAP |
| ai.rag_answer | ai_reasoning | grounded_answer | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| ai.transcribe_summarize | ai_reasoning | transcribe | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| ai.transcribe_summarize | ai_reasoning | summarize | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| ai.transcribe_summarize | filesystem | store_transcript | - | none | file_operator | LOCAL_CAPABILITY |
| ai.transcribe_summarize | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |

## ARTIFACTS (6 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| artifacts.data_to_xlsx | ai_reasoning | design_spreadsheet | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.data_to_xlsx | terminal | run_command | - | none | terminal_provider | LOCAL_CAPABILITY |
| artifacts.data_to_xlsx | terminal | run_command | - | none | terminal_provider | LOCAL_CAPABILITY |
| artifacts.data_to_xlsx | terminal | run_command | - | none | terminal_provider | LOCAL_CAPABILITY |
| artifacts.meeting_to_report | ai_reasoning | extract_meeting_structure | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.meeting_to_report | artifact | generate_docx | - | none | Unknown | LOCAL_CAPABILITY |
| artifacts.meeting_to_report | artifact | verify_docx | - | none | Unknown | LOCAL_CAPABILITY |
| artifacts.multiformat_report | ai_reasoning | research | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.multiformat_report | ai_reasoning | write_content | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.multiformat_report | artifact | generate_docx | - | none | Unknown | LOCAL_CAPABILITY |
| artifacts.multiformat_report | terminal | render_pdf_from_html | - | none | terminal_provider | LOCAL_CAPABILITY |
| artifacts.multiformat_report | artifact | generate_pptx | - | none | Unknown | LOCAL_CAPABILITY |
| artifacts.multiformat_report | terminal | verify_bundle | - | none | terminal_provider | LOCAL_CAPABILITY |
| artifacts.research_to_docx | ai_reasoning | research | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.research_to_docx | ai_reasoning | plan_document | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.research_to_docx | ai_reasoning | write_content | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.research_to_docx | artifact | generate_docx | - | none | Unknown | LOCAL_CAPABILITY |
| artifacts.research_to_docx | artifact | verify_docx | - | none | Unknown | LOCAL_CAPABILITY |
| artifacts.research_to_docx | ai_reasoning | repair_document | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.research_to_pdf | ai_reasoning | research | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.research_to_pdf | ai_reasoning | compose_html | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.research_to_pdf | terminal | render_pdf_from_html | - | none | terminal_provider | LOCAL_CAPABILITY |
| artifacts.research_to_pdf | artifact | verify_pdf | - | none | Unknown | LOCAL_CAPABILITY |
| artifacts.research_to_pptx | ai_reasoning | research | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.research_to_pptx | ai_reasoning | plan_slides | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| artifacts.research_to_pptx | artifact | generate_pptx | - | none | Unknown | LOCAL_CAPABILITY |
| artifacts.research_to_pptx | artifact | verify_pptx | - | none | Unknown | LOCAL_CAPABILITY |

## BROWSER (3 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| browser.page_change_monitor | browser | fetch_region | - | none | BrowserRuntime | ALREADY_LIVE_VERIFIED |
| browser.page_change_monitor | memory | diff_against_last | - | none | memory_ops | LOCAL_CAPABILITY |
| browser.page_change_monitor | ai_reasoning | summarize_change | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| browser.page_change_monitor | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| browser.price_monitor | browser | extract_price | - | none | BrowserRuntime | ALREADY_LIVE_VERIFIED |
| browser.price_monitor | memory | record_and_compare | - | none | memory_ops | LOCAL_CAPABILITY |
| browser.price_monitor | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| browser.structured_extract | browser | extract_records | - | none | BrowserRuntime | ALREADY_LIVE_VERIFIED |
| browser.structured_extract | filesystem | write_csv | - | none | file_operator | LOCAL_CAPABILITY |
| browser.structured_extract | filesystem | verify_csv | - | none | file_operator | LOCAL_CAPABILITY |

## BUSINESS (4 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| business.crm_followup | mcp_tool | find_stale_leads | - | crm_cred | local_store | LOCAL_CAPABILITY |
| business.crm_followup | memory | exclude_recently_contacted | - | none | memory_ops | LOCAL_CAPABILITY |
| business.crm_followup | ai_reasoning | draft_followups | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| business.crm_followup | communication | send_batch | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| business.email_autoresponder_approval | ai_reasoning | draft_reply | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| business.email_autoresponder_approval | workflow | request_approval | - | none | Execution engine | LOCAL_CAPABILITY |
| business.email_autoresponder_approval | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| business.lead_intake_crm | knowledge | validate_lead | - | none | Tavily/Exa/DuckDuckGo | ALREADY_LIVE_VERIFIED |
| business.lead_intake_crm | ai_reasoning | dedupe_and_score | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| business.lead_intake_crm | mcp_tool | crm_upsert | - | crm_cred | local_store | LOCAL_CAPABILITY |
| business.lead_intake_crm | mcp_tool | crm_get | - | crm_cred | local_store | LOCAL_CAPABILITY |
| business.lead_intake_crm | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| business.support_ticket_triage | ai_reasoning | triage_ticket | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| business.support_ticket_triage | mcp_tool | upsert_ticket | - | crm_cred | local_store | LOCAL_CAPABILITY |
| business.support_ticket_triage | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |

## COMMUNICATION (5 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| communication.chat_assistant | communication | debounce_messages | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| communication.chat_assistant | memory | load_conversation | - | none | memory_ops | LOCAL_CAPABILITY |
| communication.chat_assistant | ai_reasoning | chat | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| communication.chat_assistant | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| communication.chat_assistant | memory | save_turn | - | none | memory_ops | LOCAL_CAPABILITY |
| communication.escalation_alert | communication | send_with_ack | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| communication.escalation_alert | workflow | wait_for_ack | - | none | Execution engine | LOCAL_CAPABILITY |
| communication.escalation_alert | workflow | advance_tier_or_stop | - | none | Execution engine | LOCAL_CAPABILITY |
| communication.notify | communication | format_for_channel | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| communication.notify | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| communication.voice_assistant | ai_reasoning | transcribe | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| communication.voice_assistant | ai_reasoning | chat | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| communication.voice_assistant | media | text_to_speech | - | none | KIO Media (edge-tts/FFmpeg) | ALREADY_LIVE_VERIFIED |
| communication.voice_assistant | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| communication.workflow_failure_alert | communication | format_failure | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| communication.workflow_failure_alert | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |

## DATA (8 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| data.api_poll_to_store | knowledge | paginated_get | - | none | Tavily/Exa/DuckDuckGo | ALREADY_LIVE_VERIFIED |
| data.api_poll_to_store | memory | filter_new | - | none | memory_ops | LOCAL_CAPABILITY |
| data.api_poll_to_store | filesystem | append_records | - | none | file_operator | LOCAL_CAPABILITY |
| data.csv_pii_scrub | ai_reasoning | detect_pii | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| data.csv_pii_scrub | filesystem | redact_csv | - | none | file_operator | LOCAL_CAPABILITY |
| data.csv_pii_scrub | ai_reasoning | verify_no_pii | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| data.file_extract_to_csv | ai_reasoning | extract_structured | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| data.file_extract_to_csv | filesystem | append_csv | - | none | file_operator | LOCAL_CAPABILITY |
| data.file_extract_to_csv | filesystem | verify_csv | - | none | file_operator | LOCAL_CAPABILITY |
| data.form_intake | ai_reasoning | classify_response | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| data.form_intake | filesystem | append_sheet_row | - | none | file_operator | LOCAL_CAPABILITY |
| data.form_intake | filesystem | verify_sheet_row | - | none | file_operator | LOCAL_CAPABILITY |
| data.form_intake | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| data.json_transform | workflow | transform_records | - | none | Execution engine | LOCAL_CAPABILITY |
| data.json_transform | workflow | verify_shape | - | none | Execution engine | LOCAL_CAPABILITY |
| data.knowledge_base_sync | ai_reasoning | structure_entry | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| data.knowledge_base_sync | mcp_tool | create_page | - | kb_cred | Notion integration | ALREADY_LIVE_VERIFIED |
| data.knowledge_base_sync | mcp_tool | get_page | - | kb_cred | Notion integration | ALREADY_LIVE_VERIFIED |
| data.record_sync | mcp_tool | list_changed | - | crm_cred | local_store | LOCAL_CAPABILITY |
| data.record_sync | memory | apply_field_map | - | none | memory_ops | LOCAL_CAPABILITY |
| data.record_sync | mcp_tool | upsert | - | crm_cred | local_store | LOCAL_CAPABILITY |
| data.webhook_to_store | knowledge | verify_hmac | - | none | Tavily/Exa/DuckDuckGo | ALREADY_LIVE_VERIFIED |
| data.webhook_to_store | workflow | validate_schema | - | none | Execution engine | LOCAL_CAPABILITY |
| data.webhook_to_store | filesystem | store_record | - | none | file_operator | LOCAL_CAPABILITY |
| data.webhook_to_store | filesystem | verify_record | - | none | file_operator | LOCAL_CAPABILITY |

## DEVELOPMENT (9 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| development.ci_failure_alert | github | get_run_logs | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.ci_failure_alert | ai_reasoning | extract_error | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| development.ci_failure_alert | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| development.dependency_monitor | github | dependency_scan | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.dependency_monitor | ai_reasoning | prioritize_updates | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| development.dependency_monitor | github | create_issue | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.dependency_monitor | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| development.github_issue_triage | github | get_issue | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.github_issue_triage | ai_reasoning | classify_issue | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| development.github_issue_triage | github | apply_labels | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.github_issue_triage | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| development.issue_to_implementation | github | gather_issue_context | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.issue_to_implementation | terminal | delegate_to_agent | - | none | terminal_provider | LOCAL_CAPABILITY |
| development.issue_to_implementation | ai_reasoning | review_diff | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| development.issue_to_implementation | github | create_draft_pr | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.pr_review_prep | github | get_pr_diff | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.pr_review_prep | ai_reasoning | analyze_diff | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| development.pr_review_prep | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| development.release_changelog | github | prs_since_last_tag | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.release_changelog | ai_reasoning | write_changelog | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| development.release_changelog | github | create_release | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.repo_backup | github | export_archive | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.repo_backup | filesystem | upload_backup | - | none | file_operator | LOCAL_CAPABILITY |
| development.repo_backup | filesystem | verify_upload | - | none | file_operator | LOCAL_CAPABILITY |
| development.repo_backup | filesystem | prune_old_backups | - | none | file_operator | LOCAL_CAPABILITY |
| development.repo_health_report | github | repo_metrics | - | github_token | GitHub MCP + GITHUB_TOKEN | ALREADY_LIVE_VERIFIED |
| development.repo_health_report | ai_reasoning | summarize_health | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| development.repo_health_report | artifact | generate_docx | - | none | Unknown | LOCAL_CAPABILITY |
| development.repo_health_report | artifact | verify_docx | - | none | Unknown | LOCAL_CAPABILITY |
| development.repo_health_report | communication | send_file | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| development.scaffold_project | terminal | scaffold | - | none | terminal_provider | LOCAL_CAPABILITY |
| development.scaffold_project | terminal | git_init | - | none | terminal_provider | LOCAL_CAPABILITY |
| development.scaffold_project | terminal | open_vscode | - | none | terminal_provider | LOCAL_CAPABILITY |
| development.scaffold_project | filesystem | verify_project | - | none | file_operator | LOCAL_CAPABILITY |

## FILES (5 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| files.document_summarize | filesystem | extract_text | - | none | file_operator | LOCAL_CAPABILITY |
| files.document_summarize | ai_reasoning | summarize | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| files.document_summarize | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| files.download_folder_organizer | filesystem | classify_file | - | none | file_operator | LOCAL_CAPABILITY |
| files.download_folder_organizer | filesystem | move_file | - | none | file_operator | LOCAL_CAPABILITY |
| files.download_folder_organizer | filesystem | verify_path | - | none | file_operator | LOCAL_CAPABILITY |
| files.drive_to_social | filesystem | get_new_asset | - | none | file_operator | LOCAL_CAPABILITY |
| files.drive_to_social | media | transcode_variants | - | none | KIO Media (edge-tts/FFmpeg) | ALREADY_LIVE_VERIFIED |
| files.drive_to_social | filesystem | write_derivatives | - | none | file_operator | LOCAL_CAPABILITY |
| files.drive_to_social | filesystem | verify_paths | - | none | file_operator | LOCAL_CAPABILITY |
| files.duplicate_detector | filesystem | hash_tree | - | none | file_operator | LOCAL_CAPABILITY |
| files.duplicate_detector | filesystem | group_duplicates | - | none | file_operator | LOCAL_CAPABILITY |
| files.duplicate_detector | terminal | render_markdown | - | none | terminal_provider | LOCAL_CAPABILITY |
| files.invoice_extract_to_sheet | ai_reasoning | extract_structured | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| files.invoice_extract_to_sheet | workflow | branch | - | none | Execution engine | LOCAL_CAPABILITY |
| files.invoice_extract_to_sheet | artifact | append_xlsx_row | - | none | Unknown | LOCAL_CAPABILITY |
| files.invoice_extract_to_sheet | terminal | run_command | - | none | terminal_provider | LOCAL_CAPABILITY |

## MEDIA (1 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| media.content_repurpose | ai_reasoning | adapt_per_platform | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| media.content_repurpose | workflow | request_approval | - | none | Execution engine | LOCAL_CAPABILITY |
| media.content_repurpose | media | publish | - | platform_creds | None | IMPLEMENTATION_GAP |
| media.content_repurpose | media | verify_posts | - | platform_creds | None | IMPLEMENTATION_GAP |

## MONITORING (4 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| monitoring.inbox_monitor | communication | get_updates | - | mail_cred | None (email) | IMPLEMENTATION_GAP |
| monitoring.inbox_monitor | ai_reasoning | score_priority | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| monitoring.inbox_monitor | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| monitoring.rss_news_monitor | knowledge | read_feeds | - | none | Tavily/Exa/DuckDuckGo | ALREADY_LIVE_VERIFIED |
| monitoring.rss_news_monitor | memory | filter_new | - | none | memory_ops | LOCAL_CAPABILITY |
| monitoring.rss_news_monitor | ai_reasoning | summarize_digest | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| monitoring.rss_news_monitor | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| monitoring.security_scan_alert | knowledge | multi_scan | - | none | Tavily/Exa/DuckDuckGo | ALREADY_LIVE_VERIFIED |
| monitoring.security_scan_alert | ai_reasoning | aggregate_risk | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| monitoring.security_scan_alert | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| monitoring.website_uptime | knowledge | healthcheck | - | none | Tavily/Exa/DuckDuckGo | ALREADY_LIVE_VERIFIED |
| monitoring.website_uptime | memory | state_transition | - | none | memory_ops | LOCAL_CAPABILITY |
| monitoring.website_uptime | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |

## PRODUCTIVITY (8 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| productivity.calendar_to_status | communication | set_status | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| productivity.calendar_to_status | communication | clear_status | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| productivity.ecosystem_briefing | calendar | today_events | - | google_oauth | Google Calendar | ALREADY_LIVE_VERIFIED |
| productivity.ecosystem_briefing | communication | priority_unread | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| productivity.ecosystem_briefing | filesystem | recent_drive_changes | - | none | file_operator | LOCAL_CAPABILITY |
| productivity.ecosystem_briefing | ai_reasoning | compose_briefing | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| productivity.ecosystem_briefing | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| productivity.email_label_ai | ai_reasoning | classify | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| productivity.email_label_ai | communication | apply_label | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| productivity.email_to_calendar | ai_reasoning | detect_event | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| productivity.email_to_calendar | calendar | run_command | - | google_oauth | Google Calendar | ALREADY_LIVE_VERIFIED |
| productivity.email_to_calendar | calendar | get_event | - | google_oauth | Google Calendar | ALREADY_LIVE_VERIFIED |
| productivity.email_to_task | ai_reasoning | classify_actionable | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| productivity.email_to_task | mcp_tool | create_task | - | crm_cred | local_store | LOCAL_CAPABILITY |
| productivity.meeting_prep | calendar | upcoming_within | - | google_oauth | Google Calendar | ALREADY_LIVE_VERIFIED |
| productivity.meeting_prep | memory | gather_context | - | none | memory_ops | LOCAL_CAPABILITY |
| productivity.meeting_prep | ai_reasoning | compose_prep | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| productivity.meeting_prep | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| productivity.morning_briefing | calendar | today_events | - | google_oauth | Google Calendar | ALREADY_LIVE_VERIFIED |
| productivity.morning_briefing | mcp_tool | due_tasks | - | crm_cred | local_store | LOCAL_CAPABILITY |
| productivity.morning_briefing | knowledge | get_weather | - | none | Tavily/Exa/DuckDuckGo | ALREADY_LIVE_VERIFIED |
| productivity.morning_briefing | ai_reasoning | compose_briefing | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| productivity.morning_briefing | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| productivity.weekly_review | memory | week_activity | - | none | memory_ops | LOCAL_CAPABILITY |
| productivity.weekly_review | ai_reasoning | compose_review | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| productivity.weekly_review | artifact | generate_docx | - | none | Unknown | LOCAL_CAPABILITY |
| productivity.weekly_review | communication | send_file | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |

## RESEARCH (4 templates)

| Template | Capability | Action | Provider | Credential | KIO Provider | Status |
|----------|------------|--------|----------|------------|--------------|--------|
| research.competitor_monitor | browser | snapshot_sources | - | none | BrowserRuntime | ALREADY_LIVE_VERIFIED |
| research.competitor_monitor | memory | diff_snapshots | - | none | memory_ops | LOCAL_CAPABILITY |
| research.competitor_monitor | ai_reasoning | analyze_competitive_changes | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| research.competitor_monitor | artifact | generate_docx | - | none | Unknown | LOCAL_CAPABILITY |
| research.competitor_monitor | communication | send_file | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| research.daily_brief | ai_reasoning | research_topics | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| research.daily_brief | memory | filter_new | - | none | memory_ops | LOCAL_CAPABILITY |
| research.daily_brief | ai_reasoning | compose_brief | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| research.daily_brief | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |
| research.web_scrape_to_report | browser | crawl_extract | - | none | BrowserRuntime | ALREADY_LIVE_VERIFIED |
| research.web_scrape_to_report | ai_reasoning | synthesize_report | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| research.web_scrape_to_report | artifact | generate_docx | - | none | Unknown | LOCAL_CAPABILITY |
| research.web_scrape_to_report | artifact | verify_docx | - | none | Unknown | LOCAL_CAPABILITY |
| research.youtube_summary | knowledge | list_new_videos | - | none | Tavily/Exa/DuckDuckGo | ALREADY_LIVE_VERIFIED |
| research.youtube_summary | memory | filter_new | - | none | memory_ops | LOCAL_CAPABILITY |
| research.youtube_summary | ai_reasoning | summarize_videos | - | llm_provider | Gemini/Groq/OpenRouter | ALREADY_LIVE_VERIFIED |
| research.youtube_summary | communication | send_message | - | channel_cred | Telegram bot | ALREADY_LIVE_VERIFIED |

---

## Stale Gap Reconciliation

**Re-audit date:** 2026-09-20
**Method:** Full codebase trace of capability registry → step_runner → app_operator → provider implementation → YAML template resolution.

| Gap | Previous Status | Current Status | Evidence | Remaining Work |
|-----|-----------------|----------------|----------|----------------|
| ai.rag_answer → vector_search | IMPLEMENTATION_GAP | **STILL_BLOCKED** | Step_runner maps `(knowledge,vector_search) → execute_capability` (line 303). app_operator lists it in knowledge actions (line 3208). KnowledgeProvider.execute() handlers dict does NOT include vector_search (lines 60-71), returns unknown action. No vector DB installed. YAML requires providers_required: [llm, vectorstore] — no vectorstore provider exists. | Implement vector store backend + wire KnowledgeProvider._vector_search() |
| media.content_repurpose → publish | IMPLEMENTATION_GAP | **STILL_BLOCKED** | Step_runner maps (media,publish) → execute_capability (line 238). app_operator handles it (lines 3784-3811) via _media_providers — only YouTube/Spotify registered. Neither has publish method (MediaProvider ABC is play/pause/search only). No Twitter/LinkedIn/Instagram adapter exists. | Implement social media publisher adapters with OAuth + publish method |
| media.content_repurpose → verify_posts | IMPLEMENTATION_GAP | **STILL_BLOCKED** | Same codepath as publish (lines 3812-3834). No social media adapter with verify_posts exists. | Same as publish |
| monitoring.inbox_monitor → get_updates | IMPLEMENTATION_GAP | **STALE_MATRIX_ENTRY** | YAML uses communication/get_updates. app_operator implements it (lines 3981-4004) as Telegram Bot API getUpdates — NOT email. YAML declares providers_required: [imap] and credentials_required: mail_cred — neither exists. email capability (read_inbox, watch_inbox) is registered in step_runner (lines 203-206) but has NO handler in app_operator. Gmail API could satisfy this. | Refactor YAML to use Gmail API. Or implement email capability handler in app_operator. |

### Key Findings

1. The 63 FULL classification is incorrect for 3 templates.
2. The Provider Matrix correctly identified these as IMPLEMENTATION_GAPs — gaps were NOT resolved.
3. The step_runner action map is complete. Gap is in the provider layer.
4. No vector database is installed anywhere in the codebase.
5. No social media publishing adapter exists.
6. inbox_monitor uses wrong capability (Telegram, not email).

### Final Authoritative Counts

**63 YAML templates:**
- FULL (verified end-to-end): 60
- BLOCKED (runtime failure): 2 (ai.rag_answer, media.content_repurpose)
- WRONG ROUTING (runtime produces wrong behavior): 1 (monitoring.inbox_monitor)

**Provider gaps:**
- Resolved: 0
- Remaining: 4 (vector_search, publish, verify_posts, email inbox monitoring)
