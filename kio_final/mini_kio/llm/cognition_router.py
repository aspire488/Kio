"""
cognition_router.py — NVIDIA Cognition Router

Routes CognitiveIntent values to the correct NVIDIA model via ask_llm().
AGENT intent generates step-by-step execution plans.

Instrumentation:
  [NVIDIA_COGNITION] intent=<intent> model=<model>
  [AGENT_PLAN] steps=N
"""

import asyncio
import logging
import time
from typing import Optional

from mini_kio.core import config
from mini_kio.core.cognitive_intent import CognitiveIntent

logger = logging.getLogger(__name__)

# ── Intent → task_type mapping ─────────────────────────────────────
# Maps CognitiveIntent to the task_type string that ask_llm() expects.

_INTENT_TO_TASK: dict[CognitiveIntent, str] = {
    CognitiveIntent.CHAT: "chat",
    CognitiveIntent.FACTUAL_QA: "chat",
    CognitiveIntent.REASONING: "reasoning",
    CognitiveIntent.PLANNING: "planning",
    CognitiveIntent.ARCHITECTURE: "coding",
    CognitiveIntent.CODING: "coding",
    CognitiveIntent.DEBUGGING: "debugging",
    CognitiveIntent.AGENT: "coding",
    CognitiveIntent.VISION: "vision",
    CognitiveIntent.OCR: "vision",
    CognitiveIntent.SCREEN_ANALYSIS: "vision",
}

_COGNITION_INTENTS = frozenset(_INTENT_TO_TASK.keys())


def resolve_model_for_intent(intent: CognitiveIntent) -> str:
    """Return the NVIDIA model name for a given CognitiveIntent.

    Reads from config.NVIDIA_{UPPER}_MODEL for per-intent env overrides.
    Falls back to NVIDIA_PRIMARY_MODEL.
    """
    _intent_attrs: dict[CognitiveIntent, str] = {
        CognitiveIntent.CHAT: "CHAT",
        CognitiveIntent.FACTUAL_QA: "QA",
        CognitiveIntent.REASONING: "REASONING",
        CognitiveIntent.PLANNING: "PLANNING",
        CognitiveIntent.ARCHITECTURE: "ARCHITECTURE",
        CognitiveIntent.CODING: "CODE",
        CognitiveIntent.DEBUGGING: "DEBUG",
        CognitiveIntent.AGENT: "AGENT",
        CognitiveIntent.VISION: "VISION",
        CognitiveIntent.OCR: "OCR",
        CognitiveIntent.SCREEN_ANALYSIS: "SCREEN",
    }
    attr = _intent_attrs.get(intent, "CHAT")
    env_name = f"NVIDIA_{attr}_MODEL"
    return getattr(config, env_name, config.NVIDIA_PRIMARY_MODEL)


async def process_cognition(
    intent: CognitiveIntent,
    query: str,
) -> Optional[str]:
    """Route CognitiveIntent to the correct NVIDIA model via ask_llm().

    For AGENT intent, generates a step-by-step execution plan.
    For all other intents, calls NVIDIA directly.
    """
    from mini_kio.core.llm_router import ask_llm

    model = resolve_model_for_intent(intent)
    task_type = _INTENT_TO_TASK.get(intent, "chat")
    timeout = 30.0 if task_type in ("coding", "debugging") else 15.0
    max_tokens = 4000 if task_type in ("coding", "debugging") else 500

    logger.info(
        "[NVIDIA_COGNITION] intent=%s task_type=%s model=%s",
        intent.value, task_type, model,
    )

    if intent == CognitiveIntent.AGENT:
        return await _handle_agent(query)

    response = await ask_llm(
        query=query,
        timeout=timeout,
        max_tokens=max_tokens,
        task_type=task_type,
    )

    if response:
        logger.info("[NVIDIA_COGNITION] success intent=%s", intent.value)
    else:
        logger.warning("[NVIDIA_COGNITION] failed intent=%s", intent.value)

    return response


async def _handle_agent(query: str) -> Optional[str]:
    """Generate a browser automation plan using GPT-OSS."""
    from mini_kio.core.llm_router import ask_llm

    system_prompt = (
        "You are a browser automation planner. Given a user request, "
        "produce a numbered step-by-step plan for browser automation. "
        "Each step must be a single browser action.\n\n"
        "Format:\n"
        "1. Action: <action> Target: <target>\n"
        "2. Action: <action> Target: <target>\n\n"
        "Available actions: open_url, click, type, scroll, wait, "
        "search, navigate, submit\n\n"
        "Example:\n"
        "Input: open github and search browser automation\n"
        "Output:\n"
        "1. Action: open_url Target: https://github.com\n"
        "2. Action: wait Target: 2s\n"
        "3. Action: click Target: search bar\n"
        "4. Action: type Target: browser automation\n"
        "5. Action: submit Target: search\n"
        "6. Action: wait Target: 3s"
    )

    try:
        start_t = time.monotonic()
        plan_text = await ask_llm(
            query=f"{system_prompt}\n\nUser: {query}\n\nPlan:",
            timeout=30.0,
            max_tokens=2000,
            task_type="coding",
        )
        latency_ms = (time.monotonic() - start_t) * 1000
        if not plan_text:
            logger.warning("[AGENT_PLAN] generation returned None")
            return None
        steps = [s.strip() for s in plan_text.split("\n") if s.strip() and s[0].isdigit()]
        logger.info("[AGENT_PLAN] steps=%d latency=%.0fms", len(steps), latency_ms)
        return plan_text
    except Exception as exc:
        logger.warning("[AGENT_PLAN] generation failed: %s", exc)
        return None


def is_cognition_intent(intent: CognitiveIntent) -> bool:
    return intent in _COGNITION_INTENTS
