"""Audit every subprocess spawn site in KIO for CREATE_NO_WINDOW coverage.

KIO runs console-less on Windows, so a console-subsystem child spawned without
CREATE_NO_WINDOW opens a visible console window while KIO is running.  This
walk (AST, not grep) lists each spawn site and whether it suppresses the
window, so regressions are visible immediately.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("run", "Popen", "call", "check_call", "check_output")

# Deliberate exceptions, with the reason they are safe to leave unflagged.
#  - GUI/visible launchers: a user-requested visible action MUST stay visible,
#    so suppressing the window would be the bug.
#  - Non-Windows tools: never reached on win32, so the flag is meaningless.
EXEMPT_ARGV0 = {
    "explorer.exe": "GUI launcher — user-requested visible action",
    "explorer": "GUI launcher — user-requested visible action",
    "xdg-open": "Linux/macOS opener — not reached on Windows",
    "open": "macOS opener — not reached on Windows",
    "osascript": "macOS tool — not reached on Windows",
    "notify-send": "Linux tool — not reached on Windows",
    "pkill": "Unix tool — not reached on Windows",
}

# Sites whose argv is computed at runtime; reviewed by hand and intentionally
# allowed (non-Windows fallback branches of user-visible app launching).
EXEMPT_SITES = {
    ("mini_kio/core/app_operator.py", 3088): "non-Windows branch of visible app launch",
}


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def audit(path: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    except SyntaxError as exc:
        return [{"file": str(path), "line": 0, "kind": "SYNTAX_ERROR", "covered": False,
                 "detail": str(exc)}]

    findings: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        if not any(name.endswith(f"subprocess.{t}") or name == f"subprocess.{t}"
                   for t in TARGETS):
            continue
        keywords = {kw.arg for kw in node.keywords if kw.arg}
        has_no_window = "creationflags" in keywords or "startupinfo" in keywords
        # **no_window() / **kwargs splat — treat as covered, reviewed by hand.
        splat = any(kw.arg is None for kw in node.keywords)
        argv0 = ""
        if node.args and isinstance(node.args[0], ast.List) and node.args[0].elts:
            first = node.args[0].elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                argv0 = first.value
        findings.append({
            "file": str(path.relative_to(ROOT)).replace("\\", "/"),
            "line": node.lineno,
            "kind": name,
            "argv0": argv0,
            "covered": has_no_window or splat,
            "detail": "creationflags" if has_no_window else ("**kwargs" if splat else "NO FLAGS"),
        })
    return findings


def main() -> int:
    files: list[Path] = []
    for base in ("mini_kio",):
        files.extend(sorted((ROOT / base).rglob("*.py")))
    all_findings: list[dict] = []
    for f in files:
        if "_probe" in f.name:
            continue
        all_findings.extend(audit(f))

    gaps = []
    exempt = 0
    for f in all_findings:
        if f["covered"]:
            continue
        if f.get("argv0") in EXEMPT_ARGV0:
            exempt += 1
            continue
        if (f["file"], f["line"]) in EXEMPT_SITES:
            exempt += 1
            continue
        gaps.append(f)

    print(f"spawn sites scanned: {len(all_findings)}")
    print(f"exempt (documented GUI/non-Windows launchers): {exempt}")
    print(f"uncovered (no CREATE_NO_WINDOW): {len(gaps)}")
    for g in gaps:
        print(f"  {g['file']}:{g['line']}  {g['kind']}  "
              f"argv0={g.get('argv0', '')!r}  {g['detail']}")
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
