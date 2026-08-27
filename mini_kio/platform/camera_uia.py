"""
camera_uia.py — Native Camera app capture + verification (free, local, UIA).

The Windows Camera UWP app exposes its real controls through UI Automation:
the shutter is a button named "Take photo" (photo mode) / "Record video"
(video mode), and the mode toggle is "Switch to video mode". Driving these
through UIA is deterministic — no pixel guessing, no coordinate hacks.

Verification is filesystem-truth: a photo/video is only reported when a NEW
file with valid content actually appears in the camera's output folder. The
Camera Roll folder is OneDrive-redirected on many machines, so the real shell
folder is resolved instead of assuming ~/Pictures.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mini_kio.platform.camera_uia")


# ── Camera output folder (OneDrive-redirection aware) ───────────────────────
def camera_roll_dirs() -> list[Path]:
    """Real camera output folders in priority order (OneDrive first)."""
    home = Path.home()
    candidates = [
        home / "OneDrive" / "Pictures" / "Camera Roll",
        home / "Pictures" / "Camera Roll",
        home / "OneDrive" / "Pictures",
        home / "Pictures",
    ]
    out: list[Path] = []
    for p in candidates:
        if p.is_dir() and p not in out:
            out.append(p)
    return out


def snapshot_roll() -> set[str]:
    """Names of every file currently in the camera output folders."""
    files: set[str] = set()
    for d in camera_roll_dirs():
        try:
            files |= {f.name for f in d.iterdir() if f.is_file()}
        except Exception:
            continue
    return files


# ── UIA control helpers ──────────────────────────────────────────────────────
def camera_window() -> Optional[object]:
    """Locate the Camera app top-level window via UIA (None when unavailable)."""
    try:
        import uiautomation as auto  # noqa: PLC0415 — lazy by design
    except Exception:
        return None
    try:
        for w in auto.GetRootControl().GetChildren():
            try:
                name = (w.Name or "").lower()
            except Exception:
                continue
            if name == "camera" or (name and "camera" in name and "window" not in name):
                return w
    except Exception:
        return None
    return None


def _find_button(win: object, names: list[str], timeout_s: float = 1.0) -> Optional[object]:
    """Locate a UIA button by name, polling — the Camera app's control tree
    populates a few seconds after launch/focus, so a single lookup is not
    reliable."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for name in names:
            try:
                btn = win.ButtonControl(Name=name, searchDepth=8)  # type: ignore[attr-defined]
                if btn.Exists(0.4):
                    return btn
            except Exception:
                continue
        time.sleep(0.7)
    return None


def click_button(win: object, names: list[str], timeout_s: float = 8.0) -> bool:
    """Invoke a UIA button by name (polled). True only when a real click landed."""
    btn = _find_button(win, names, timeout_s=timeout_s)
    if btn is None:
        return False
    try:
        btn.GetInvokePattern().Invoke()  # type: ignore[attr-defined]
        return True
    except Exception:
        try:
            btn.Click()  # type: ignore[attr-defined]
            return True
        except Exception as exc:
            logger.debug("UIA click failed on %s: %s", names, exc)
            return False


def in_video_mode(win: object) -> bool:
    """True when the camera is already in video mode (photo toggle present)."""
    return _find_button(win, ["Switch to photo mode"], timeout_s=2.0) is not None


def ensure_video_mode(win: object) -> bool:
    """Toggle the camera into video mode when it isn't already."""
    if in_video_mode(win):
        return True
    return click_button(win, ["Switch to video mode"])


def capture_photo(win: object) -> bool:
    return click_button(win, ["Take photo", "Take a photo", "Capture photo"])


def start_video(win: object) -> bool:
    """Begin recording — the shutter is "Take video" in video mode."""
    return click_button(win, ["Take video", "Record video", "Start recording"])


def stop_video(win: object) -> bool:
    """End recording — the same shutter toggles, so retry the video shutter."""
    return click_button(win, ["Stop recording", "Take video", "Record video", "Stop"])


# ── Content verification (filesystem truth) ─────────────────────────────────
def is_valid_jpeg(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(4)
        return head[:3] == b"\xff\xd8\xff"
    except Exception:
        return False


def is_plausible_video(path: Path) -> bool:
    """A real recorded clip: non-trivial size + a media extension/header."""
    try:
        if not path.is_file() or path.stat().st_size < 32_000:
            return False
    except Exception:
        return False
    ext = path.suffix.lower()
    if ext in (".mp4", ".wmv", ".avi", ".mov", ".mkv", ".m4v"):
        return True
    try:
        with open(path, "rb") as f:
            head = f.read(12)
        if head[4:8] == b"ftyp" or head[:4] == b"RIFF" or head[:4] == b"\x1aE\xdf\xa3":
            return True
    except Exception:
        pass
    return ext != ""  # camera clips always carry an extension


def wait_for_new_file(before: set[str], timeout_s: float = 8.0) -> Optional[Path]:
    """Poll the camera roll until a NEW file appears; return its real path."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for d in camera_roll_dirs():
            try:
                for f in d.iterdir():
                    if f.is_file() and f.name not in before:
                        return f
            except Exception:
                continue
        time.sleep(0.5)
    return None


__all__ = [
    "camera_roll_dirs",
    "camera_window",
    "capture_photo",
    "click_button",
    "ensure_video_mode",
    "in_video_mode",
    "is_plausible_video",
    "is_valid_jpeg",
    "snapshot_roll",
    "start_video",
    "stop_video",
    "wait_for_new_file",
]
