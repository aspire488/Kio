"""Execute all 63 KIO workflows through the AutomationEngine with safe test inputs.

Bootstraps the full KIO runtime (mirrors kio_bot.py) so that:
  - .env is loaded via dotenv (canonical path)
  - bootstrap_runtime() sets the runtime singleton, registers providers,
    initializes BrowserRuntime, MCPRuntime, and writes the readiness flag
  - The LLM gateway is initialized with the real provider chain
"""
import sys, os, json, time, asyncio

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, '.')

from mini_kio.core.runtime import bootstrap_runtime
bootstrap_runtime()

from mini_kio.core.providers import register_all_providers
register_all_providers()

from mini_kio.core.llm_router import _get_gateway
_get_gateway()  # Eagerly initialize the LLM gateway with registered providers

from mini_kio.automation.engine import create_automation_engine
engine = create_automation_engine()

# Safe test inputs per workflow category
TEST_INPUTS = {
    # AI
    "ai.classify_and_route": {
        "item": {"text": "Please update billing address", "source": "email"},
        "config": {"categories": ["billing", "support", "feature_request"], "routes": {"billing": "finance_team", "support": "support_team", "feature_request": "product_team"}}
    },
    "ai.enrich_records": {
        "records": [{"name": "Acme Corp", "domain": "acme.com"}],
        "config": {"enrich_fields": ["industry", "size"]}
    },
    "ai.extract_to_structured": {
        "text": "John Smith, CEO, Acme Corp, john@acme.com, $50,000 deal",
        "config": {"schema": {"name": "string", "title": "string", "company": "string", "email": "string", "amount": "number"}}
    },
    "ai.image_generate": {
        "prompt": "A simple blue circle on white background",
        "config": {"style": "minimal", "size": "512x512"}
    },
    "ai.rag_answer": {
        "query": "What is KIO?",
        "config": {"context_docs": ["KIO is an AI assistant platform"]}
    },
    "ai.transcribe_summarize": {
        "audio_path": "test_audio.wav",
        "config": {"summary_length": "brief"}
    },
    # Artifacts
    "artifacts.data_to_xlsx": {
        "data": [{"name": "Test", "value": 42}],
        "config": {"sheet_name": "Test", "output_dir": "~/KIO/test_output"}
    },
    "artifacts.meeting_to_report": {
        "meeting_notes": "Q4 planning: discussed budget, timeline, and resource allocation. Action items: update roadmap, prepare budget proposal.",
        "config": {"format": "docx", "output_dir": "~/KIO/test_output"}
    },
    "artifacts.multiformat_report": {
        "content": "Quarterly Business Review\nRevenue: $1.2M\nGrowth: 15%\nCustomers: 500",
        "config": {"formats": ["docx", "pdf"], "output_dir": "~/KIO/test_output"}
    },
    "artifacts.research_to_docx": {
        "topic": " artificial intelligence trends 2026",
        "config": {"length": "brief", "output_dir": "~/KIO/test_output"}
    },
    "artifacts.research_to_pdf": {
        "topic": "renewable energy basics",
        "config": {"length": "brief", "output_dir": "~/KIO/test_output"}
    },
    "artifacts.research_to_pptx": {
        "topic": "cloud computing overview",
        "config": {"length": "brief", "output_dir": "~/KIO/test_output"}
    },
    # Browser
    "browser.page_change_monitor": {
        "url": "https://example.com",
        "config": {"selector": "h1", "interval_minutes": 60}
    },
    "browser.price_monitor": {
        "url": "https://example.com/product",
        "config": {"price_selector": ".price", "threshold": 100}
    },
    "browser.structured_extract": {
        "url": "https://example.com/data",
        "config": {"output_path": "~/KIO/test_output/extracted.csv"}
    },
    # Business
    "business.crm_followup": {
        "leads": [{"name": "Test Lead", "email": "test@example.com", "last_contact": "2026-09-01"}],
        "config": {"followup_template": "Hi {{name}}, following up on our conversation."}
    },
    "business.email_autoresponder_approval": {
        "email": {"from": "test@example.com", "subject": "Question about pricing", "body": "What are your prices?"},
        "config": {"autorespond": True, "approval_required": False}
    },
    "business.lead_intake_crm": {
        "lead": {"name": "New Lead", "email": "new@lead.com", "source": "website"},
        "config": {"crm_provider": "local"}
    },
    "business.support_ticket_triage": {
        "ticket": {"subject": "Login not working", "body": "I cannot login to my account", "priority": "high"},
        "config": {"categories": ["bug", "feature", "question"]}
    },
    # Communication
    "communication.chat_assistant": {
        "message": "Hello, how are you?",
        "config": {"personality": "helpful"}
    },
    "communication.escalation_alert": {
        "alert": {"severity": "high", "message": "Server CPU at 95%", "service": "api-server"},
        "config": {"escalation_tiers": ["oncall", "manager"]}
    },
    "communication.notify": {
        "message": "Test notification from KIO workflow",
        "config": {"channel": "telegram"}
    },
    "communication.voice_assistant": {
        "audio_input": "test_audio.wav",
        "config": {"voice": "default"}
    },
    "communication.workflow_failure_alert": {
        "failure": {"workflow_id": "test.workflow", "error": "Test error", "step": "test_step"},
        "config": {"channel": "telegram"}
    },
    # Data
    "data.api_poll_to_store": {
        "url": "https://jsonplaceholder.typicode.com/posts/1",
        "config": {"interval_minutes": 60, "store_path": "~/KIO/test_output/api_data.json"}
    },
    "data.csv_pii_scrub": {
        "csv_path": "test_data.csv",
        "config": {"pii_columns": ["email", "phone"], "output_path": "~/KIO/test_output/scrubbed.csv"}
    },
    "data.file_extract_to_csv": {
        "file_path": "test_document.pdf",
        "config": {"output_path": "~/KIO/test_output/extracted.csv"}
    },
    "data.form_intake": {
        "form_data": {"name": "Test User", "email": "test@example.com", "message": "Hello"},
        "config": {"validation_rules": {"email": "required"}}
    },
    "data.json_transform": {
        "data": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}],
        "config": {"transform": {"filter": "age >= 26", "select": ["name"]}, "output_format": "json"}
    },
    "data.knowledge_base_sync": {
        "entries": [{"title": "Test Entry", "content": "This is a test knowledge base entry."}],
        "config": {"sync_target": "local"}
    },
    "data.record_sync": {
        "source_records": [{"id": 1, "name": "Test"}],
        "config": {"sync_target": "local"}
    },
    "data.webhook_to_store": {
        "payload": {"event": "test", "data": {"value": 42}},
        "config": {"store_path": "~/KIO/test_output/webhook_data.json"}
    },
    # Development
    "development.ci_failure_alert": {
        "failure": {"pipeline": "test-pipeline", "stage": "test", "error": "Tests failed"},
        "config": {"channel": "telegram"}
    },
    "development.dependency_monitor": {
        "repo": "aspire488/aspire488",
        "config": {"check_interval_hours": 24}
    },
    "development.github_issue_triage": {
        "issue": {"title": "Bug: Login fails", "body": "When I try to login, I get a 500 error", "labels": []},
        "repo": "aspire488/aspire488",
        "config": {"categories": ["bug", "feature", "question"]}
    },
    "development.issue_to_implementation": {
        "issue": {"title": "Add dark mode", "body": "Users want a dark mode option"},
        "repo": "aspire488/aspire488",
        "config": {"language": "python"}
    },
    "development.pr_review_prep": {
        "pr": {"number": 1, "repo": "aspire488/aspire488"},
        "config": {"review_checklist": ["security", "performance", "tests"]}
    },
    "development.release_changelog": {
        "repo": "aspire488/aspire488",
        "config": {"since_tag": "v1.0.0", "format": "markdown"}
    },
    "development.repo_backup": {
        "repo": "aspire488/aspire488",
        "config": {"backup_path": "~/KIO/test_output/backups"}
    },
    "development.repo_health_report": {
        "repo": "aspire488/aspire488",
        "config": {"checks": ["stars", "issues", "prs", "contributors"]}
    },
    "development.scaffold_project": {
        "project_name": "test_project",
        "config": {"language": "python", "template": "basic"}
    },
    # Files
    "files.document_summarize": {
        "file_path": "test_document.txt",
        "config": {"summary_length": "brief"}
    },
    "files.download_folder_organizer": {
        "folder_path": "~/Downloads",
        "config": {"rules": {"pdf": "Documents", "jpg": "Images"}}
    },
    "files.drive_to_social": {
        "file_path": "test_image.jpg",
        "config": {"platforms": ["telegram"]}
    },
    "files.duplicate_detector": {
        "folder_path": "~/Documents",
        "config": {"similarity_threshold": 0.9}
    },
    "files.invoice_extract_to_sheet": {
        "file_path": "test_invoice.pdf",
        "config": {"output_path": "~/KIO/test_output/invoices.xlsx"}
    },
    # Media
    "media.content_repurpose": {
        "content": "Check out our new product launch! It features AI-powered automation.",
        "config": {"platforms": ["telegram"], "formats": ["text"]}
    },
    # Monitoring
    "monitoring.inbox_monitor": {
        "config": {"check_interval_minutes": 5, "filters": {"subject_contains": "important"}}
    },
    "monitoring.rss_news_monitor": {
        "feed_url": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "config": {"keywords": ["AI", "technology"], "max_items": 5}
    },
    "monitoring.security_scan_alert": {
        "target": "example.com",
        "config": {"scan_type": "basic"}
    },
    "monitoring.website_uptime": {
        "url": "https://example.com",
        "config": {"check_interval_minutes": 5, "expected_status": 200}
    },
    # Productivity
    "productivity.calendar_to_status": {
        "config": {"output_format": "text"}
    },
    "productivity.ecosystem_briefing": {
        "config": {"include": ["calendar", "email", "tasks"]}
    },
    "productivity.email_label_ai": {
        "email": {"from": "test@example.com", "subject": "Meeting tomorrow", "body": "Can we meet tomorrow at 3pm?"},
        "config": {"labels": ["meeting", "action_required", "fyi"]}
    },
    "productivity.email_to_calendar": {
        "email": {"from": "test@example.com", "subject": "Meeting tomorrow at 3pm", "body": "Let's meet tomorrow at 3pm in Conference Room A."},
        "config": {"calendar": "primary"}
    },
    "productivity.email_to_task": {
        "email": {"from": "boss@company.com", "subject": "Q4 Report Due", "body": "Please prepare the Q4 financial report by Friday."},
        "config": {"task_system": "todoist"}
    },
    "productivity.meeting_prep": {
        "meeting": {"title": "Q4 Planning", "attendees": ["alice@co.com", "bob@co.com"], "time": "2026-09-22T10:00:00"},
        "config": {"prep_items": ["agenda", "previous_notes", "action_items"]}
    },
    "productivity.morning_briefing": {
        "config": {"include": ["calendar", "weather", "news"]}
    },
    "productivity.weekly_review": {
        "config": {"week": "current", "include": ["tasks", "calendar", "emails"]}
    },
    # Research
    "research.competitor_monitor": {
        "competitors": ["example.com"],
        "config": {"tracked_pages": ["https://example.com/pricing"]}
    },
    "research.daily_brief": {
        "topics": ["AI news", "tech startups"],
        "config": {"sources": ["web"], "max_items": 5}
    },
    "research.web_scrape_to_report": {
        "url": "https://example.com",
        "config": {"output_format": "docx", "output_dir": "~/KIO/test_output"}
    },
    "research.youtube_summary": {
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "config": {"summary_length": "brief"}
    },
}

# Execute all 63
results = {}
print(f"\n{'='*70}")
print(f"EXECUTING ALL 63 WORKFLOWS")
print(f"{'='*70}\n")

async def run_all():
    for tid in engine.list_templates():
        rec = engine.get_template(tid)
        test_input = TEST_INPUTS.get(tid, {})
        # Separate inputs and config
        inputs = {}
        config = {}
        for k, v in test_input.items():
            if k == "config":
                config = v
            else:
                inputs[k] = v

        start = time.time()
        try:
            result = await engine.execute(tid, inputs=inputs, config=config)
            elapsed = (time.time() - start) * 1000
            status = "FULL" if result.get("success") else "FAILED"
            error = result.get("error", "")
            steps_ok = sum(1 for s in result.get("steps", []) if s.get("success"))
            steps_total = len(result.get("steps", []))
            results[tid] = {
                "status": status,
                "success": result.get("success", False),
                "steps": f"{steps_ok}/{steps_total}",
                "elapsed_ms": round(elapsed),
                "error": error[:120] if error else "",
            }
            icon = "OK" if result.get("success") else "FAIL"
            print(f"[{icon:4s}] {tid:45s} steps={steps_ok}/{steps_total} {elapsed:7.0f}ms" +
                  (f" err={error[:60]}" if error else ""))
        except Exception as exc:
            elapsed = (time.time() - start) * 1000
            results[tid] = {
                "status": "FAILED",
                "success": False,
                "steps": "0/0",
                "elapsed_ms": round(elapsed),
                "error": str(exc)[:120],
            }
            print(f"[FAIL] {tid:45s} EXCEPTION: {str(exc)[:80]}")

asyncio.run(run_all())

# Summary
print(f"\n{'='*70}")
print(f"SUMMARY")
print(f"{'='*70}")
full = sum(1 for r in results.values() if r["status"] == "FULL")
failed = sum(1 for r in results.values() if r["status"] == "FAILED")
print(f"FULL: {full}/63")
print(f"FAILED: {failed}/63")
if failed:
    print(f"\nFailed workflows:")
    for tid, r in results.items():
        if r["status"] == "FAILED":
            print(f"  {tid}: {r['error'][:80]}")

# Save results
with open("_e2e_results.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to _e2e_results.json")
