"""Step execution: runs individual automation steps through the KIO execution boundary."""

from __future__ import annotations

import logging
import time
from typing import Any

from mini_kio.automation.context import AutomationExecutionContext, StepResult

logger = logging.getLogger(__name__)


class StepRunner:
    """Executes individual automation steps through the KIO execution boundary.

    Every step in a YAML template has a (capability, action) pair. This runner:
    1. Resolves {{ }} references in step inputs
    2. Maps the (capability, action) pair to a KIO execution_boundary action
    3. Executes through execute_action() — the single entry point
    4. Returns a StepResult with outputs

    This is the ONLY path for side effects. No step can execute outside this runner.
    """

    # Mapping from (capability, action) to execution_boundary action names.
    # This is the bridge between YAML template semantics and KIO operator semantics.
    _ACTION_MAP: dict[tuple[str, str], str] = {
        # AI reasoning
        ("ai_reasoning", "classify"): "execute_capability",
        ("ai_reasoning", "classify_actionable"): "execute_capability",
        ("ai_reasoning", "classify_issue"): "execute_capability",
        ("ai_reasoning", "classify_response"): "execute_capability",
        ("ai_reasoning", "analyze"): "execute_capability",
        ("ai_reasoning", "analyze_competitive_changes"): "execute_capability",
        ("ai_reasoning", "analyze_diff"): "execute_capability",
        ("ai_reasoning", "summarize"): "execute_capability",
        ("ai_reasoning", "summarize_change"): "execute_capability",
        ("ai_reasoning", "summarize_digest"): "execute_capability",
        ("ai_reasoning", "summarize_health"): "execute_capability",
        ("ai_reasoning", "summarize_videos"): "execute_capability",
        ("ai_reasoning", "extract"): "execute_capability",
        ("ai_reasoning", "extract_error"): "execute_capability",
        ("ai_reasoning", "extract_meeting_structure"): "execute_capability",
        ("ai_reasoning", "extract_structured"): "execute_capability",
        ("ai_reasoning", "generate"): "execute_capability",
        ("ai_reasoning", "transform"): "execute_capability",
        ("ai_reasoning", "enrich"): "execute_capability",
        ("ai_reasoning", "reason"): "execute_capability",
        ("ai_reasoning", "adapt_per_platform"): "execute_capability",
        ("ai_reasoning", "aggregate_risk"): "execute_capability",
        ("ai_reasoning", "chat"): "execute_capability",
        ("ai_reasoning", "compose_brief"): "execute_capability",
        ("ai_reasoning", "compose_briefing"): "execute_capability",
        ("ai_reasoning", "compose_html"): "execute_capability",
        ("ai_reasoning", "compose_prep"): "execute_capability",
        ("ai_reasoning", "compose_review"): "execute_capability",
        ("ai_reasoning", "dedupe_and_score"): "execute_capability",
        ("ai_reasoning", "design_spreadsheet"): "execute_capability",
        ("ai_reasoning", "detect_event"): "execute_capability",
        ("ai_reasoning", "detect_pii"): "execute_capability",
        ("ai_reasoning", "draft_followups"): "execute_capability",
        ("ai_reasoning", "draft_reply"): "execute_capability",
        ("ai_reasoning", "embed"): "execute_capability",
        ("ai_reasoning", "grounded_answer"): "execute_capability",
        ("ai_reasoning", "plan_document"): "execute_capability",
        ("ai_reasoning", "plan_slides"): "execute_capability",
        ("ai_reasoning", "prioritize_updates"): "execute_capability",
        ("ai_reasoning", "repair_document"): "execute_capability",
        ("ai_reasoning", "research"): "execute_capability",
        ("ai_reasoning", "research_topics"): "execute_capability",
        ("ai_reasoning", "review_diff"): "execute_capability",
        ("ai_reasoning", "score_priority"): "execute_capability",
        ("ai_reasoning", "structure_entry"): "execute_capability",
        ("ai_reasoning", "synthesize_report"): "execute_capability",
        ("ai_reasoning", "transcribe"): "execute_capability",
        ("ai_reasoning", "triage_ticket"): "execute_capability",
        ("ai_reasoning", "validate_against_schema"): "execute_capability",
        ("ai_reasoning", "verify_no_pii"): "execute_capability",
        ("ai_reasoning", "write_changelog"): "execute_capability",
        ("ai_reasoning", "write_content"): "execute_capability",
        # Browser
        ("browser", "navigate"): "browser_goto",
        ("browser", "goto"): "browser_goto",
        ("browser", "click"): "browser_click",
        ("browser", "hover"): "browser_hover",
        ("browser", "scroll"): "browser_scroll",
        ("browser", "type"): "browser_type",
        ("browser", "fill"): "browser_fill",
        ("browser", "select"): "browser_select",
        ("browser", "screenshot"): "browser_screenshot",
        ("browser", "extract_text"): "browser_extract_text",
        ("browser", "extract_html"): "browser_extract_html",
        ("browser", "evaluate"): "browser_evaluate",
        ("browser", "extract_records"): "browser_extract_records",
        ("browser", "fetch_region"): "browser_fetch_region",
        ("browser", "crawl_extract"): "browser_crawl_extract",
        ("browser", "snapshot_sources"): "browser_snapshot_sources",
        ("browser", "extract_price"): "browser_extract_price",
        ("browser", "monitor_page"): "execute_capability",
        ("browser", "check_change"): "execute_capability",
        ("browser", "check_price"): "browser_extract_price",
        # Filesystem — mapped to new boundary actions
        ("filesystem", "write_csv"): "write_csv",
        ("filesystem", "append_csv"): "execute_capability",
        ("filesystem", "verify_csv"): "execute_capability",
        ("filesystem", "write_file"): "write_csv",
        ("filesystem", "write"): "write_csv",
        ("filesystem", "append_records"): "execute_capability",
        ("filesystem", "append_sheet_row"): "execute_capability",
        ("filesystem", "redact_csv"): "execute_capability",
        ("filesystem", "store_transcript"): "execute_capability",
        ("filesystem", "upload_backup"): "write_csv",
        ("filesystem", "write_derivatives"): "write_csv",
        ("filesystem", "read_file"): "read_file",
        ("filesystem", "extract_text"): "execute_capability",
        ("filesystem", "get_new_asset"): "read_file",
        ("filesystem", "list_files"): "list_files",
        ("filesystem", "list_directory"): "list_files",
        ("filesystem", "recent_drive_changes"): "list_files",
        ("filesystem", "move_file"): "move_file",
        ("filesystem", "prune_old_backups"): "execute_capability",
        ("filesystem", "classify_file"): "execute_capability",
        ("filesystem", "verify_path"): "execute_capability",
        ("filesystem", "verify_paths"): "fs_exists",
        ("filesystem", "verify_image"): "execute_capability",
        ("filesystem", "verify_project"): "execute_capability",
        ("filesystem", "verify_sheet_row"): "execute_capability",
        ("filesystem", "verify_upload"): "fs_exists",
        ("filesystem", "hash_tree"): "hash_tree",
        ("filesystem", "hash_file"): "hash_file",
        ("filesystem", "detect_duplicates"): "hash_tree",
        ("filesystem", "group_duplicates"): "execute_capability",
        ("filesystem", "store_record"): "store_record",
        ("filesystem", "verify_record"): "execute_capability",
        ("filesystem", "organize_files"): "move_file",
        # Communication
        ("communication", "send_message"): "execute_capability",
        ("communication", "send_with_ack"): "execute_capability",
        ("communication", "send_batch"): "execute_capability",
        ("communication", "send_file"): "execute_capability",
        ("communication", "format_for_channel"): "execute_capability",
        ("communication", "format_failure"): "execute_capability",
        ("communication", "send_notification"): "execute_capability",
        ("communication", "send_alert"): "execute_capability",
        ("communication", "apply_label"): "execute_capability",
        ("communication", "clear_status"): "execute_capability",
        ("communication", "set_status"): "execute_capability",
        ("communication", "debounce_messages"): "execute_capability",
        ("communication", "get_updates"): "execute_capability",
        ("communication", "priority_unread"): "execute_capability",
        # GitHub
        ("github", "get_pr_diff"): "execute_capability",
        ("github", "list_issues"): "execute_capability",
        ("github", "create_issue"): "execute_capability",
        ("github", "create_draft_pr"): "execute_capability",
        ("github", "get_repo_info"): "execute_capability",
        ("github", "get_issue"): "execute_capability",
        ("github", "get_run_logs"): "execute_capability",
        ("github", "apply_labels"): "execute_capability",
        ("github", "backup_repo"): "execute_capability",
        ("github", "scan_dependencies"): "execute_capability",
        ("github", "create_release"): "execute_capability",
        ("github", "dependency_scan"): "execute_capability",
        ("github", "export_archive"): "execute_capability",
        ("github", "gather_issue_context"): "execute_capability",
        ("github", "prs_since_last_tag"): "execute_capability",
        ("github", "repo_metrics"): "execute_capability",
        # Workflow
        ("workflow", "transform_records"): "execute_capability",
        ("workflow", "verify_shape"): "execute_capability",
        ("workflow", "route"): "execute_capability",
        ("workflow", "aggregate"): "execute_capability",
        ("workflow", "filter"): "execute_capability",
        ("workflow", "conditional_branch"): "execute_capability",
        ("workflow", "branch"): "execute_capability",
        ("workflow", "request_approval"): "execute_capability",
        ("workflow", "validate_schema"): "execute_capability",
        ("workflow", "advance_tier_or_stop"): "execute_capability",
        ("workflow", "wait_for_ack"): "execute_capability",
        # Monitoring
        ("monitoring", "check_rss"): "execute_capability",
        ("monitoring", "check_website"): "execute_capability",
        ("monitoring", "check_inbox"): "execute_capability",
        ("monitoring", "run_scan"): "execute_capability",
        ("monitoring", "check_uptime"): "execute_capability",
        # Artifact
        ("artifact", "generate_pdf"): "execute_capability",
        ("artifact", "generate_docx"): "execute_capability",
        ("artifact", "generate_pptx"): "execute_capability",
        ("artifact", "generate_xlsx"): "execute_capability",
        ("artifact", "generate_html"): "execute_capability",
        ("artifact", "verify_docx"): "execute_capability",
        ("artifact", "verify_pdf"): "execute_capability",
        ("artifact", "verify_pptx"): "execute_capability",
        ("artifact", "append_xlsx_row"): "execute_capability",
        # Data
        ("data", "read_source"): "execute_capability",
        ("data", "transform"): "execute_capability",
        ("data", "write_store"): "execute_capability",
        ("data", "validate_shape"): "execute_capability",
        # Email
        ("email", "read_inbox"): "execute_capability",
        ("email", "send_email"): "execute_capability",
        ("email", "apply_label"): "execute_capability",
        ("email", "watch_inbox"): "execute_capability",
        # Calendar
        ("calendar", "list_events"): "execute_capability",
        ("calendar", "create_event"): "execute_capability",
        ("calendar", "get_todays_events"): "execute_capability",
        ("calendar", "get_event"): "execute_capability",
        ("calendar", "run_command"): "execute_capability",
        ("calendar", "today_events"): "execute_capability",
        ("calendar", "upcoming_within"): "execute_capability",
        ("calendar", "upcoming"): "execute_capability",
        # Google Calendar backend actions (selected via backend=google)
        ("calendar", "list_calendars"): "execute_capability",
        ("calendar", "update_event"): "execute_capability",
        ("calendar", "delete_event"): "execute_capability",
        ("calendar", "search_events"): "execute_capability",
        # Google Drive (cloud-storage backend)
        ("drive", "list_files"): "execute_capability",
        ("drive", "search_files"): "execute_capability",
        ("drive", "get_metadata"): "execute_capability",
        ("drive", "create_folder"): "execute_capability",
        ("drive", "upload_file"): "execute_capability",
        ("drive", "download_file"): "execute_capability",
        ("drive", "rename_file"): "execute_capability",
        ("drive", "move_file"): "execute_capability",
        ("drive", "delete_file"): "execute_capability",
        # Google People API (contacts)
        ("contacts", "list_contacts"): "execute_capability",
        ("contacts", "list"): "execute_capability",
        ("contacts", "search_contacts"): "execute_capability",
        ("contacts", "search"): "execute_capability",
        ("contacts", "get_contact"): "execute_capability",
        ("contacts", "create_contact"): "execute_capability",
        ("contacts", "create"): "execute_capability",
        ("contacts", "update_contact"): "execute_capability",
        ("contacts", "update"): "execute_capability",
        ("contacts", "delete_contact"): "execute_capability",
        # Google Photos (supported surface + Picker API)
        ("photos", "list_albums"): "execute_capability",
        ("photos", "get_album"): "execute_capability",
        ("photos", "create_album"): "execute_capability",
        ("photos", "list_media"): "execute_capability",
        ("photos", "search_media"): "execute_capability",
        ("photos", "get_media"): "execute_capability",
        ("photos", "upload_media"): "execute_capability",
        ("photos", "create_picker_session"): "execute_capability",
        ("photos", "list_picked_items"): "execute_capability",
        # Memory
        ("memory", "store"): "execute_capability",
        ("memory", "retrieve"): "execute_capability",
        ("memory", "log_event"): "execute_capability",
        ("memory", "apply_field_map"): "execute_capability",
        ("memory", "diff_against_last"): "execute_capability",
        ("memory", "diff_snapshots"): "execute_capability",
        ("memory", "exclude_recently_contacted"): "execute_capability",
        ("memory", "filter_new"): "execute_capability",
        ("memory", "gather_context"): "execute_capability",
        ("memory", "load_conversation"): "execute_capability",
        ("memory", "record_and_compare"): "execute_capability",
        ("memory", "save_turn"): "execute_capability",
        ("memory", "state_transition"): "execute_capability",
        ("memory", "week_activity"): "execute_capability",
        # HTTP
        ("http", "fetch"): "execute_capability",
        ("http", "poll"): "execute_capability",
        ("http", "post"): "execute_capability",
        # Media
        ("media", "transcribe"): "execute_capability",
        ("media", "generate_image"): "execute_capability",
        ("media", "process_video"): "execute_capability",
        ("media", "publish"): "execute_capability",
        ("media", "text_to_speech"): "execute_capability",
        ("media", "transcode_variants"): "execute_capability",
        ("media", "verify_posts"): "execute_capability",
        # Code project
        ("code_project", "scaffold"): "execute_capability",
        ("code_project", "run_tests"): "execute_capability",
        ("code_project", "lint"): "execute_capability",
        # MCP tool
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
        # Local store (task tracker, CRM, tickets)
        ("local_store", "task_create"): "execute_capability",
        ("local_store", "create_task"): "execute_capability",
        ("local_store", "task_list"): "execute_capability",
        ("local_store", "list_tasks"): "execute_capability",
        ("local_store", "task_update"): "execute_capability",
        ("local_store", "update_task"): "execute_capability",
        ("local_store", "task_complete"): "execute_capability",
        ("local_store", "complete_task"): "execute_capability",
        ("local_store", "task_delete"): "execute_capability",
        ("local_store", "delete_task"): "execute_capability",
        ("local_store", "task_search"): "execute_capability",
        ("local_store", "crm_add"): "execute_capability",
        ("local_store", "add_contact"): "execute_capability",
        ("local_store", "crm_list"): "execute_capability",
        ("local_store", "list_contacts"): "execute_capability",
        ("local_store", "crm_search"): "execute_capability",
        ("local_store", "crm_update"): "execute_capability",
        ("local_store", "update_contact"): "execute_capability",
        ("local_store", "ticket_create"): "execute_capability",
        ("local_store", "create_ticket"): "execute_capability",
        ("local_store", "ticket_list"): "execute_capability",
        ("local_store", "list_tickets"): "execute_capability",
        ("local_store", "ticket_update"): "execute_capability",
        ("local_store", "update_ticket"): "execute_capability",
        ("local_store", "ticket_comment"): "execute_capability",
        ("local_store", "ticket_close"): "execute_capability",
        ("local_store", "close_ticket"): "execute_capability",
        # Knowledge (RAG/KB queries) — now routed to dedicated KnowledgeProvider actions
        ("knowledge", "web_search"): "web_search",
        ("knowledge", "fetch_url"): "fetch_url",
        ("knowledge", "fetch_wikipedia"): "fetch_wikipedia",
        ("knowledge", "healthcheck"): "healthcheck",
        ("knowledge", "list_new_videos"): "list_new_videos",
        ("knowledge", "read_feeds"): "read_feeds",
        ("knowledge", "paginated_get"): "paginated_get",
        ("knowledge", "verify_hmac"): "verify_hmac",
        ("knowledge", "query"): "web_search",
        ("knowledge", "search"): "web_search",
        ("knowledge", "retrieve"): "fetch_url",
        ("knowledge", "sync"): "execute_capability",
        ("knowledge", "get_weather"): "execute_capability",
        ("knowledge", "validate_lead"): "execute_capability",
        # Fallback knowledge -> web_search for unrecognized actions
        ("knowledge", "batch_lookup"): "web_search",
        ("knowledge", "vector_search"): "execute_capability",
        ("knowledge", "multi_scan"): "web_search",
        # Terminal (code execution)
        ("terminal", "run"): "execute_capability",
        ("terminal", "execute"): "execute_capability",
        ("terminal", "scaffold"): "execute_capability",
        ("terminal", "backup"): "execute_capability",
        ("terminal", "health_check"): "execute_capability",
        ("terminal", "scan"): "execute_capability",
        ("terminal", "create_release"): "execute_capability",
        ("terminal", "extract"): "execute_capability",
        ("terminal", "generate"): "execute_capability",
        ("artifact", "append_xlsx_row"): "execute_capability",
        ("terminal", "delegate_to_agent"): "execute_capability",
        ("terminal", "git_init"): "execute_capability",
        ("terminal", "open_vscode"): "execute_capability",
        ("terminal", "render_docx"): "execute_capability",
        ("terminal", "render_markdown"): "execute_capability",
        ("terminal", "render_pdf_from_html"): "execute_capability",
        ("terminal", "render_pptx"): "execute_capability",
        ("terminal", "run_command"): "execute_capability",
        ("terminal", "clipboard_copy"): "execute_capability",
        ("terminal", "clipboard_paste"): "execute_capability",
        ("terminal", "verify_bundle"): "execute_capability",
        ("terminal", "verify_docx"): "execute_capability",
        ("terminal", "verify_pdf"): "execute_capability",
        ("terminal", "verify_pptx"): "execute_capability",
    }

    def execute_step(
        self,
        step: dict[str, Any],
        ctx: AutomationExecutionContext,
    ) -> StepResult:
        """Execute a single automation step.

        Resolves references, executes through the boundary, returns result.
        """
        step_id = step["id"]
        capability = step.get("capability", "")
        action = step.get("action", "")
        inputs = step.get("inputs", {})
        on_error = step.get("on_error", {})
        max_retries = on_error.get("retry", {}).get("max", 0)

        # Resolve {{ }} references in inputs
        resolved_inputs = ctx.resolve_value(inputs)

        # Map to execution_boundary action
        boundary_action = self._ACTION_MAP.get((capability, action), "execute_capability")

        # Build the target string for execute_action
        target = self._build_target(capability, action, resolved_inputs)

        last_error = None
        for attempt in range(1 + max_retries):
            start = time.time()
            try:
                result = self._call_boundary(boundary_action, target, resolved_inputs, capability, action)
                elapsed = (time.time() - start) * 1000

                if result.get("success"):
                    # Extract outputs from the result
                    outputs = self._extract_outputs(step, result, ctx)
                    return StepResult(
                        step_id=step_id,
                        success=True,
                        outputs=outputs,
                        elapsed_ms=elapsed,
                        retry_count=attempt,
                    )
                else:
                    last_error = result.get("message", "Step failed")
                    if attempt < max_retries:
                        logger.warning(
                            "[STEP_RUNNER] step %s attempt %d failed: %s, retrying",
                            step_id, attempt + 1, last_error,
                        )
                        continue
                    return StepResult(
                        step_id=step_id,
                        success=False,
                        error=last_error,
                        elapsed_ms=elapsed,
                        retry_count=attempt,
                        blocked=result.get("blocked", False),
                        blocking_reason=result.get("message"),
                    )

            except Exception as exc:
                elapsed = (time.time() - start) * 1000
                last_error = str(exc)
                if attempt < max_retries:
                    logger.warning(
                        "[STEP_RUNNER] step %s attempt %d exception: %s, retrying",
                        step_id, attempt + 1, last_error,
                    )
                    continue
                return StepResult(
                    step_id=step_id,
                    success=False,
                    error=last_error,
                    elapsed_ms=elapsed,
                    retry_count=attempt,
                )

        return StepResult(
            step_id=step_id,
            success=False,
            error=last_error or "Exhausted retries",
            retry_count=max_retries,
        )

    def _call_boundary(
        self,
        action: str,
        target: str,
        inputs: dict[str, Any],
        capability: str,
        step_action: str,
    ) -> dict[str, Any]:
        """Call the KIO execution boundary, passing inputs as kwargs.

        Priority:
        1. ProviderRegistry — if a provider declares the step_action, delegate
           directly.  This covers ai_reasoning, memory, workflow, communication,
           artifact, github, terminal, code_project, browser, mcp_tool, media,
           http, and all Google services.
        2. Execution boundary execute_capability — for app_operator-routed
           capabilities (spotify, chrome, youtube, etc.).
        3. Direct filesystem/knowledge kwargs pass-through.
        """
        try:
            from mini_kio.core.provider_registry import get_provider_registry
            registry = get_provider_registry()

            # 1. Try provider registry first (covers most workflow actions)
            provider = registry.get_provider(step_action)
            if provider is None:
                provider = registry.get_provider(capability)
            if provider is not None:
                try:
                    return provider.execute(step_action, target=target, **inputs)
                except Exception as exc:
                    return {"success": False, "message": f"{capability}.{step_action} failed: {exc}"}

            # 2. Fall back to execution_boundary execute_capability
            from mini_kio.core.execution_boundary import execute_action
            if capability in ("filesystem", "knowledge"):
                return execute_action(action, target, **inputs)
            if action == "execute_capability":
                import json
                target = f"{capability}::{step_action}::{json.dumps(inputs)}"
            return execute_action(action, target)
        except Exception as exc:
            return {"success": False, "message": f"Execution boundary error: {exc}"}

    def _build_target(
        self, capability: str, action: str, inputs: dict[str, Any]
    ) -> str:
        """Build the target string for execute_action based on capability and inputs."""
        # For browser actions, target is typically the URL
        if capability == "browser":
            return str(inputs.get("url", inputs.get("target", "")))
        # For communication, target is the channel
        if capability == "communication":
            return str(inputs.get("channel", inputs.get("target", "")))
        # For github, target is repo
        if capability == "github":
            return str(inputs.get("repo", inputs.get("target", "")))
        # For knowledge actions, target is query/url
        if capability == "knowledge":
            return str(inputs.get("query", inputs.get("url", inputs.get("target", ""))))
        # Default: first string input value or action name
        for v in inputs.values():
            if isinstance(v, str) and v:
                return v
        return action

    def _extract_outputs(
        self,
        step: dict[str, Any],
        result: dict[str, Any],
        ctx: AutomationExecutionContext,
    ) -> dict[str, Any]:
        """Extract declared outputs from the step result.

        Maps the step's declared output names to actual values from the
        execution boundary result.
        """
        declared_outputs = step.get("outputs", [])
        outputs: dict[str, Any] = {}

        # The execution boundary returns data in 'data', 'result', or top-level keys
        result_data = result.get("data", result.get("result", result))

        for out_name in declared_outputs:
            if isinstance(result_data, dict) and out_name in result_data:
                outputs[out_name] = result_data[out_name]
            elif out_name in result:
                outputs[out_name] = result[out_name]
            else:
                # Try to find a reasonable default
                outputs[out_name] = None

        return outputs
