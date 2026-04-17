"""
Command Router - Main routing engine with multi-step support.

The route() function is the Telegram bot entry point.
The handle_command() function is the internal routing handler.

Routing rules:
1. Multi-step commands ("X and Y", "X then Y") → task_engine
2. "search X" → search_web() directly
3. "open X" where X has folder keywords → open_folder()
4. "open X" where X is app → launch_app()
5. "close X" → close_app()
6. System commands → system_operator
7. Utilities (ping, help) → direct response
8. Unknown → AI fallback
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Import operators lazily to avoid circular imports
_task_engine = None
_app_operator = None
_file_operator = None
_system_operator = None
_ai = None


def _lazy_import(module_name: str, item_names: list[str]) -> dict:
    """Lazy import with error handling."""
    try:
        if module_name == "task_engine":
            from core.task_engine import run_task

            return {"run_task": run_task}
        elif module_name == "app_operator":
            from core.app_operator import launch_app, close_app, search_web

            return {
                "launch_app": launch_app,
                "close_app": close_app,
                "search_web": search_web,
            }
        elif module_name == "file_operator":
            from core.file_operator import open_folder

            return {"open_folder": open_folder}
        elif module_name == "system_operator":
            from core.system_operator import (
                shutdown_system,
                restart_system,
                lock_system,
            )

            return {
                "shutdown_system": shutdown_system,
                "restart_system": restart_system,
                "lock_system": lock_system,
            }
        elif module_name == "browser_operator":
            from core.browser_operator import (
                open_url,
                search_google,
                search_youtube,
                play_youtube,
            )

            return {
                "open_url": open_url,
                "search_google": search_google,
                "search_youtube": search_youtube,
                "play_youtube": play_youtube,
            }
        elif module_name == "ai":
            from core.ai import ask_ai

            return {"ask_ai": ask_ai}
    except ImportError as e:
        logger.warning(f"Failed to import {module_name}: {e}")
    return {}


def _log_route(event: str, **fields: Any) -> None:
    """Log routing decision."""
    payload = {"evt": event}
    payload.update(fields)
    logger.info(json.dumps(payload, default=str))


# Folder keywords for routing
_FOLDER_KEYWORDS = {
    "downloads",
    "desktop",
    "documents",
    "pictures",
    "music",
    "videos",
    "home",
    "appdata",
}


def _is_multi_step(lower: str) -> bool:
    """Detect genuine multi-step commands vs queries containing connectors."""
    verbs = {"open", "close", "search", "type", "launch", "folder"}

    for sep in (r"\s+and\s+", r"\s+then\s+"):
        parts = re.split(sep, lower, maxsplit=1)
        if len(parts) == 2:
            left_verb = parts[0].strip().split()[0] if parts[0].strip() else ""
            right_verb = parts[1].strip().split()[0] if parts[1].strip() else ""
            if left_verb in verbs and right_verb in verbs:
                return True

    return False


def handle_command(command: str) -> dict:
    """
    Route command to appropriate handler.

    Returns:
        {"success": bool, "message": str, ...}
    """
    command = command.strip()
    logger.info(f"[KIO] command parsed: {command!r}")
    if not command:
        return {"success": False, "message": "Empty command"}

    lower = command.lower()

    try:
        # ── MULTI-STEP (and / then) ────────────────────────────────────────────
        if _is_multi_step(lower):
            _log_route("route", intent="multi_step", text_len=len(command))
            task_funcs = _lazy_import("task_engine", ["run_task"])
            if "run_task" in task_funcs:
                result = task_funcs["run_task"](command)
                logger.info(f"[KIO] routing: multi-step task executed")
                return result
            return {"success": False, "message": "Task engine unavailable"}

        # ── SEARCH ────────────────────────────────────────────────────────────
        if lower.startswith("search "):
            query = command[7:].strip()
            _log_route("route", intent="search", text_len=len(command))
            app_funcs = _lazy_import("app_operator", ["search_web"])
            if "search_web" in app_funcs:
                result = app_funcs["search_web"](query)
                logger.info(f"[KIO] routing: web search for {query!r}")
                return result
            return {"success": False, "message": "Search unavailable"}

        # ── OPEN ───────────────────────────────────────────────────────────────
        if lower.startswith("open "):
            target = command[5:].strip()
            target_lower = target.lower()

            # Check if target contains folder keywords
            words_in_target = set(target_lower.split())
            if words_in_target & _FOLDER_KEYWORDS:
                # Strip the word "folder" if present
                folder_name = target_lower.replace("folder", "").strip()
                if not folder_name:
                    folder_name = target_lower
                folder_name = " ".join(folder_name.split())
                _log_route("route", intent="open_folder", target=folder_name)
                file_funcs = _lazy_import("file_operator", ["open_folder"])
                if "open_folder" in file_funcs:
                    result = file_funcs["open_folder"](folder_name)
                    logger.info(f"[KIO] routing: opened folder {folder_name!r}")
                    return result
                return {"success": False, "message": "File operator unavailable"}

            # Generic app open
            _log_route("route", intent="open_app", target=target)
            app_funcs = _lazy_import("app_operator", ["launch_app"])
            if "launch_app" in app_funcs:
                result = app_funcs["launch_app"](target)
                logger.info(f"[KIO] routing: launched app {target!r}")
                return result
            return {"success": False, "message": "App operator unavailable"}

        # ── CLOSE ──────────────────────────────────────────────────────────────
        if lower.startswith("close "):
            target = command[6:].strip()
            _log_route("route", intent="close_app", target=target)
            app_funcs = _lazy_import("app_operator", ["close_app"])
            if "close_app" in app_funcs:
                result = app_funcs["close_app"](target)
                logger.info(f"[KIO] routing: closed app {target!r}")
                return result
            return {"success": False, "message": "App operator unavailable"}

        # ── PLAY ────────────────────────────────────────────────────────────────
        if lower.startswith("play "):
            query = command[5:].strip()
            _log_route("route", intent="play_youtube", text_len=len(command))
            browser_funcs = _lazy_import("browser_operator", ["play_youtube"])
            if "play_youtube" in browser_funcs:
                result = browser_funcs["play_youtube"](query)
                logger.info(f"[KIO] routing: playing YouTube {query!r}")
                return result
            return {"success": False, "message": "Browser operator unavailable"}

        # ── SEARCH YOUTUBE ─────────────────────────────────────────────────────
        if lower.startswith("search youtube "):
            query = command[14:].strip()  # "search youtube " is 14 chars
            _log_route("route", intent="search_youtube", text_len=len(command))
            browser_funcs = _lazy_import("browser_operator", ["search_youtube"])
            if "search_youtube" in browser_funcs:
                result = browser_funcs["search_youtube"](query)
                logger.info(f"[KIO] routing: YouTube search for {query!r}")
                return result
            return {"success": False, "message": "Browser operator unavailable"}

        # ── YOUTUBE (direct) ───────────────────────────────────────────────────
        if lower.startswith("youtube "):
            query = command[8:].strip()  # "youtube " is 8 chars
            _log_route("route", intent="play_youtube", text_len=len(command))
            browser_funcs = _lazy_import("browser_operator", ["play_youtube"])
            if "play_youtube" in browser_funcs:
                result = browser_funcs["play_youtube"](query)
                logger.info(f"[KIO] routing: YouTube {query!r}")
                return result
            return {"success": False, "message": "Browser operator unavailable"}

        # ── SYSTEM ────────────────────────────────────────────────────────────
        if lower in ("shutdown computer", "shutdown", "shut down"):
            sys_funcs = _lazy_import("system_operator", ["shutdown_system"])
            if "shutdown_system" in sys_funcs:
                result = sys_funcs["shutdown_system"]()
                logger.info(f"[KIO] routing: system shutdown")
                return result
            return {"success": False, "message": "System operator unavailable"}

        if lower in ("restart computer", "restart"):
            sys_funcs = _lazy_import("system_operator", ["restart_system"])
            if "restart_system" in sys_funcs:
                result = sys_funcs["restart_system"]()
                logger.info(f"[KIO] routing: system restart")
                return result
            return {"success": False, "message": "System operator unavailable"}

        if lower in ("lock computer", "lock"):
            sys_funcs = _lazy_import("system_operator", ["lock_system"])
            if "lock_system" in sys_funcs:
                result = sys_funcs["lock_system"]()
                logger.info(f"[KIO] routing: system lock")
                return result
            return {"success": False, "message": "System operator unavailable"}

        # ── UTILITY ───────────────────────────────────────────────────────────
        if lower == "ping":
            logger.info(f"[KIO] routing: ping response")
            return {"success": True, "message": "KIO online"}

        if "help" in lower:
            logger.info(f"[KIO] routing: help requested")
            return _show_help()

        # ── AI FALLBACK ───────────────────────────────────────────────────────
        _log_route("route", intent="ai_fallback", text_len=len(command))
        result = _ai_fallback(command)
        logger.info(f"[KIO] routing: AI fallback for {command!r}")
        return result

    except Exception as e:
        logger.exception(f"handle_command crashed: {e}")
        return {"success": False, "message": f"Internal error: {str(e)[:100]}"}


def route(text: str, user_id: int = 0) -> str:
    """
    Telegram-facing entry point.

    Used by telegram_bot.py to forward messages to KIO.

    Args:
        text: User message
        user_id: Telegram user ID (for logging)

    Returns:
        Plain text response string
    """
    try:
        _log_route("route_entry", user_id=user_id, text_len=len(text))
        result = handle_command(text)

        if result.get("success"):
            msg = result.get("message", "Done.")
            logger.info(f"[KIO] response returned: success=True message={msg!r}")
            return msg if msg else "Done."
        else:
            msg = result.get("message", "Command failed.")
            logger.info(f"[KIO] response returned: success=False message={msg!r}")
            return f"Error: {msg}"
    except Exception as e:
        logger.exception(f"route() crashed: {e}")
        return "KIO encountered an internal error but is still running."


def _ai_fallback(query: str) -> dict:
    """Send unknown query to AI model or knowledge base."""
    query_lower = query.lower().strip()

    # Knowledge base lookup
    knowledge_base = {
        "recursion": "Recursion is when a function calls itself to solve smaller versions of a problem.",
        "binary search": "Binary search is an efficient algorithm that finds the position of a target value within a sorted array by repeatedly dividing the search interval in half.",
        "stack vs queue": "A stack follows LIFO (Last In, First Out) while a queue follows FIFO (First In, First Out).",
        "python list": "A Python list is a mutable, ordered collection of items that can contain elements of different types.",
        "difference between list and tuple": "Lists are mutable (can be changed) while tuples are immutable (cannot be changed after creation).",
        "what is ai": "AI, or Artificial Intelligence, is the simulation of human intelligence processes by machines, especially computer systems.",
        "who created you": "I am KIO, a lightweight AI assistant created by Joel.",
        "what are you": "I am KIO, a lightweight AI assistant created by Joel.",
        "who is monkey d luffy": "Monkey D. Luffy is the main character of the anime and manga One Piece created by Eiichiro Oda.",
        "what is one piece": "One Piece is a popular Japanese manga and anime series created by Eiichiro Oda, following the adventures of Monkey D. Luffy and his pirate crew.",
        "explain c programming": "C is a general-purpose programming language that provides low-level access to memory and is widely used for system programming, embedded systems, and performance-critical applications.",
        "what is programming": "Programming is the process of creating instructions for computers to follow, using programming languages to solve problems and automate tasks.",
        "what is computer science": "Computer science is the study of computers and computational systems, including algorithms, data structures, programming languages, and software engineering.",
        "what is algorithm": "An algorithm is a step-by-step procedure or formula for solving a problem, often used in computer programming and mathematics.",
        "what is data structure": "A data structure is a way of organizing and storing data so that it can be accessed and modified efficiently, such as arrays, lists, stacks, and trees.",
    }

    # Check knowledge base first
    for key, answer in knowledge_base.items():
        if key in query_lower:
            return {"success": True, "message": answer}

    # Try LLM providers
    try:
        import asyncio
        from core.llm_router import ask_llm

        # Since we're in a sync context, we can't await, so skip LLM for now
        # response = asyncio.run(ask_llm(query, timeout=8, max_tokens=200))
        response = None
        if response:
            return {"success": True, "message": response}
    except Exception as e:
        logger.warning(f"LLM fallback failed: {e}")

    # Default response
    return {
        "success": False,
        "message": f"I don't understand '{query}'. Try commands like 'open chrome' or 'search python tutorial'.",
    }

    # Default response
    return {
        "success": False,
        "message": f"I don't understand '{query}'. Try commands like 'open chrome' or 'search python tutorial'.",
    }


def _show_help() -> dict:
    """Return help text."""
    help_text = """KIO Commands:

APPS:
  open chrome        Open Chrome browser
  open calculator    Open Calculator
  open notepad       Open Notepad
  open vscode        Open Visual Studio Code
  open edge          Open Microsoft Edge
  close <app>        Close application

FOLDERS:
  open downloads folder
  open desktop
  open documents
  open pictures

SEARCH:
  search <query>     Search Google
  search python tutorial

SYSTEM:
  shutdown           Shutdown computer
  restart            Restart computer
  lock               Lock workstation

MULTI-STEP (using 'and' or 'then'):
  open chrome and search python tutorial
  open chrome then search AI news
  open notepad and type hello

UTILITY:
  ping               Check KIO status
  help               Show this help
"""
    return {"success": True, "message": help_text.strip()}


__all__ = ["handle_command", "route"]
