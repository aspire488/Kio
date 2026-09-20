"""Verify project creation and that VS Code *visibly* opens the project.

Two things are checked separately and neither is accepted from KIO's reply
text:

1. the real filesystem layout of the created project, and
2. a real top-level VS Code window whose title contains the project folder
   name — a textual "opened it in VS Code" is not evidence.

Run:  python tools/verify_vscode_project.py
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

PY_SOURCE = '''"""Prime test utility."""


def is_prime(n: int) -> bool:
    """Return True when n is a prime number."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True
'''

JS_SOURCE = """function isPrime(n) {
  if (n < 2) return false;
  for (let i = 2; i * i <= n; i += 1) if (n % i === 0) return false;
  return true;
}

module.exports = { isPrime };
"""


def windows_containing(needle: str) -> list[dict]:
    """Visible top-level windows whose title contains *needle*."""
    found: list[dict] = []

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        if needle.lower() in title.value.lower():
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            found.append({"pid": pid.value, "title": title.value, "class": cls.value})
        return True

    EnumWindows(PROC(_cb), 0)
    return found


def wait_for_window(needle: str, timeout: float = 45.0) -> list[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        hits = windows_containing(needle)
        if hits:
            return hits
        time.sleep(1.0)
    return []


def check_project(case: dict) -> dict:
    from mini_kio.core.artifact_operator import create_code_project, open_in_editor

    result = create_code_project(
        case["name"], case["source"], readme=case["readme"], language=case["language"],
    )
    entry: dict = {
        "case": case["name"],
        "language": case["language"],
        "create_success": bool(result.get("success")),
        "create_message": result.get("message"),
    }
    if not result.get("success"):
        return entry

    project_dir = Path(result["project_dir"])
    entry["project_dir"] = str(project_dir)
    entry["files"] = sorted(
        str(p.relative_to(project_dir)).replace("\\", "/")
        for p in project_dir.rglob("*") if p.is_file()
    )
    required = case["required"]
    entry["missing_required"] = [r for r in required if r not in entry["files"]]
    entry["dirs_present"] = sorted(
        d.name for d in project_dir.iterdir() if d.is_dir()
    )

    # Visual proof: open the FOLDER and wait for a window titled with it.
    entry["open_in_editor_returned"] = bool(open_in_editor(project_dir, "vs code"))
    hits = wait_for_window(project_dir.name, timeout=45)
    entry["vscode_windows"] = hits
    entry["vscode_window_visible"] = bool(hits)
    entry["pass"] = (
        not entry["missing_required"]
        and entry["vscode_window_visible"]
        and entry["open_in_editor_returned"]
    )
    return entry


CASES = [
    {
        "name": "kio_prime_test",
        "language": "python",
        "source": PY_SOURCE,
        "readme": "# kio_prime_test\n\nPrime number checks with tests.\n",
        "required": ["README.md", ".gitignore", "requirements.txt"],
    },
    {
        "name": "kio_js_prime_test",
        "language": "javascript",
        "source": JS_SOURCE,
        "readme": "# kio_js_prime_test\n\nPrime number checks in JavaScript.\n",
        "required": ["README.md", ".gitignore", "package.json"],
    },
]


def main() -> int:
    results = [check_project(c) for c in CASES]
    ok = all(r.get("pass") for r in results)
    print(json.dumps({
        "passed": sum(1 for r in results if r.get("pass")),
        "total": len(results),
        "result": "PASS" if ok else "FAIL",
        "cases": results,
    }, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
