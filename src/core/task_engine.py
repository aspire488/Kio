"""
Task Engine - Execute multi-step commands sequentially.

Key improvements:
1. Parses and executes multi-step commands: "open X and search Y"
2. Proper waits between steps for windows to appear
3. No window focus logic (removed)
4. Proper error handling — stops on first failure
5. Structured responses with step-by-step results
6. Folder action support
"""

from __future__ import annotations

import logging
import time
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Delays between steps (seconds)
_INTER_STEP_DELAY = 1.0         # Normal delay between steps
_BROWSER_STARTUP_DELAY = 2.0    # Extra delay after browser launch


def run_task(command: str) -> dict:
    """
    Parse and execute a multi-step command.
    
    Args:
        command: Command string like "open chrome and search python"
        
    Returns:
        {"success": bool, "message": str, "results": [...]}
    """
    logger.info(f"[TASK] run_task: {command!r}")

    try:
        from .command_parser import parse_command
    except ImportError:
        from command_parser import parse_command

    # Parse the command into steps
    steps = parse_command(command)
    if not steps:
        return {
            "success": False,
            "message": f"Could not parse command: {command!r}"
        }

    logger.debug(f"[TASK] parsed {len(steps)} step(s): {steps}")
    
    # Execute all steps
    return execute_steps(steps)


def execute_steps(steps: List[Dict[str, Any]]) -> dict:
    """
    Execute a list of parsed steps sequentially.
    
    Args:
        steps: List of {"action": str, "target": str} dicts
        
    Returns:
        {"success": bool, "message": str, "results": [...]}
    """
    if not steps:
        return {"success": False, "message": "No steps to execute"}

    results = []
    prev_action = None

    for i, step in enumerate(steps):
        action = step.get("action", "")
        target = step.get("target", "")

        logger.info(f"[TASK] Step {i + 1}/{len(steps)}: {action} → {target!r}")

        # Inject extra delay after browser launch before search
        if action == "search" and prev_action == "open":
            logger.debug(f"[TASK] waiting {_BROWSER_STARTUP_DELAY}s for browser")
            time.sleep(_BROWSER_STARTUP_DELAY)

        # Execute this step
        result = _execute_step(action, target)
        results.append(result)

        # Stop on failure
        if not result.get("success"):
            msg = result.get("message", "unknown error")
            logger.warning(f"[TASK] Step {i + 1} failed: {msg}")
            return {
                "success": False,
                "message": f"Step {i + 1} ({action} {target}) failed: {msg}",
                "results": results,
            }

        prev_action = action

        # Inter-step delay (but not after the last step)
        if i < len(steps) - 1:
            logger.debug(f"[TASK] waiting {_INTER_STEP_DELAY}s before next step")
            time.sleep(_INTER_STEP_DELAY)

    # All steps succeeded
    step_summary = ", ".join(f"{s.get('action')} {s.get('target')}" for s in steps)
    return {
        "success": True,
        "message": f"Completed {len(steps)} step(s): {step_summary}",
        "results": results,
    }


def _execute_step(action: str, target: str) -> dict:
    """
    Execute a single step.
    
    Args:
        action: Action type (open, close, search, folder, type)
        target: Target argument
        
    Returns:
        {"success": bool, "message": str}
    """
    try:
        # ── OPEN ──────────────────────────────────────────────────────────────
        if action == "open":
            try:
                from .app_operator import launch_app
            except ImportError:
                from app_operator import launch_app
            return launch_app(target)

        # ── CLOSE ─────────────────────────────────────────────────────────────
        if action == "close":
            try:
                from .app_operator import close_app
            except ImportError:
                from app_operator import close_app
            return close_app(target)

        # ── SEARCH ────────────────────────────────────────────────────────────
        if action == "search":
            try:
                from .app_operator import search_web
            except ImportError:
                from app_operator import search_web
            return search_web(target)

        # ── FOLDER ────────────────────────────────────────────────────────────
        if action == "folder":
            try:
                from .file_operator import open_folder
            except ImportError:
                from file_operator import open_folder
            return open_folder(target)

        # ── YOUTUBE PLAY ───────────────────────────────────────────────────────
        if action == "youtube_play":
            try:
                from .browser_operator import play_youtube
            except ImportError:
                from browser_operator import play_youtube
            return play_youtube(target)

        # ── SEARCH YOUTUBE ─────────────────────────────────────────────────────
        if action == "search_youtube":
            try:
                from .browser_operator import search_youtube
            except ImportError:
                from browser_operator import search_youtube
            return search_youtube(target)

        # Unknown action
        logger.warning(f"[TASK] unknown action: {action!r}")
        return {"success": False, "message": f"Unknown action: {action}"}

    except Exception as e:
        logger.exception(f"[TASK] step {action!r} raised: {e}")
        return {"success": False, "message": str(e)[:100]}


def _type_text(text: str) -> dict:
    """
    Type text using pyautogui (optional).
    
    This action fails gracefully if pyautogui is not installed.
    """
    try:
        import pyautogui
        time.sleep(0.5)
        pyautogui.typewrite(text, interval=0.05)
        logger.info(f"[TASK] typed: {text!r}")
        return {"success": True, "message": f"Typed: {text}"}
    except ImportError:
        logger.warning("[TASK] pyautogui not installed — type action unavailable")
        return {"success": False, "message": "pyautogui not available for type action"}
    except Exception as e:
        logger.error(f"[TASK] type error: {e}")
        return {"success": False, "message": f"Type failed: {str(e)[:80]}"}


__all__ = ["run_task", "execute_steps"]
