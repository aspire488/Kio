#!/usr/bin/env python3
"""Compact focused validation for the KIO voice-input hardening slice.

Deterministic and audio-free. It checks utterance-level referential marker
behavior, transcript normalization, save_complete seam availability, and
probe-artifact cleanup. It is intentionally conservative about explicit
voice-request forms, which are NOT assertable in the referential path.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from mini_kio.voice.voice_input_harden import (
    is_referential_voice_ask,
    normalize_transcript,
    prune_probe_artifacts,
    voice_input_readiness,
)

REFEREENTIAL_TRUE = [
    "say that again",
    "say that again.",
    "say that again!",
    "say that out loud",
    "say that out loud.",
    "read your last answer",
    "read the previous reply",
    "i want to hear that",
    "hear that again",
    "Say that again",
    "  uh  say that again  ",
]

REFEREENTIAL_FALSE = [
    "say that you agree",
    "say that you agree.",
    "tell me that story",
    "explain that to me out loud",
    "explain that to me out loud.",
    "what is the weather",
]


def main() -> int:
    fails = 0

    print("== referential marker ==")
    for c in REFEREENTIAL_TRUE:
        ok = is_referential_voice_ask(c)
        if not ok:
            fails += 1
            print(f"  FAIL expected True: {c!r}")
        else:
            print(f"  ok True: {c!r}")
    for c in REFEREENTIAL_FALSE:
        ok = is_referential_voice_ask(c)
        if ok:
            fails += 1
            print(f"  FAIL expected False: {c!r}")
        else:
            print(f"  ok False: {c!r}")

    print("== transcript normalization ==")
    for raw, expected in [
        ("um how is the weather", "how is the weather"),
        ("uh tell me more", "tell me more"),
        ("say that again", "say that again"),
        ("  uh  say that again  ", "say that again"),
        ("line one\nline two", "line one"),
        ("", ""),
    ]:
        got = normalize_transcript(raw)
        if got != expected:
            fails += 1
            print(f"  FAIL {raw!r} -> {got!r} (expected {expected!r})")
        else:
            print(f"  ok {raw!r} -> {got!r}")

    print("== save_complete seam ==")
    ready = voice_input_readiness()
    if not ready["save_complete_seam"]:
        fails += 1
        print("  FAIL save_complete seam absent")
    else:
        print("  ok save_complete seam present")

    print("== probe cleanup ==")
    removed = prune_probe_artifacts()
    for p in removed:
        print(f"  pruned {p.name}")
    if not removed:
        print("  none found (acceptable)")

    print("== summary ==")
    print(
        f"voice-input hardening slice: "
        f"{'PASS' if fails == 0 else 'FAIL'} ({fails} failure(s))"
    )
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
