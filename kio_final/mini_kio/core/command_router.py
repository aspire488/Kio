"""
command_router.py — KIO Command Router
=======================================
Fixes applied in this revision
--------------------------------
BUG-01  _is_multi_step() was missing "play" verb → "open chrome and play messi"
        was never detected as multi-step.
BUG-02  _ai_fallback() had two unreachable duplicate return statements (dead code
        after the first return in the knowledge-base miss branch).
BUG-03  LLM integration was disabled: `response = None` was hard-coded, making
        asyncio.run(ask_llm(...)) permanently skipped.  Now uses asyncio.run()
        with a hard 8 s timeout and falls through gracefully on failure.
BUG-04  "what are your features" was not in the knowledge base, causing it to
        fall through to the generic "I don't understand" error.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from mini_kio.core.execution_boundary import execute_action

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-import helpers (avoid circular imports at module load time)
# ---------------------------------------------------------------------------

def _lazy_import(module_name: str, item_names: list[str]) -> dict:
    try:
        if module_name == "task_engine":
            from mini_kio.core.task_engine import run_task
            return {"run_task": run_task}
        elif module_name == "app_operator":
            from mini_kio.core.app_operator import launch_app, close_app, search_web
            return {"launch_app": launch_app, "close_app": close_app, "search_web": search_web}
        elif module_name == "file_operator":
            from mini_kio.core.file_operator import open_folder
            return {"open_folder": open_folder}
        elif module_name == "system_operator":
            from mini_kio.core.system_operator import shutdown_system, restart_system, lock_system
            return {"shutdown_system": shutdown_system, "restart_system": restart_system, "lock_system": lock_system}
        elif module_name == "browser_operator":
            from mini_kio.core.browser_operator import open_url, search_google, search_youtube, play_youtube
            return {"open_url": open_url, "search_google": search_google, "search_youtube": search_youtube, "play_youtube": play_youtube}
        elif module_name == "ai":
            from mini_kio.core.ai import ask_ai
            return {"ask_ai": ask_ai}
    except ImportError as e:
        logger.warning(f"Failed to import {module_name}: {e}")
    return {}


def _log_route(event: str, **fields: Any) -> None:
    payload: dict[str, Any] = {"evt": event}
    payload.update(fields)
    logger.info(json.dumps(payload, default=str))


# Folder keywords for routing (must match file_operator.WINDOWS_FOLDERS)
_FOLDER_KEYWORDS: frozenset[str] = frozenset(
    {"downloads", "desktop", "documents", "pictures", "music", "videos", "home", "appdata"}
)


# ---------------------------------------------------------------------------
# Multi-step detection
# ---------------------------------------------------------------------------

def _is_multi_step(lower: str) -> bool:
    """
    Detect genuine multi-step commands.

    BUG-01 FIX: Added "play" to the verb set.
    "open chrome and play messi" now correctly returns True.
    "search for cats and dogs" still returns False (no verb after 'and').
    """
    # FIX: multi-step system commands and lock/restart verbs are also valid RHS verbs
    verbs = {
        "open",
        "close",
        "search",
        "type",
        "launch",
        "folder",
        "play",
        "lock",
        "shutdown",
        "restart",
    }

    for sep in (r"\s+and\s+", r"\s+then\s+"):
        parts = re.split(sep, lower, maxsplit=1)
        if len(parts) == 2:
            left_verb  = parts[0].strip().split()[0] if parts[0].strip() else ""
            right_verb = parts[1].strip().split()[0] if parts[1].strip() else ""
            if left_verb in verbs and right_verb in verbs:
                return True

    return False


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def handle_command(command: str) -> dict:
    """
    Route command to the correct operator.
    Always returns {"success": bool, "message": str}.
    """
    command = command.strip()
    logger.info(f"[KIO] handle_command: {command!r}")
    if not command:
        return {"success": False, "message": "Empty command"}

    lower = command.lower()

    try:
        # ── MULTI-STEP ────────────────────────────────────────────────────────
        if _is_multi_step(lower):
            _log_route("route", intent="multi_step", text_len=len(command))
            from mini_kio.core.command_parser import parse_command

            steps = parse_command(command)
            # If connectors were present but parsing returned no steps,
            # treat this as a malformed chain rather than attempting
            # to collapse into a single-step command.
            if not steps:
                if " and " in lower or lower.strip().endswith(" and") or " then " in lower or lower.strip().endswith(" then"):
                    return {"success": False, "message": "Malformed command chain."}
                return {"success": False, "message": f"Could not parse multi-step command: {command!r}"}
            return _execute_multi_step(steps)

        # If connectors present but not identified as multi-step, treat as malformed
        if re.search(r"\b(?:and|then)\b", lower) and not _is_multi_step(lower):
            return {"success": False, "message": "Malformed command chain."}

        # ── SEARCH ────────────────────────────────────────────────────────────
        if lower.startswith("search "):
            query = command[7:].strip()
            _log_route("route", intent="search")
            return execute_action("search_web", query)

        # ── OPEN ──────────────────────────────────────────────────────────────
        if lower.startswith("open "):
            target       = command[5:].strip()
            target_lower = target.lower()
            words        = set(target_lower.split())

            # Folder detection BEFORE launch_app
            if words & _FOLDER_KEYWORDS:
                folder = target_lower.replace("folder", "").strip()
                folder = " ".join(folder.split()) or target_lower
                _log_route("route", intent="open_folder", target=folder)
                return execute_action("open_folder", folder)

            _log_route("route", intent="open_app", target=target)
            return execute_action("open_app", target)

        # ── CLOSE ─────────────────────────────────────────────────────────────
        if lower.startswith("close "):
            target = command[6:].strip()
            _log_route("route", intent="close_app", target=target)
            return execute_action("close_app", target)

        # ── PLAY (YouTube) ────────────────────────────────────────────────────
        if lower.startswith("play "):
            query = command[5:].strip()
            _log_route("route", intent="play_youtube")
            return execute_action("play_youtube", query)

        # ── SEARCH YOUTUBE ────────────────────────────────────────────────────
        if lower.startswith("search youtube "):
            query = command[15:].strip()
            return execute_action("search_youtube", query)

        if lower.startswith("youtube "):
            query = command[8:].strip()
            return execute_action("play_youtube", query)

        # ── SYSTEM ────────────────────────────────────────────────────────────
        if lower in ("shutdown", "shutdown computer", "shut down"):
            return execute_action("shutdown_system")

        if lower in ("restart", "restart computer"):
            return execute_action("restart_system")

        if lower in ("lock", "lock computer"):
            return execute_action("lock_system")

        # ── UTILITY ───────────────────────────────────────────────────────────
        if lower == "ping":
            return {"success": True, "message": "KIO online ✓"}

        if "help" in lower:
            return _show_help()

        # ── AI FALLBACK ───────────────────────────────────────────────────────
        _log_route("route", intent="ai_fallback", text_len=len(command))
        return _ai_fallback(command)

    except Exception as exc:
        logger.exception(f"handle_command unhandled exception: {exc}")
        return {"success": False, "message": f"Internal error: {str(exc)[:120]}"}


def _execute_multi_step(steps: list[dict[str, Any]]) -> dict:
    """Execute parsed multi-step commands through runtime execution policy."""
    results: list[dict[str, Any]] = []
    blocked_count = 0
    success_count = 0

    for idx, step in enumerate(steps, start=1):
        action = step.get("action", "")
        target = step.get("target", "")
        _log_route(
            "execution_policy_apply",
            action=action,
            target=target,
            step=idx,
            total=len(steps),
        )

        result = execute_action(action, target)
        results.append(result)

        if result.get("blocked"):
            blocked_count += 1
            _log_route(
                "execution_policy_blocked",
                action=action,
                target=target,
                step=idx,
            )
            continue

        if result.get("success"):
            success_count += 1
            _log_route(
                "execution_policy_allowed",
                action=action,
                target=target,
                step=idx,
                success=True,
            )
        else:
            _log_route(
                "execution_policy_allowed",
                action=action,
                target=target,
                step=idx,
                success=False,
            )
            return {
                "success": False,
                "message": f"Step {idx} failed: {result.get('message', 'unknown error')}",
                "results": results,
            }

    message = (
        f"Completed {success_count} step(s); blocked {blocked_count} step(s)."
        if blocked_count
        else f"Completed {len(steps)} step(s)."
    )
    return {
        "success": blocked_count == 0 and success_count > 0,
        "message": message,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Telegram-facing entry point
# ---------------------------------------------------------------------------

def route(text: str, user_id: int = 0) -> str:
    """
    Channel-facing dispatcher (compat wrapper).
    Returns a plain-text string.  Never raises.
    """
    try:
        _log_route("route_entry", user_id=user_id, text_len=len(text))
        from mini_kio.core.runtime import dispatch_channel_input, format_channel_reply

        result = dispatch_channel_input(text, channel="telegram", user_id=user_id)
        return format_channel_reply(result)
    except Exception as exc:
        logger.exception(f"route() crashed: {exc}")
        return "KIO encountered an internal error but is still running."


# ---------------------------------------------------------------------------
# AI / Knowledge fallback
# ---------------------------------------------------------------------------

# BUG-04 FIX: Added "what are your features" to knowledge base.
_KNOWLEDGE_BASE: dict[str, str] = {
    "who created you":          "I am KIO, a lightweight AI assistant created by Joel.",
    "what are you":             "I am KIO, a lightweight AI assistant created by Joel.",
    "what is kio":              "KIO is a lightweight desktop AI assistant that can open apps, search the web, play YouTube videos, and more.",
    "what are your features":   (
        "KIO can: open/close applications, search Google, play YouTube videos, "
        "open folders, perform multi-step commands (e.g. 'open chrome and search python'), "
        "and answer general questions via AI fallback."
    ),
    "who is monkey d luffy":    "Monkey D. Luffy is the main protagonist of the One Piece manga/anime by Eiichiro Oda.",
    "what is one piece":        "One Piece is a popular Japanese manga and anime series created by Eiichiro Oda.",
    "explain c programming":    "C is a general-purpose, low-level programming language widely used for systems programming, embedded systems, and performance-critical applications.",
    "what is programming":      "Programming is writing instructions for computers to follow, using languages like Python, C, or JavaScript.",
    "what is computer science": "Computer science is the study of computation, algorithms, data structures, software engineering, and related fields.",
    "what is algorithm":        "An algorithm is a step-by-step procedure for solving a problem.",
    "what is data structure":   "A data structure organises and stores data for efficient access and modification (e.g. arrays, lists, trees).",
    "what is recursion":        "Recursion is when a function calls itself to solve smaller sub-problems until a base case is reached.",
    "explain recursion":        "Recursion is when a function calls itself. Example: factorial(n) = n * factorial(n-1), with factorial(0) = 1.",
    "what is ai":               "AI (Artificial Intelligence) is the simulation of human intelligence by machines, including learning, reasoning, and problem-solving.",
    "binary search":            "Binary search finds a target in a sorted array by repeatedly halving the search range. Time complexity: O(log n).",
}


def _ai_fallback(query: str) -> dict:
    """
    Fallback for unrecognised commands.

    Order:
      1. Knowledge-base lookup (instant, no network).
      2. LLM via llm_router (async, 8 s timeout).
      3. Helpful error message.

    BUG-02 FIX: Removed duplicate unreachable return statements.
    BUG-03 FIX: LLM is now actually called via asyncio.run() instead of
                being hard-disabled with `response = None`.
    """
    q = query.lower().strip()

    # 1. Knowledge base
    for key, answer in _KNOWLEDGE_BASE.items():
        if key in q:
            return {"success": True, "message": answer}

    # 2. LLM providers (attempt with asyncio.run; skip if no event loop available)
    try:
        from mini_kio.core.llm_router import ask_llm
        response = asyncio.run(ask_llm(query, timeout=8.0, max_tokens=200))
        if response:
            return {"success": True, "message": response}
    except RuntimeError:
        # asyncio.run() cannot be called when a loop is already running
        logger.debug("asyncio.run() skipped — already inside an event loop")
    except Exception as exc:
        logger.warning(f"LLM fallback failed: {exc}")

    # 3. Graceful unknown
    return {
        "success": False,
        "message": (
            f"I don't know how to handle '{query}'. "
            "Try: 'open chrome', 'search python tutorial', or 'play messi highlights'."
        ),
    }


def _show_help() -> dict:
    return {
        "success": True,
        "message": (
            "KIO Commands\n"
            "─────────────────────────────────\n"
            "open <app>             open chrome / calculator / notepad / vscode\n"
            "open <folder>          open downloads folder / desktop / documents\n"
            "close <app>            close chrome\n"
            "search <query>         search Google\n"
            "play <query>           play on YouTube\n"
            "open chrome and search <query>   multi-step\n"
            "open chrome and play <query>     multi-step\n"
            "shutdown / restart / lock\n"
            "ping                   check KIO status\n"
            "help                   show this message"
        ),
    }


__all__ = ["handle_command", "route"]
