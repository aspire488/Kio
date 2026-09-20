# KIO Phase 7 — Provider Status Table
# Generated: 2026-09-18

## Provider Capability Matrix

| Provider | Module | Actions | Status | Auth Required |
|----------|--------|---------|--------|---------------|
| **Memory Ops** | memory_ops.py | filter_new, week_activity, exclude_recently_contacted, apply_field_map, diff_snapshots, state_transition | ✅ REAL | None (local JSON) |
| **Communication** | app_operator.py | send_with_ack, get_updates, priority_unread | ✅ REAL | TELEGRAM_TOKEN |
| **Media (TTS)** | media_ops.py | text_to_speech | ✅ REAL | None (edge-tts) |
| **Media (Transcode)** | media_ops.py | transcode_variants | ✅ REAL | None (ffmpeg) |
| **Calendar** | calendar_ops.py | today_events, upcoming_within, create_event, get_event, list_events | ✅ REAL | None (ICS local) |
| **Task Tracker** | local_store.py | task_create, task_list, task_update, task_complete, task_delete, task_search | ✅ REAL | None (local JSON) |
| **CRM** | local_store.py | crm_add, crm_list, crm_search, crm_update | ✅ REAL | None (local JSON) |
| **Tickets** | local_store.py | ticket_create, ticket_list, ticket_update, ticket_comment, ticket_close | ✅ REAL | None (local JSON) |
| **GitHub API** | mcp_github_server.py | 21 tools (search, issues, PRs, releases, etc.) | ✅ REAL | GITHUB_TOKEN |
| **Telegram Bot** | runtime.py / execution_boundary.py | send_message, getUpdates | ✅ REAL | TELEGRAM_TOKEN |
| **AI Reasoning** | llm_ops.py | 39 actions (classify, summarize, extract, etc.) | ✅ REAL | GEMINI/GROQ/OPENROUTER |
| **Workflow Engine** | workflow_provider.py | 9 actions (route, branch, approval, etc.) | ✅ REAL | None |
| **Knowledge/RAG** | knowledge_provider.py | 10 actions (web_search, fetch, etc.) | ✅ REAL | TAVILY/EXA keys |
| **Browser** | browser_provider.py | goto, click, scroll, screenshot, etc. | ✅ REAL | None (Playwright) |
| **Filesystem** | file_operator.py | 24 actions (read, write, hash, verify, etc.) | ✅ REAL | None (local) |
| **Terminal** | terminal_provider.py | 20 actions (run, scaffold, scan, etc.) | ✅ REAL | None (local) |
| **Google Calendar** | — | today_events, upcoming_within, get_event, create_event | ⏳ BLOCKED | GOOGLE_OAUTH_CLIENT_ID/SECRET |
| **Google Drive** | — | list_files, download, upload | ⏳ BLOCKED | GOOGLE_OAUTH_CLIENT_ID/SECRET |
| **YouTube Publish** | youtube_provider.py | publish, verify_posts | ⏳ BLOCKED | YOUTUBE_CLIENT_ID/SECRET |
| **Notion** | — | create_page, get_page | ⏳ BLOCKED | NOTION_API_KEY |
| **Todoist** | — | create_task, due_tasks | ⏳ BLOCKED | TODOIST_API_TOKEN |

## Summary

- **REAL providers**: 17 (all local/credential-backed, verified)
- **BLOCKED providers**: 5 (need user-provided OAuth/API credentials)
- **Total capability actions**: ~164 unique (cap, action) pairs
- **Provider health**: 10/10 active providers pass health check

## What's Needed to Unblock

See `KIO_PHASE7_PROVIDER_SETUP.md` for step-by-step credential setup for:
- Google Calendar + Drive (OAuth Desktop credentials)
- YouTube Data API v3 (OAuth)
- Notion (Integration token)
- Todoist (API token)
