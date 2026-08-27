"""
validate_new_capabilities.py — live runtime validation of the capability-delta
batch through KIO's REAL single routing authority (Pipeline.run). Uses the real
DB and live network. Browser opens are intercepted so no window launches.

Run:  python tests/validate_new_capabilities.py
"""

import logging
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Simulate a no-connector environment (the DEFAULT per config.py) so the
# honest media fallback path is exercised. Also avoids the port bind noise.
os.environ["BROWSER_CONNECTOR_ENABLED"] = "false"

logging.basicConfig(level=logging.ERROR)

# intercept default-browser opens so validation stays headless
_OPENED = []
webbrowser.open = lambda url, *a, **k: _OPENED.append(url) or True

from mini_kio.core.pipeline import Pipeline

P = Pipeline()
CHANNEL, USER = "telegram", 777


def run(label, text):
    res = P.run(text, session_id=f"tg_{USER}", channel=CHANNEL, user_id=USER)
    msg = res.get("message") or ""
    print(f"\n### {label}: {text!r}")
    print(f"    intent/decision: {res.get('intent') or res.get('decision') or res.get('capability')}")
    print(f"    reply: {msg}")
    return res


def main():
    print("=" * 70)
    print("KIO capability-delta runtime validation (real pipeline, live net)")
    print("=" * 70)

    # 1. Project summary (GitHub meta + releases + issues, no key)
    run("PROJECT", "summarize the project psf/requests")

    # 2. Project summary (PyPI)
    run("PROJECT-PYPI", "summarize the project requests")

    # 3. Release watcher: register + list
    run("WATCH-ADD", "watch psf/requests for new releases")
    run("WATCH-LIST", "what am I watching")

    # 4. Research thread: write, recall, continue, list
    r1 = run("RESEARCH", "research the papers of yann lecun 2026")
    run("RESEARCH-BRIEF", "research brief on the papers of yann lecun 2026")
    run("RESEARCH-CONTINUE", "continue research on the papers of yann lecun 2026")
    run("RESEARCH-TOPICS", "what did I research")

    # 5. Media: honest no-connector play (browser open intercepted)
    from mini_kio.media.providers.youtube_provider import YouTubeProvider
    YouTubeProvider._get_conn = lambda self: None  # simulate "no connector"
    run("MEDIA-PLAY", "play the live soundtrack trailer")
    print(f"\n    (browser opened: {_OPENED[-1] if _OPENED else 'none'})")

    # 6. Release watcher: the change-notification loop
    from mini_kio.monitoring import watches as w
    print("\n### WATCH-POLL (real feed, baseline compare)")
    res = w.poll_watches()
    print(f"    poll result: {res}")

    # 7. Cleanup: stop watching
    run("WATCH-STOP", "stop watching psf/requests")
    run("WATCH-LIST-EMPTY", "what am I watching")

    print("\n" + "=" * 70)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())