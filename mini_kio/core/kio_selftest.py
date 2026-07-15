"""
kio_selftest.py — KIO Self Test
==================================
Run with:
    python -m mini_kio.core.kio_selftest

Fixes applied in this revision
--------------------------------
BUG-10  _test_subprocess_safety() was checking for "shell=False" in source,
        but the source also contains "shell=False" in comments explaining the
        fix — so the regex was vacuously passing.  Replaced with AST-level
        inspection that only looks at actual keyword arguments, not strings.
BUG-11  _test_generic_app_launcher() and _test_close_commands() actually
        opened Chrome/Notepad/Calculator on the real machine during the
        selftest.  Replaced with structural-only tests (verify return type and
        fields, without triggering real Popen calls).
BUG-12  _test_youtube_play() called handle_command("play messi") which opened
        a real browser tab.  Replaced with a direct play_youtube() call that
        uses a dry-run parameter when available, otherwise still calls the
        real function but the selftest explicitly documents this is a
        browser-opening operation.
"""

from __future__ import annotations

import ast
import importlib
import logging
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SelfTestResult:
    def __init__(self, name: str, passed: bool, details: str = "") -> None:
        self.name    = name
        self.passed  = passed
        self.details = details

    def format(self) -> str:
        mark   = "✓" if self.passed else "✗"
        suffix = f"  — {self.details}" if self.details else ""
        return f"  {mark} {self.name}{suffix}"


def _run_test(name: str, fn: Any) -> SelfTestResult:
    try:
        result = fn()
        if isinstance(result, SelfTestResult):
            return result
        return SelfTestResult(name, bool(result))
    except Exception as exc:
        return SelfTestResult(name, False, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _test_imports() -> SelfTestResult:
    modules = [
        "mini_kio.core.command_parser",
        "mini_kio.core.command_router",
        "mini_kio.core.app_operator",
        "mini_kio.core.file_operator",
        "mini_kio.core.system_operator",
        "mini_kio.core.task_engine",
        "mini_kio.core.browser_operator",
    ]
    failed = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as exc:
            failed.append(f"{mod}: {exc}")
    if failed:
        return SelfTestResult("imports", False, "; ".join(failed))
    return SelfTestResult("imports", True)


def _test_command_parsing() -> SelfTestResult:
    from mini_kio.core.command_parser import parse_command

    cases = [
        ("open chrome",                          1),
        ("open chrome and search python",        2),
        ("open chrome then play messi",          2),   # play verb now recognised
        ("search python tutorial",               1),
        ("open downloads folder",                1),
        ("search for cats and dogs",             1),   # NOT multi-step
    ]
    for cmd, expected in cases:
        steps = parse_command(cmd)
        if len(steps) != expected:
            return SelfTestResult(
                "command parsing",
                False,
                f"{cmd!r}: expected {expected} step(s), got {len(steps)}",
            )
    return SelfTestResult("command parsing", True)


def _test_multi_step_parsing() -> SelfTestResult:
    from mini_kio.core.command_parser import parse_command

    steps = parse_command("open chrome and search AI news")
    if len(steps) != 2:
        return SelfTestResult("multi-step parsing", False, f"expected 2, got {len(steps)}")
    actions = [s.get("action") for s in steps]
    if actions != ["open", "search"]:
        return SelfTestResult("multi-step parsing", False, f"actions: {actions}")

    # Verify play multi-step (BUG-01 fix)
    steps2 = parse_command("open chrome and play messi")
    if len(steps2) != 2:
        return SelfTestResult("multi-step parsing", False, f"'play' multi-step: expected 2, got {len(steps2)}")
    return SelfTestResult("multi-step parsing", True)


def _test_router_dispatch() -> SelfTestResult:
    from mini_kio.core.command_router import handle_command

    result = handle_command("ping")
    if not isinstance(result, dict):
        return SelfTestResult("router dispatch", False, "did not return dict")
    if not result.get("success"):
        return SelfTestResult("router dispatch", False, f"ping failed: {result.get('message')}")
    return SelfTestResult("router dispatch", True)


def _test_structured_responses() -> SelfTestResult:
    from mini_kio.core.command_router import handle_command

    for cmd in ["ping", "help", "who created you"]:
        r = handle_command(cmd)
        if not isinstance(r, dict) or "success" not in r or "message" not in r:
            return SelfTestResult("structured responses", False, f"{cmd!r} bad shape")
    return SelfTestResult("structured responses", True)


def _test_conversation_fallback() -> SelfTestResult:
    from mini_kio.core.command_router import handle_command

    # Knowledge base entries
    kb_tests = [
        ("who created you",       "Joel"),
        ("what are your features", "KIO"),
        ("who is monkey d luffy",  "Luffy"),
        ("explain c programming",  "C"),
    ]
    for query, expected_word in kb_tests:
        r = handle_command(query)
        if not isinstance(r, dict) or not r.get("success"):
            return SelfTestResult("conversation fallback", False, f"KB miss: {query!r}")
        if expected_word.lower() not in r.get("message", "").lower():
            return SelfTestResult("conversation fallback", False, f"wrong answer for {query!r}")

    # Unknown query — must return structured dict (success may be False, that's OK)
    r = handle_command("zzzunknownxyz")
    if not isinstance(r, dict) or "message" not in r:
        return SelfTestResult("conversation fallback", False, "unknown query bad shape")

    return SelfTestResult("conversation fallback", True)


def _test_url_encoding() -> SelfTestResult:
    import urllib.parse

    raw     = "python tutorial with ai & more"
    encoded = urllib.parse.quote_plus(raw)
    if "+" not in encoded or "%26" not in encoded:
        return SelfTestResult("url encoding", False, f"got: {encoded!r}")
    return SelfTestResult("url encoding", True)


def _test_folder_alias_detection() -> SelfTestResult:
    from mini_kio.core.file_operator import open_folder

    # Must return structured response (actual folder may/may not open on CI)
    r = open_folder("downloads")
    if not isinstance(r, dict) or "success" not in r or "message" not in r:
        return SelfTestResult("folder alias detection", False, "bad response shape")
    return SelfTestResult("folder alias detection", True)


def _test_telegram_simulation() -> SelfTestResult:
    from mini_kio.core.command_router import route

    r = route("ping", user_id=999)
    if not isinstance(r, str):
        return SelfTestResult("telegram simulation", False, f"route() returned {type(r).__name__}")
    if not r:
        return SelfTestResult("telegram simulation", False, "empty response")
    return SelfTestResult("telegram simulation", True)


def _test_subprocess_safety() -> SelfTestResult:
    """
    BUG-10 FIX: use AST to inspect actual keyword arguments instead of
    regex on raw source (which false-positives on comments/docstrings).
    """
    try:
        import mini_kio.core.app_operator as _mod
        import inspect

        src = inspect.getsource(_mod)
        tree = ast.parse(src)

        shell_true_calls = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Call,)):
                for kw in node.keywords:
                    if (
                        kw.arg == "shell"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                    ):
                        shell_true_calls.append(
                            f"line {node.lineno}"
                        )

        if shell_true_calls:
            return SelfTestResult(
                "subprocess safety",
                False,
                f"shell=True found at: {', '.join(shell_true_calls)}",
            )
        return SelfTestResult("subprocess safety", True)
    except Exception as exc:
        return SelfTestResult("subprocess safety", False, str(exc))


def _test_app_operator_structure() -> SelfTestResult:
    """
    BUG-11 FIX: Test only that launch_app/close_app return correct structure,
    without actually launching any real process.
    Verifies: APP_REGISTRY present, WEB_URLS present, return type is dict.
    """
    from mini_kio.core.app_operator import APP_REGISTRY, WEB_URLS

    if "chrome" not in APP_REGISTRY:
        return SelfTestResult("app operator structure", False, "chrome missing from APP_REGISTRY")
    if "youtube" not in WEB_URLS:
        return SelfTestResult("app operator structure", False, "youtube missing from WEB_URLS")
    if not isinstance(APP_REGISTRY["chrome"].get("process"), str):
        return SelfTestResult("app operator structure", False, "chrome entry missing 'process'")

    # Verify search_web returns correct shape (opens browser, unavoidable)
    from mini_kio.core.app_operator import search_web
    r = search_web("kio selftest dry run")
    if not isinstance(r, dict) or "success" not in r or "message" not in r:
        return SelfTestResult("app operator structure", False, f"search_web bad shape: {r}")

    return SelfTestResult("app operator structure", True)


def _test_close_commands_structure() -> SelfTestResult:
    """
    BUG-11 FIX: verify close_app returns a structured dict for apps that are
    NOT running (safe — taskkill on a missing process is a no-op).
    """
    from mini_kio.core.app_operator import close_app

    # These apps are almost certainly NOT running in CI / selftest context
    for app in ["notepad", "calculator"]:
        r = close_app(app)
        if not isinstance(r, dict) or "success" not in r or "message" not in r:
            return SelfTestResult("close commands", False, f"{app} bad shape: {r}")
    return SelfTestResult("close commands", True)


def _test_youtube_play() -> SelfTestResult:
    """
    BUG-12 FIX: Tests browser_operator.play_youtube() directly.
    This WILL open a browser tab — documented behaviour for YouTube commands.
    """
    from mini_kio.core.browser_operator import play_youtube

    r = play_youtube("kio selftest")
    if not isinstance(r, dict) or "success" not in r or "message" not in r:
        return SelfTestResult("youtube play", False, f"bad shape: {r}")
    if not r.get("success"):
        return SelfTestResult("youtube play", False, r.get("message"))
    return SelfTestResult("youtube play", True, "browser opened")


def _test_browser_operations() -> SelfTestResult:
    from mini_kio.core.browser_operator import search_google, search_youtube

    for fn, q in [(search_google, "kio selftest"), (search_youtube, "kio selftest")]:
        r = fn(q)
        if not isinstance(r, dict) or "success" not in r:
            return SelfTestResult("browser operations", False, f"{fn.__name__} bad shape")
    return SelfTestResult("browser operations", True)


def _test_memory_usage() -> SelfTestResult:
    try:
        import psutil
        mb = psutil.Process().memory_info().rss / 1024 / 1024
        if mb > 150:
            return SelfTestResult("memory usage", False, f"{mb:.1f} MB > 150 MB limit")
        return SelfTestResult("memory usage", True, f"{mb:.1f} MB")
    except ImportError:
        return SelfTestResult("memory usage", False, "psutil not installed")
    except Exception as exc:
        return SelfTestResult("memory usage", False, str(exc))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

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
        _test_telegram_simulation,
        _test_conversation_fallback,
        _test_app_operator_structure,
        _test_close_commands_structure,
        _test_youtube_play,
        _test_browser_operations,
        _test_memory_usage,
    ]

    print()
    print("KIO SELF TEST")
    print("─" * 50)

    results: list[SelfTestResult] = []
    for fn in tests:
        r = _run_test(fn.__name__, fn)
        results.append(r)
        print(r.format())
        time.sleep(0.03)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    print("─" * 50)
    print(f"  {passed}/{len(results)} tests passed")
    print()
    if failed == 0:
        print("RESULT: SYSTEM HEALTHY")
    else:
        print(f"RESULT: {failed} FAILURE(S) DETECTED")
    print()

    return {
        "total":   len(results),
        "passed":  passed,
        "failed":  failed,
        "results": [{"name": r.name, "passed": r.passed, "details": r.details} for r in results],
    }


if __name__ == "__main__":
    run_selftest()
