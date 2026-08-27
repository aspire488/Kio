import asyncio
import logging
import re
import threading
from typing import Optional
from mini_kio.core.config import GEMINI_ENABLED, GEMINI_TIMEOUT_S, GEMINI_MAX_TOKENS
from mini_kio.core.llm_router import ask_llm

logger = logging.getLogger(__name__)

# Shared event loop for sync callers — avoids creating a new loop per call.
# Initialized lazily on first use from a background thread.
_sync_loop: Optional[asyncio.AbstractEventLoop] = None
_sync_loop_lock = threading.Lock()


def _get_sync_loop() -> asyncio.AbstractEventLoop:
    """Return a persistent background event loop for synchronous LLM calls.

    Creating asyncio.run() per call spins up and tears down a full event loop
    each time — measurable overhead (5-15ms) plus resource churn. A single
    dedicated loop avoids that cost and enables proper cancellation via
    loop.call_soon_threadsafe.
    """
    global _sync_loop
    if _sync_loop is not None and _sync_loop.is_running():
        return _sync_loop
    with _sync_loop_lock:
        if _sync_loop is not None and _sync_loop.is_running():
            return _sync_loop
        _sync_loop = asyncio.new_event_loop()
        t = threading.Thread(target=_sync_loop.run_forever, daemon=True,
                             name="kio-llm-sync-loop")
        t.start()
        return _sync_loop


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


def ask_llm_sync(query: str, system_prompt: Optional[str] = None,
                 timeout: float = 20.0, max_tokens: int = 400,
                 task: str = "") -> Optional[str]:
    """Synchronous wrapper for LLM requests.

    Uses a persistent background event loop instead of asyncio.run() per call.
    The outer timeout is bounded to the caller's value; the gateway enforces
    its own tighter per-provider and total-chain timeouts internally.
    """
    # Build prompt
    if system_prompt and "Current User Input:" in system_prompt:
        prompt = f"{system_prompt}\nKIO:"
    elif system_prompt:
        prompt = f"{system_prompt}\n\nUser: {query}\nKIO:"
    else:
        prompt = f"You are KIO.\n\nUser: {query}\nKIO:"

    # Outer timeout: must be strictly larger than the gateway's chain budget
    # (10s normal / 6s fast) so the gateway controls actual provider latency,
    # not the sync wrapper. Add2s headroom for event-loop dispatch overhead.
    _outer_timeout = max(timeout, 8.0) + 2.0

    try:
        try:
            content = asyncio.run(ask_llm(prompt, timeout=timeout,
                                          max_tokens=max_tokens, task=task))
        except RuntimeError:
            # Called from an async context where asyncio.run() is forbidden.
            # Fall back to the shared background loop via thread-safe dispatch.
            try:
                loop = _get_sync_loop()
                future = asyncio.run_coroutine_threadsafe(
                    ask_llm(prompt, timeout=timeout,
                            max_tokens=max_tokens, task=task),
                    loop,
                )
                content = future.result(timeout=_outer_timeout)
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning("LLM sync call timed out after %.1fs", _outer_timeout)
                content = None
            except BaseException:
                logger.exception("LLM provider crashed in sync-loop path")
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
