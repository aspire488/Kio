import asyncio
import logging
import re
from typing import Any, Optional

from mini_kio.core import config as kio_config
from mini_kio.core.llm_router import ask_llm

logger = logging.getLogger(__name__)

# ── AuraClient singleton (lazy) ────────────────────────────────────
_aura_client: Optional["AuraClient"] = None


def _get_aura_client():
    global _aura_client
    if _aura_client is None:
        from mini_kio.aura import AuraClient
        _aura_client = AuraClient()
    return _aura_client


# ── AURA response extraction ───────────────────────────────────────

def _extract_aura_context(result: dict) -> list[dict[str, Any]]:
    """Extract context items from an AURA retrieve() response dict.

    Accepts multiple response shapes:
      {"context": [{"text": ..., "score": ...}, ...]}
      {"results": [{"text": ..., "score": ...}, ...]}
      {"response": [{"text": ..., "score": ...}, ...]}
    Returns empty list on any mismatch.
    """
    items: list[dict[str, Any]] = []
    for key in ("context", "results", "response", "memories", "documents"):
        raw = result.get(key)
        if isinstance(raw, list):
            items = raw
            break
    if not items:
        # Single-document response
        text_val = result.get("text") or result.get("content") or result.get("response")
        if isinstance(text_val, str):
            items = [{"text": text_val, "score": 1.0}]
    return items


# ── Sanitizer ──────────────────────────────────────────────────────

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


# ── Main entry point ───────────────────────────────────────────────


def ask_llm_sync(query: str, system_prompt: Optional[str] = None, timeout: float = 20.0, max_tokens: int = 400, task_type: str = "chat") -> Optional[str]:
    """Synchronous wrapper for LLM requests.

    Attempts AURA context retrieval first when AURA_ENABLED=true.
    Falls back to the provided system_prompt (local context) on any failure.
    """
    # ── AURA context retrieval ──────────────────────────────────────
    if kio_config.AURA_ENABLED and kio_config.AURA_BASE_URL:
        try:
            aura = _get_aura_client()
            if aura._enabled:
                health = asyncio.run(aura.health())
                if health is not None:
                    result = asyncio.run(aura.retrieve(query))
                    if result is not None:
                        items = _extract_aura_context(result)
                        memories = [
                            m for m in items
                            if m.get("score", 1.0) >= 0.40
                        ]
                        memories = sorted(
                            memories,
                            key=lambda x: x.get("score", 1.0),
                            reverse=True,
                        )[:3]
                        if memories:
                            mem_lines = [
                                f"* ({m.get('score', 1.0):.2f}) {m.get('text', '')}"
                                for m in memories
                            ]
                            aura_context = "\n\nRelevant Context:\n" + "\n".join(mem_lines)
                            system_prompt = (system_prompt or "") + aura_context
                            logger.info(
                                "[AURA_RETRIEVE] status=aura count=%d",
                                len(memories),
                            )
                        else:
                            logger.info("[AURA_RETRIEVE] status=aura count=0 (below threshold)")
                    else:
                        logger.info("[AURA_RETRIEVE] status=fallback reason=retrieve_failed")
                else:
                    logger.info("[AURA_RETRIEVE] status=fallback reason=health_failed")
            else:
                logger.info("[AURA_RETRIEVE] status=fallback reason=client_disabled")
        except Exception:
            logger.exception("[AURA_FALLBACK] retrieval failed")
    else:
        logger.info("[AURA_RETRIEVE] status=local reason=disabled")

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
