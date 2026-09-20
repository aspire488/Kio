"""Serial Telegram E2E test runner for all 63 KIO workflows.

Uses dispatch_channel_input — the exact function that kio_bot.py's
handle_message calls — so every test exercises the full Telegram code path:

    Telegram message  ->  dispatch_channel_input  ->  Pipeline  ->
    ExecutionCoordinator  ->  providers  ->  verification  ->  formatted reply

Workflows run ONE AT A TIME (never concurrently) to avoid:
  - Telegram rate limits
  - LLM provider quota saturation across providers
  - Race conditions in shared runtime state

Usage:
    python _tg_e2e_serial.py [--start=N] [--count=N] [--workflow=CATEGORY]
"""
import sys
import os
import json
import time
import argparse
import traceback

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, '.')

from mini_kio.core.config import TELEGRAM_TOKEN, ALLOWED_USER_IDS
from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input, format_channel_reply

USER_ID = ALLOWED_USER_IDS[0] if ALLOWED_USER_IDS else 2146008061

# ── Natural-language commands mapped to each workflow ───────────────
# Only workflows that can be triggered by a natural-language command are listed.
# Workflows requiring structured inputs use engine.execute() directly (still via
# the bootstrapped runtime, just the AutomationEngine entry point).
NL_COMMANDS = {
    "ai.classify_and_route": "Please update billing address from email",
    "ai.enrich_records": "Enrich the record for Acme Corp with domain acme.com",
    "ai.extract_to_structured": "Extract from: John Smith, CEO, Acme Corp, john@acme.com, deal worth $50000",
    "ai.image_generate": "Generate an image of a simple blue circle on white background",
    "ai.rag_answer": "What is KIO?",
    "ai.transcribe_summarize": "Transcribe and summarize the audio in test_audio.wav",
    "artifacts.data_to_xlsx": "Write test data name:Test,value:42 to an xlsx file",
    "artifacts.meeting_to_report": "Create a meeting report from: Q4 planning discussed budget, timeline, resources. Action: update roadmap",
    "artifacts.multiformat_report": "Create a report from: Revenue $1.2M, 15% growth, 500 customers in docx and pdf",
    "artifacts.research_to_docx": "Research artificial intelligence trends 2026 and write a docx report",
    "artifacts.research_to_pdf": "Research renewable energy basics and create a pdf report",
    "artifacts.research_to_pptx": "Research cloud computing overview and create a pptx presentation",
    "browser.page_change_monitor": "Monitor example.com for changes to the h1 element every 60 minutes",
    "browser.price_monitor": "Monitor the price of a product at example.com/product, alert below $100",
    "browser.structured_extract": "Extract structured data from https://example.com/data to ~/KIO/test_output/extracted.csv",
    "business.crm_followup": "Send a CRM followup to Test Lead at test@example.com",
    "business.email_autoresponder_approval": "Set up auto-responder for test@example.com with approval off",
    "business.lead_intake_crm": "Add a new lead named New Lead from new@lead.com to CRM",
    "business.support_ticket_triage": "Triage this support ticket: subject=Login not working, body=cannot login, priority=high",
    "communication.chat_assistant": "Hello, how are you?",
    "communication.escalation_alert": "Escalate this incident: Server CPU at 95% on api-server",
    "communication.notify": "Send a test notification to telegram",
    "communication.voice_assistant": "Process voice input from test_audio.wav",
    "communication.workflow_failure_alert": "Alert on workflow test.workflow failure at test_step: Test error",
    "data.api_poll_to_store": "Poll https://jsonplaceholder.typicode.com/posts/1 and store to ~/KIO/test_output/api_data.json",
    "data.csv_pii_scrub": "Scrub PII columns email and phone from test_data.csv into ~/KIO/test_output/scrubbed.csv",
    "data.file_extract_to_csv": "Extract text from test_document.pdf to ~/KIO/test_output/extracted.csv",
    "data.form_intake": "Process form submission: name=Test User, email=test@example.com, message=Hello",
    "data.json_transform": "Transform JSON data to filter age>=26 and select name for Alice(30) and Bob(25)",
    "data.knowledge_base_sync": "Sync this entry to knowledge base: title=Test Entry, content=This is a test",
    "data.record_sync": "Sync record id=1 name=Test to local",
    "data.webhook_to_store": "Store webhook payload event=test data.value=42 to ~/KIO/test_output/webhook_data.json",
    "development.ci_failure_alert": "CI pipeline test-pipeline failed at stage test with: Tests failed",
    "development.dependency_monitor": "Check dependencies for aspire488/aspire488",
    "development.github_issue_triage": "Triage GitHub issue: Bug: Login fails - When I try to login, I get a 500 error in aspire488/aspire488",
    "development.issue_to_implementation": "Implement this issue: Add dark mode - Users want a dark mode option in aspire488/aspire488",
    "development.pr_review_prep": "Prepare PR #1 review for aspire488/aspire488 with checklist: security, performance, tests",
    "development.release_changelog": "Generate changelog for aspire488/aspire488 since tag v1.0.0",
    "development.repo_backup": "Backup aspire488/aspire488 to ~/KIO/test_output/backups",
    "development.repo_health_report": "Generate health report for aspire488/aspire488 checking stars, issues, PRs, contributors",
    "development.scaffold_project": "Scaffold a new project named test_project in python with basic template",
    "files.document_summarize": "Summarize the document at test_document.txt briefly",
    "files.download_folder_organizer": "Organize ~/Downloads folder, move PDF to Documents and JPG to Images",
    "files.drive_to_social": "Share test_image.jpg to telegram",
    "files.duplicate_detector": "Find duplicate files in ~/Documents with 90% similarity",
    "files.invoice_extract_to_sheet": "Extract invoice data from test_invoice.pdf to ~/KIO/test_output/invoices.xlsx",
    "media.content_repurpose": "Repurpose content 'Check out our new product launch with AI automation' for telegram as text",
    "monitoring.inbox_monitor": "Monitor inbox for important emails every 5 minutes",
    "monitoring.rss_news_monitor": "Monitor RSS feed https://feeds.bbci.co.uk/news/technology/rss.xml for AI and technology news, max 5 items",
    "monitoring.security_scan_alert": "Scan example.com for security issues with basic scan type",
    "monitoring.website_uptime": "Check uptime of https://example.com every 5 minutes expecting status 200",
    "productivity.calendar_to_status": "Show my calendar status as text",
    "productivity.ecosystem_briefing": "Give me a briefing including calendar, email, and tasks",
    "productivity.email_label_ai": "Label email from test@example.com subject: Meeting tomorrow with categories meeting, action_required, fyi",
    "productivity.email_to_calendar": "Create calendar event from email: meeting tomorrow at 3pm in Conference Room A",
    "productivity.email_to_task": "Create task from email: Q4 Report Due by Friday - prepare Q4 financial report",
    "productivity.meeting_prep": "Prepare for Q4 Planning meeting with alice@co.com and bob@co.com at 2026-09-22T10:00:00 including agenda, previous_notes, action_items",
    "productivity.morning_briefing": "Give me a morning briefing with calendar, weather, and news",
    "productivity.weekly_review": "Do a weekly review for current week including tasks, calendar, and emails",
    "research.competitor_monitor": "Monitor competitor example.com tracking https://example.com/pricing",
    "research.daily_brief": "Research topics AI news and tech startups from web, max 5 items, deliver brief to telegram",
    "research.web_scrape_to_report": "Scrape and summarize https://example.com into a docx report",
    "research.youtube_summary": "Summarize YouTube video https://www.youtube.com/watch?v=dQw4w9WgXcQ",
}


def run_workflow_serial(wf_id: str, nl_command: str) -> dict:
    """Run one workflow through the Telegram code path and verify the result.

    Uses dispatch_channel_input — the exact function kio_bot.py handle_message calls.
    """
    result = {
        "workflow": wf_id,
        "command": nl_command,
        "success": False,
        "status_code": None,
        "elapsed_ms": 0,
        "error": "",
    }

    start = time.time()
    try:
        reply = dispatch_channel_input(nl_command, channel="telegram", user_id=USER_ID)
        elapsed = (time.time() - start) * 1000
        result["elapsed_ms"] = round(elapsed)

        formatted = format_channel_reply(reply)
        result["status_code"] = "ok"
        result["reply"] = formatted[:200] if isinstance(formatted, str) else str(reply)[:200]

        success_markers = [
            "I've", "I did", "Opened", "Sent", "Created", "Wrote", "Extracted",
            "Researched", "Summarized", "Scaffolded", "Backed up", "Labelled",
            "Scheduled", "Found", "Generated",
        ]
        failure_markers = ["I couldn't", "failed", "error", "not available",
                          "not configured", "missing", "blocked", "unavailable",
                          "I don't", "can't", "cannot"]

        is_failure = any(m.lower() in formatted.lower() for m in failure_markers)
        is_success = any(m.lower() in formatted.lower() for m in success_markers)

        if is_failure:
            result["error"] = formatted[:200]
        elif is_success:
            result["success"] = True
        else:
            result["success"] = reply.get("success", False)
            result["error"] = "Unclear response" if not result["success"] else ""

    except Exception as exc:
        elapsed = (time.time() - start) * 1000
        result["elapsed_ms"] = round(elapsed)
        result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        result["traceback"] = traceback.format_exc()[-500:]

    return result


def main():
    parser = argparse.ArgumentParser(description="Serial Telegram E2E test runner")
    parser.add_argument("--start", type=int, default=1, help="Start from workflow N (1-indexed)")
    parser.add_argument("--count", type=int, default=0, help="Run N workflows (0 = all)")
    parser.add_argument("--workflow", type=str, default="", help="Run only this workflow category")
    args = parser.parse_args()

    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_TOKEN not set in .env")
        sys.exit(1)

    print("Bootstrapping KIO runtime (mirrors kio_bot.py) ...")
    runtime = bootstrap_runtime()
    print(f"Runtime ready: {runtime is not None}")

    from mini_kio.core.llm_router import _get_gateway
    gateway = _get_gateway()
    providers = gateway.get_registry().get_providers()
    print(f"LLM gateway initialized with {len(providers)} provider(s): {', '.join(providers) if providers else 'none'}")

    from mini_kio.automation.engine import create_automation_engine
    engine = create_automation_engine()

    all_wf = sorted(NL_COMMANDS.keys())
    if args.workflow:
        all_wf = [w for w in all_wf if w.startswith(args.workflow)]
    if args.start > 1:
        all_wf = all_wf[args.start - 1:]
    if args.count > 0:
        all_wf = all_wf[:args.count]

    total = len(all_wf)
    print(f"\nRunning {total} workflows serially through Telegram path...\n")

    results = {}
    ok_count = 0
    fail_count = 0

    for i, wf_id in enumerate(all_wf, 1):
        nl = NL_COMMANDS[wf_id]
        print(f"[{i}/{total}] {wf_id} : \"{nl}\"")

        result = run_workflow_serial(wf_id, nl)
        results[wf_id] = result

        if result["success"]:
            ok_count += 1
            print(f"    OK   {result['elapsed_ms']}ms  {result.get('reply', '')[:80]}")
        else:
            fail_count += 1
            print(f"    FAIL {result['elapsed_ms']}ms  {result.get('error', '')[:80]}")

        # Serial delay: one message at a time, let prior response settle
        if i < total:
            time.sleep(2)

    print(f"\n{'='*70}")
    print(f"SERIAL TELEGRAM E2E RESULTS  —  OK: {ok_count}  FAIL: {fail_count}  TOTAL: {total}")
    print(f"{'='*70}")

    if fail_count:
        print("\nFailed workflows:")
        for wf_id, r in results.items():
            if not r["success"]:
                print(f"  {wf_id}: {r.get('error', '')[:100]}")

    with open("_tg_e2e_serial_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to _tg_e2e_serial_results.json")


if __name__ == "__main__":
    main()
