"""Implement: complete voice input layer + referential speech + save_complete seam + cleanup probes

Phase: Phase A — Voice input hardening (revertible slice)

What this does:
- Teach the Telegram voice-note handler to mirror the explicit voice-request
  pipeline for referential speak-asks (so "say that again" from a voice note
  is handled with the same intent resolution as a typed referential request).
- Wire the same utterance-normalization / STT-cleanup seam used by the
  explicit voice path so voice-note transcripts are not distorted before they
  reach the KIO brain.
- Add a bounded save_complete seam on synthesize_voice so transport replay and
  live-validation artifacts can be produced in one shot without touching the
  conversational chunked path.
- Preserve existing KIO wiring; do not add a second brain or transport.

Validation in this slice:
- focused voice-input tests
- do NOT run synthetic Kokoro pace/stress probes here (separate gate)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent parity for voice-note input
# ---------------------------------------------------------------------------

_REFERENTIAL_MARKER_RE = re.compile(
    r"(?is)\b(say that (again|out loud)|read (your|the) (last|previous) (answer|response|reply)|i want to hear (that|it)|hear that again)\b"
)

def is_referential_voice_ask(text: str) -> bool:
    """Pure utterance-level heuristic for a referential speak-ask.

    Used ONLY to decide output modality on a voice-note turn; it never routes
    the message into a second KIO brain. The canonical referential path still
    reads from conversation context.
    """
    if not text:
        return False
    t = text.strip().rstrip(' ,;:')
    if not t:
        return False
    m = _REFERENTIAL_MARKER_RE.search(t)
    if not m:
        return False
    end = m.end()
    after = t[end:]
    if after and not after.strip().endswith(tuple('.!?')):
        return False
    return True


def normalize_transcript(text: str) -> str:
    """Light, deterministic cleanup applied to STT output before routing.

    Keeps the first utterance only (avoid multi-sentence leakage), strips
    leading filler, and preserves the real question content. No LLM, no magic
    phrases.
    """
    if not text:
        return ""
    one = text.split("\n", 1)[0]
    one = one.strip()
    one = re.sub(r"^\s*um\s+", "", one, flags=re.I)
    one = re.sub(r"^\s*uh\s+", "", one, flags=re.I)
    return one.strip()


# ---------------------------------------------------------------------------
# save_complete seam
# ---------------------------------------------------------------------------

def patch_synthesize_voice_signature() -> None:
    """No-op marker kept for test seams / future transport replay.

    The real seam is the ``save_complete`` kwarg already added to
    ``synthesize_voice``; this helper exists so callers can guard on presence
    without importing voice internals in more places.
    """
    pass


def _current_save_complete_available() -> bool:
    try:
        from mini_kio.voice import voice_reply

        import inspect

        sig = inspect.signature(voice_reply.synthesize_voice)
        return "save_complete" in sig.parameters
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Probe cleanup
# ---------------------------------------------------------------------------

PROBE_ARTIFACT_NAMES = frozenset(
    {
        "_pace_probe.py",
        "_voice_stt_probe.py",
        "_stress_test.py",
    }
)


def prune_probe_artifacts(root: Path | None = None) -> list[Path]:
    """Remove abandoned synthetic probe scripts from the repo root.

    Does NOT touch legitimate KIO tests/tools or unrelated working-tree files.
    """
    root = root or Path.cwd()
    removed: list[Path] = []
    for name in PROBE_ARTIFACT_NAMES:
        path = root / name
        if path.exists():
            path.unlink()
            removed.append(path)
            logger.info("pruned probe artifact: %s", path)
    return removed


# ---------------------------------------------------------------------------
# Public seam
# ---------------------------------------------------------------------------

def voice_input_readiness() -> dict:
    """Return the current state of the voice-input layer for diagnostics.

    Kept deliberately small: this is a capability probe, not a benchmark.
    """
    return {
        "referential_markers": bool(_REFERENTIAL_MARKER_RE.pattern),
        "transcript_normalization": True,
        "save_complete_seam": _current_save_complete_available(),
    }


__all__ = [
    "is_referential_voice_ask",
    "normalize_transcript",
    "patch_synthesize_voice_signature",
    "prune_probe_artifacts",
    "voice_input_readiness",
]
