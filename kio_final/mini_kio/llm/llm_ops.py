import asyncio
import logging
import os
import re
from typing import Optional

import requests
from mini_kio.core.config import GEMINI_ENABLED, GEMINI_TIMEOUT_S, GEMINI_MAX_TOKENS
from mini_kio.core.llm_router import ask_llm

logger = logging.getLogger(__name__)

_EXECUTION_CLAIM_RE = re.compile(
    r"\b(I'll\s+(?:open|close|execute|launch|run|start|stop|kill)\s+|"
    r"I've\s+(?:opened|closed|executed|launched|run|started|stopped)\s+|"
    r"I\s+(?:opened|closed|executed|launched|ran|started|stopped|killed|"
    r"will\s+(?:open|close|execute|launch|run|start|stop|kill)|"
    r"have\s+(?:opened|closed|executed|launched|run|started|stopped))\s+)",
    re.IGNORECASE,
)

_AUTHORITY_CLAIM_RE = re.compile(
    r"\b(I\s+(?:control|manage|administer|override|bypass|ignore)\s+)",
    re.IGNORECASE,
)

def _sanitize_llm_output(text: str) -> str:
    """Remove execution claims, authority hallucinations, and reasoning blocks."""
    if text.startswith("KIO:"):
        text = text[4:].strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = _EXECUTION_CLAIM_RE.sub("", text)
    text = _AUTHORITY_CLAIM_RE.sub("", text)
    return text.strip().strip('"').strip("'")

def ask_llm_sync(query: str, system_prompt: Optional[str] = None, timeout: float = 20.0, max_tokens: int = 400, task_type: str = "chat") -> Optional[str]:
    """Synchronous wrapper for LLM requests."""
    _aura_url = os.environ.get("AURA_URL")
    if _aura_url:
        try:
            logger.info("[AURA_RETRIEVE] query=%s", query)
            resp = requests.post(
                f"{_aura_url}/retrieval/query",
                json={"query": query, "top_k": 10},
                timeout=2,
            )
            logger.info("[AURA_RETRIEVE] status=%s", resp.status_code)
            if resp.ok:
                results = resp.json().get("results", [])
                logger.info("[AURA_RETRIEVE] retrieved=%d", len(results))
                memories = [
                    m for m in results
                    if m.get("score", 0) >= 0.40
                ]
                memories = sorted(
                    memories,
                    key=lambda x: x.get("score", 0),
                    reverse=True,
                )[:3]
                logger.info("[AURA_RETRIEVE] injected=%d", len(memories))
                logger.info("[AURA_RETRIEVE] top_scores=%s",
                    [round(m.get("score", 0), 3) for m in memories]
                )
                if memories:
                    mem_lines = [
                        f"* ({m.get('score', 0):.2f}) {m['text']}"
                        for m in memories
                    ]
                    aura_context = "\n\nRelevant Memories:\n" + "\n".join(mem_lines)
                    system_prompt = (system_prompt or "") + aura_context
        except Exception:
            logger.exception("[AURA_FALLBACK] retrieval failed")

    # Build prompt
    if system_prompt and "Current User Input:" in system_prompt:
        prompt = f"{system_prompt}\nKIO:"
    elif system_prompt:
        prompt = f"{system_prompt}\n\nUser: {query}\nKIO:"
    else:
        prompt = f"You are KIO.\n\nUser: {query}\nKIO:"

    try:
        try:
            content = asyncio.run(ask_llm(prompt, timeout=timeout, max_tokens=max_tokens, task_type=task_type))
        except RuntimeError:
            # Called from an async context where asyncio.run() is forbidden.
            # Fall back to scheduling on the running loop via thread-safe bridge.
            try:
                loop = asyncio.get_running_loop()
                future = asyncio.run_coroutine_threadsafe(
                    ask_llm(prompt, timeout=timeout, max_tokens=max_tokens, task_type=task_type),
                    loop,
                )
                content = future.result(timeout=timeout + 5.0)
            except BaseException:
                logger.exception("LLM provider crashed in async fallback path")
                content = None
        except BaseException:
            logger.exception("LLM provider crashed in asyncio.run path")
            content = None

        if content:
            sanitized = _sanitize_llm_output(content)
            return sanitized if sanitized else None
    except Exception as e:
        logger.debug(f"LLM fallback triggered: {str(e)[:100]}")

    return None
