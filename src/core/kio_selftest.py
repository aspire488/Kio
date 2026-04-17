"""
Mini-KIO Self Test - lightweight health check for the core system.

Run with:
    python -m mini_kio.core.kio_selftest
"""

from __future__ import annotations

import importlib
import logging
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TESTS: list[tuple[str, Any]] = []


class SelfTestResult:
    def __init__(self, name: str, passed: bool, details: str = "") -> None:
        self.name = name
        self.passed = passed
        self.details = details

    def format(self) -> str:
        status = "[OK]" if self.passed else "[FAIL]"
        suffix = f" - {self.details}" if self.details else ""
        return f"{status} {self.name}{suffix}"


def _run_test(name: str, fn: Any) -> SelfTestResult:
    try:
        result = fn()
        if isinstance(result, SelfTestResult):
            return result
        return SelfTestResult(name, bool(result), str(result) if not result else "")
    except Exception as exc:
        return SelfTestResult(name, False, f"{type(exc).__name__}: {exc}")


def _test_imports() -> SelfTestResult:
    modules = [
        "mini_kio.core.command_parser",
        "mini_kio.core.command_router",
        "mini_kio.core.app_operator",
        "mini_kio.core.file_operator",
        "mini_kio.core.system_operator",
        "mini_kio.core.task_engine",
    ]
    failed: list[str] = []
    for module in modules:
        try:
            importlib.import_module(module)
        except Exception as exc:
            failed.append(f"{module}: {type(exc).__name__}: {exc}")
    if failed:
        return SelfTestResult("module imports", False, "; ".join(failed))
    return SelfTestResult("module imports", True)


def _test_command_parsing() -> SelfTestResult:
    from core.command_parser import parse_command

    test_cases = [
        ("open chrome", 1),
        ("open chrome and search python", 2),
        ("search python tutorial", 1),
        ("open downloads folder", 1),
    ]
    for command, expected in test_cases:
        steps = parse_command(command)
        if len(steps) != expected:
            return SelfTestResult(
                "command parsing",
                False,
                f"{command!r} returned {len(steps)} steps, expected {expected}",
            )
    return SelfTestResult("command parsing", True)


def _test_multi_step_parsing() -> SelfTestResult:
    from core.command_parser import parse_command

    steps = parse_command("open chrome and search AI news")
    if len(steps) != 2:
        return SelfTestResult("multi-step parsing", False, "expected 2 parsed steps")
    actions = [step.get("action") for step in steps]
    if actions != ["open", "search"]:
        return SelfTestResult(
            "multi-step parsing", False, f"unexpected actions: {actions}"
        )
    return SelfTestResult("multi-step parsing", True)


def _test_router_dispatch() -> SelfTestResult:
    from core.command_router import handle_command

    result = handle_command("ping")
    if not isinstance(result, dict):
        return SelfTestResult(
            "router dispatch", False, "handle_command did not return dict"
        )
    if not result.get("success"):
        return SelfTestResult(
            "router dispatch", False, f"ping failed: {result.get('message')}"
        )
    return SelfTestResult("router dispatch", True)


def _test_structured_responses() -> SelfTestResult:
    from core.command_router import handle_command

    result = handle_command("help")
    if not isinstance(result, dict):
        return SelfTestResult("structured responses", False, "result is not a dict")
    if "message" not in result:
        return SelfTestResult("structured responses", False, "missing message field")
    return SelfTestResult("structured responses", True)


def _test_folder_alias_detection() -> SelfTestResult:
    from core.file_operator import open_folder

    result = open_folder("downloads folder")
    if not isinstance(result, dict):
        return SelfTestResult("folder alias detection", False, "result is not a dict")
    if "success" not in result or "message" not in result:
        return SelfTestResult(
            "folder alias detection", False, "missing structured fields"
        )
    return SelfTestResult("folder alias detection", True)


def _test_url_encoding() -> SelfTestResult:
    import urllib.parse

    raw = "python tutorial with ai"
    encoded = urllib.parse.quote_plus(raw)
    if encoded != "python+tutorial+with+ai":
        return SelfTestResult(
            "url encoding",
            False,
            f"got {encoded!r}",
        )
    return SelfTestResult("url encoding", True)


def _test_telegram_handler_simulation() -> SelfTestResult:
    from core.command_router import route

    response = route("search python tutorial", user_id=123)
    if not isinstance(response, str):
        return SelfTestResult(
            "telegram simulation", False, "route did not return string"
        )
    if not response:
        return SelfTestResult("telegram simulation", False, "empty response")
    return SelfTestResult("telegram simulation", True)


def _test_subprocess_safety() -> SelfTestResult:
    import inspect
    import re
    from core import app_operator

    source = inspect.getsource(app_operator)
    cleaned_source = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    if re.search(r"shell\s*=\s*True", cleaned_source):
        return SelfTestResult(
            "subprocess safety", False, "shell=True detected in app_operator"
        )
    if "subprocess.Popen" in cleaned_source and "shell=False" not in cleaned_source:
        return SelfTestResult(
            "subprocess safety", False, "subprocess.Popen usage may be unsafe"
        )
    return SelfTestResult("subprocess safety", True)


def _get_memory_usage_mb() -> float | None:
    try:
        import psutil

        proc = psutil.Process()
        return proc.memory_info().rss / 1024.0 / 1024.0
    except ImportError:
        return None
    except Exception:
        return None


def _test_conversation_fallback() -> SelfTestResult:
    from core.command_router import handle_command

    # Test knowledge base
    result = handle_command("who created you")
    if not isinstance(result, dict) or not result.get("success"):
        return SelfTestResult(
            "conversation fallback", False, "knowledge base lookup failed"
        )

    if "Joel" not in result.get("message", ""):
        return SelfTestResult(
            "conversation fallback", False, "wrong knowledge base answer"
        )

    # Test unknown query (should still return structured response)
    result = handle_command("some unknown query xyz")
    if not isinstance(result, dict):
        return SelfTestResult(
            "conversation fallback", False, "unknown query didn't return dict"
        )

    return SelfTestResult("conversation fallback", True)


def _test_generic_app_launcher() -> SelfTestResult:
    from core.app_operator import launch_app

    # Test known apps
    test_apps = ["chrome", "notepad", "calculator"]
    for app in test_apps:
        result = launch_app(app)
        if not isinstance(result, dict):
            return SelfTestResult(
                "generic app launcher", False, f"{app} didn't return dict"
            )
        if "success" not in result or "message" not in result:
            return SelfTestResult(
                "generic app launcher", False, f"{app} missing structured fields"
            )

    return SelfTestResult("generic app launcher", True)


def _test_close_commands() -> SelfTestResult:
    from core.app_operator import close_app

    # Test close commands (these should return structured responses even if app not running)
    test_apps = ["chrome", "notepad", "calculator"]
    for app in test_apps:
        result = close_app(app)
        if not isinstance(result, dict):
            return SelfTestResult(
                "close commands", False, f"{app} close didn't return dict"
            )
        if "success" not in result or "message" not in result:
            return SelfTestResult(
                "close commands", False, f"{app} close missing structured fields"
            )

    return SelfTestResult("close commands", True)


def _test_youtube_play() -> SelfTestResult:
    from core.browser_operator import play_youtube
    from core.command_router import handle_command

    # Test direct function call
    result = play_youtube("test query")
    if not isinstance(result, dict):
        return SelfTestResult("youtube play", False, "result is not a dict")
    if "success" not in result or "message" not in result:
        return SelfTestResult("youtube play", False, "missing structured fields")

    # Test command parsing
    parsed = handle_command("play messi")
    if not parsed.get("success"):
        return SelfTestResult(
            "youtube play", False, f"command failed: {parsed.get('message')}"
        )

    return SelfTestResult("youtube play", True)


def _test_browser_operations() -> SelfTestResult:
    from core.browser_operator import search_google, search_youtube

    # Test Google search
    result = search_google("test")
    if not isinstance(result, dict):
        return SelfTestResult(
            "browser operations", False, "Google search result is not a dict"
        )

    # Test YouTube search
    result = search_youtube("test")
    if not isinstance(result, dict):
        return SelfTestResult(
            "browser operations", False, "YouTube search result is not a dict"
        )

    return SelfTestResult("browser operations", True)


def _test_expanded_knowledge() -> SelfTestResult:
    from core.command_router import handle_command

    test_queries = [
        "who is monkey d luffy",
        "what is one piece",
        "explain c programming",
        "what is programming",
        "what is computer science",
        "what is algorithm",
        "what is data structure",
    ]

    for query in test_queries:
        result = handle_command(query)
        if not isinstance(result, dict) or not result.get("success"):
            return SelfTestResult(
                "expanded knowledge", False, f"Failed on query: {query}"
            )

    return SelfTestResult("expanded knowledge", True)


def _test_memory_usage() -> SelfTestResult:
    mem_mb = _get_memory_usage_mb()
    if mem_mb is None:
        return SelfTestResult(
            "memory usage",
            False,
            "psutil unavailable; install psutil to verify memory usage",
        )
    if mem_mb > 150.0:
        return SelfTestResult(
            "memory usage",
            False,
            f"process uses {mem_mb:.1f} MB (>150 MB)",
        )
    return SelfTestResult("memory usage", True, f"{mem_mb:.1f} MB")


def run_selftest() -> dict[str, Any]:
    tests = [
        _test_imports,
        _test_command_parsing,
        _test_multi_step_parsing,
        _test_router_dispatch,
        _test_structured_responses,
        _test_subprocess_safety,
        _test_folder_alias_detection,
        _test_url_encoding,
        _test_telegram_handler_simulation,
        _test_conversation_fallback,
        _test_generic_app_launcher,
        _test_close_commands,
        _test_youtube_play,
        _test_browser_operations,
        _test_expanded_knowledge,
        _test_memory_usage,
    ]

    print("KIO SELF TEST")
    print("--------------")
    results: list[SelfTestResult] = []
    for test in tests:
        result = _run_test(test.__name__, test)
        results.append(result)
        print(result.format())
        time.sleep(0.05)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    print("\nRESULT:", "SYSTEM HEALTHY" if failed == 0 else "FAILURES DETECTED")
    print(f"{passed}/{len(results)} tests passed")

    return {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": [
            {"name": r.name, "passed": r.passed, "details": r.details} for r in results
        ],
    }


if __name__ == "__main__":
    run_selftest()
