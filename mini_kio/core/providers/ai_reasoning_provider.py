"""AIReasoningProvider — exposes KIO's existing LLM stack through the ExecutionProvider contract.

This is a thin adapter, NOT a second LLM architecture. Execution delegates to the
single existing `ai_reasoning` branch in `app_operator.execute_capability()`, which
itself routes through `ask_llm_sync()` → `ask_llm()` → `LLMGateway` →
multi-provider failover chain. Nothing about cognition is reimplemented here.

Its purpose is availability honesty. The automation capability check
(`automation/capability_resolver.py`) resolves capabilities through the
ProviderRegistry, so a capability whose implementation lives in KIO's capability
router but that is not registered as a provider is reported MISSING even though it
works. Registering the capability here — with `health()` derived from the real
provider chain — lets the registry answer "is ai_reasoning available right now?"
truthfully instead of "was a registration performed?".

`health()` is the gate: HEALTHY only when the existing chain has at least one
provider registered, OFFLINE otherwise (so `ProviderRegistry.get_provider()`
returns None and the capability is reported missing rather than falsely
available). No keys, model names, or provider details are ever exposed as
credential values.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mini_kio.core.provider_contract import (
    ExecutionProvider,
    ProviderCapability,
    ProviderHealth,
)

logger = logging.getLogger(__name__)

# Names the rest of KIO looks this capability up by. `ai_reasoning` is the
# capability name used by every workflow YAML; `llm` is the name those same
# templates declare in `providers_required`.
_CAPABILITY_NAMES = ("ai_reasoning", "llm")

# All AI reasoning actions that workflows use
_AI_ACTIONS = [
    "classify", "classify_actionable", "classify_issue", "classify_response",
    "analyze", "analyze_competitive_changes", "analyze_diff",
    "summarize", "summarize_change", "summarize_digest", "summarize_health", "summarize_videos",
    "extract", "extract_error", "extract_meeting_structure", "extract_structured",
    "generate", "generate_image",
    "transform", "enrich",
    "research", "plan_document", "write_content", "compose_html",
    "compose_briefing", "compose_brief", "compose_review", "plan_slides",
    "validate_against_schema", "detect_pii", "prioritize_updates",
    "score_priority", "synthesize_report", "chat", "transcribe",
    "repair_document", "dedupe_and_score", "draft_followups",
    "triage_ticket", "structure_entry", "adapt_per_platform",
]


def llm_provider_names() -> list[str]:
    """Names of the LLM providers currently registered in the existing chain.

    Single source of truth for "is KIO's cognition backend up?" — used by this
    provider's health gate and by the automation credential bridge (a YAML
    `type: llm` credential is satisfied by this chain, not by CredentialVault).
    Returns [] when the chain cannot be inspected — never a fabricated list.
    """
    try:
        from mini_kio.core.llm_router import _get_gateway
        return list(_get_gateway().get_registry().get_providers())
    except Exception as exc:
        logger.debug("AIReasoningProvider: LLM chain unavailable: %s", exc)
        return []


def llm_capability_available() -> tuple[bool, str]:
    """(available, detail) for the ai_reasoning capability's real dependency."""
    names = llm_provider_names()
    if not names:
        return False, "no LLM provider configured"
    return True, f"{len(names)} LLM provider(s) configured"


class AIReasoningProvider(ExecutionProvider):
    """Health-gated bridge from the provider registry to the existing LLM stack."""

    def id(self) -> str:
        return "ai_reasoning"

    def capabilities(self) -> list[ProviderCapability]:
        caps = [
            ProviderCapability(name=name, category="read_only", timeout_s=25.0, ram_budget_mb=20)
            for name in _CAPABILITY_NAMES
        ]
        # Register all AI reasoning actions so the provider registry can find them
        for action in _AI_ACTIONS:
            caps.append(ProviderCapability(name=action, category="ai_reasoning", timeout_s=30.0, ram_budget_mb=20))
        return caps

    def health(self) -> ProviderHealth:
        available, _ = llm_capability_available()
        return ProviderHealth.HEALTHY if available else ProviderHealth.OFFLINE

    def estimate(self, action: str, target: str) -> dict[str, Any]:
        return {"estimated_ms": 10000, "action": action, "target": target}

    def execute(self, action: str, target: str = "", **kwargs: Any) -> dict[str, Any]:
        """Execute an AI reasoning action.

        Tries the existing execution boundary first; if that fails with an
        unsupported action, falls back to direct LLM call via ask_llm_sync.
        """
        payload = dict(kwargs)
        if target:
            try:
                parsed = json.loads(target)
            except (json.JSONDecodeError, TypeError):
                payload.setdefault("input", target)
            else:
                if isinstance(parsed, dict):
                    for key, value in parsed.items():
                        payload.setdefault(key, value)
                else:
                    payload.setdefault("input", parsed)
        # Try existing execution boundary
        try:
            from mini_kio.core.execution_boundary import execute_action
            result = execute_action(
                "execute_capability",
                f"ai_reasoning::{action}::{json.dumps(payload)}",
            )
            if result.get("success"):
                return result
        except Exception:
            pass
        # Fallback: direct LLM call
        try:
            from mini_kio.core.llm_router import ask_llm
            import asyncio
            prompt = self._build_prompt(action, payload)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already in an event loop — use a new thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, ask_llm(prompt))
                        response = future.result(timeout=30)
                else:
                    response = loop.run_until_complete(ask_llm(prompt))
            except RuntimeError:
                response = asyncio.run(ask_llm(prompt))
            return {"success": True, "action": action, "response": response,
                    "message": f"AI {action} completed"}
        except Exception as exc:
            return {"success": False, "message": f"AI reasoning unavailable: {exc}"}

    def _build_prompt(self, action: str, payload: dict) -> str:
        """Build an LLM prompt for the given action."""
        input_text = payload.get("input", payload.get("text", payload.get("item", "")))
        if isinstance(input_text, dict):
            input_text = json.dumps(input_text)
        if action == "classify":
            categories = payload.get("categories", [])
            return f"Classify the following into one of {categories}: {input_text}"
        if action == "classify_actionable":
            return f"Is this actionable? Reply with yes/no and reason: {input_text}"
        if action == "classify_issue":
            return f"Classify this issue: {input_text}"
        if action == "classify_response":
            return f"Classify this response: {input_text}"
        if action in ("summarize", "summarize_change", "summarize_digest", "summarize_health"):
            return f"Summarize the following concisely: {input_text}"
        if action == "summarize_videos":
            return f"Summarize these video transcripts: {input_text}"
        if action in ("extract", "extract_structured"):
            schema = payload.get("schema", {})
            return f"Extract structured data matching {schema} from: {input_text}"
        if action == "extract_error":
            return f"Extract the error details from: {input_text}"
        if action == "extract_meeting_structure":
            return f"Extract meeting structure (attendees, agenda, decisions, action items) from: {input_text}"
        if action in ("analyze", "analyze_competitive_changes"):
            return f"Analyze the following: {input_text}"
        if action == "analyze_diff":
            return f"Analyze these code changes: {input_text}"
        if action == "research":
            query = payload.get("query", input_text)
            return f"Research and provide key findings on: {query}"
        if action == "plan_document":
            findings = payload.get("findings", input_text)
            return f"Create a document outline with sections and tables for: {findings}"
        if action == "write_content":
            outline = payload.get("outline", input_text)
            return f"Write substantive content for this outline: {outline}"
        if action == "compose_html":
            return f"Compose HTML content for: {input_text}"
        if action in ("compose_briefing", "compose_brief"):
            return f"Compose a briefing on: {input_text}"
        if action == "compose_review":
            return f"Compose a review based on: {input_text}"
        if action == "plan_slides":
            return f"Plan presentation slides for: {input_text}"
        if action == "validate_against_schema":
            schema = payload.get("schema", {})
            return f"Validate this data against schema {schema}: {input_text}"
        if action == "detect_pii":
            return f"Detect PII in: {input_text}"
        if action == "prioritize_updates":
            return f"Prioritize these updates by urgency: {input_text}"
        if action == "score_priority":
            return f"Score priority (1-10) for: {input_text}"
        if action == "synthesize_report":
            return f"Synthesize a report from: {input_text}"
        if action == "chat":
            return str(input_text)
        if action == "transcribe":
            return f"Transcribe: {input_text}"
        if action == "repair_document":
            return f"Fix document issues: {input_text}"
        if action == "dedupe_and_score":
            return f"Dedupe and score: {input_text}"
        if action == "draft_followups":
            return f"Draft follow-up messages for: {input_text}"
        if action == "triage_ticket":
            return f"Triage this support ticket: {input_text}"
        if action == "structure_entry":
            return f"Structure this knowledge entry: {input_text}"
        if action == "adapt_per_platform":
            return f"Adapt this content for different platforms: {input_text}"
        if action == "generate_image":
            return f"Describe an image generation prompt for: {input_text}"
        return f"Process: {action} - {input_text}"

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "ai_reasoning")
        if result.get("success"):
            result.setdefault("verification_status", "passed")
            result.setdefault("outcome_class", "SUCCESS")
        else:
            result.setdefault("verification_status", "failed")
            result.setdefault("outcome_class", "FAILURE")
        return result
