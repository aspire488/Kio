"""
desktop_state.py — Canonical Desktop Snapshot Owner
====================================================
System-level, read-only desktop observation for the deterministic state
family ("What's open?" / "What am I using?" / "What's active?" / ...).

The model is:

    DesktopState
        ├── native windows (visible top-level windows from the Windows
        │     desktop API, enriched with process/app identity)
        └── browser tabs (from the browser connector / browser runtime)

Composition is hierarchical: Application → Window → Browser tab. The
observation mechanism is fully generic (EnumWindows) — any arbitrary GUI
application is observed through the same path; nothing here is a
terminal/explorer/browser special case. A small display-name map is used
ONLY for brand-cased presentation of well-known binaries; detection never
consults it.

Invariants:
  - reading state is side-effect free (no activation, no launching, no LLM)
  - background processes without a visible window never appear
  - raw URLs / PIDs / internal ids / "::" chains never reach the response
  - unavailable state is reported truthfully, never fabricated
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Browser host binaries — used ONLY to classify a native window as a browser
# host so its tabs can be grouped under it (and so a browser window is never
# mistaken for an ordinary app). Detection stays generic.
_BROWSER_PROC_NAMES = frozenset({
    "chrome", "msedge", "firefox", "brave", "comet", "opera",
})

# System wrapper/overlay binaries that never represent a user application
# window (console host, shell experience host, input overlay).
_SKIP_WRAPPER_EXES = frozenset({
    "conhost.exe", "shellexperiencehost.exe", "textinputhost.exe",
})

# UWP broker: owns the visible window on behalf of the packaged app, so the
# window title carries the real app identity. Compared against the stripped
# process base (no .exe), like _BROWSER_PROC_NAMES.
_UWP_BROKER_EXES = frozenset({"applicationframehost"})

# Display-only brand casing for well-known binaries. Detection never reads
# this map — an unknown binary is prettified generically and still appears.
_NATIVE_DISPLAY_NAMES: dict[str, str] = {
    "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox",
    "brave": "Brave", "opera": "Opera", "comet": "Comet",
    "explorer": "File Explorer", "code": "VS Code", "devenv": "Visual Studio",
    "windowsterminal": "Windows Terminal", "wt": "Windows Terminal",
    "powershell": "PowerShell", "pwsh": "PowerShell", "cmd": "Command Prompt",
    "notepad": "Notepad", "mspaint": "Paint", "calculator": "Calculator",
    "spotify": "Spotify", "telegram": "Telegram", "discord": "Discord",
    "whatsapp": "WhatsApp", "slack": "Slack", "notion": "Notion",
    "obsidian": "Obsidian", "vlc": "VLC", "capcut": "CapCut",
    "opencode": "OpenCode", "codex": "Codex", "wezterm": "WezTerm",
    "windowsapps": "App", "snippingtool": "Snipping Tool",
    "systemsettings": "Settings",
}

_BROWSER_TITLE_SUFFIXES = (
    " - Google Chrome", " - Chrome", " - Microsoft Edge", " - Mozilla Firefox",
    " - Brave", " - Opera", " - Comet",
)


# ---------------------------------------------------------------------------
# Sanitization / naming helpers (moved from the pipeline coordinator —
# these are the canonical, pure presentation helpers)
# ---------------------------------------------------------------------------

def _clean_title(title: str) -> str:
    """Clean a window/tab title for display; '' when nothing meaningful."""
    cleaned = re.sub(r"https?://\S+", "", title or "").strip()
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return ""
    return cleaned[:80]


def _strip_browser_title_suffix(title: str) -> str:
    """Strip the browser-brand suffix Chrome/Edge/etc append to window titles."""
    for suffix in _BROWSER_TITLE_SUFFIXES:
        if title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title


def native_app_display_name(exe_base: str) -> str:
    """Brand-cased display name for a process image base (no .exe)."""
    base = (exe_base or "").strip().lower()
    if base in _NATIVE_DISPLAY_NAMES:
        return _NATIVE_DISPLAY_NAMES[base]
    # Generic prettify: underscores -> spaces, title-case each word.
    words = [w.capitalize() for w in re.split(r"[_\s]+", base) if w]
    return " ".join(words) or "Application"


def tab_detail(tab) -> dict:
    """Resolve one browser tab to structured identity + detail (user-safe).

    identity: canonical web-app brand (ChatGPT / Telegram / YouTube) when
    the tab URL maps to a registered web app; else "".
    detail: sanitized tab title (URLs stripped); "" when none or when it
    merely repeats the identity.
    is_owned / active: KIO provenance + connector active flag.
    """
    from mini_kio.core.target_ref import webapp_name_from_url, display_target_name

    url = (getattr(tab, "url", "") or "").strip()
    title = (getattr(tab, "title", "") or "").strip()
    identity = ""
    if url:
        ident = webapp_name_from_url(url)
        if ident:
            identity = display_target_name(ident)
    detail = ""
    if title and not re.match(r"^https?://", title, re.IGNORECASE):
        cleaned = _clean_title(title)
        if cleaned:
            detail = cleaned
    if identity and detail and detail.lower().strip() == identity.lower().strip():
        detail = ""
    return {
        "identity": identity,
        "detail": detail,
        "is_owned": bool(getattr(tab, "is_owned", False)),
        "active": bool(getattr(tab, "active", False)),
    }


# ---------------------------------------------------------------------------
# Native window observation (generic EnumWindows + psutil enrichment)
# ---------------------------------------------------------------------------

def _exe_name_for_pid(pid: int) -> str:
    """Process image name (lowercased) for a window PID; '' when unavailable."""
    try:
        import psutil
        try:
            return str(psutil.Process(int(pid)).name() or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            return ""
    except Exception:
        return ""


def _kio_tracked_bases() -> set[str]:
    """Process image bases KIO currently tracks (for provenance only)."""
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt is None:
            return set()
        try:
            rt.prune_tracked_processes()
        except Exception:
            pass
        bases = set()
        for entry in rt.tracked_processes:
            name = str(entry.get("name", "") or "").lower()
            if name.endswith(".exe"):
                name = name[:-4]
            if name:
                bases.add(name)
        return bases
    except Exception:
        return set()


def observe_native_windows() -> tuple[list[dict], bool]:
    """Return (windows, ok).

    windows: [{app, base, title, pid, is_foreground, is_browser_host,
               is_kio_owned}] for every visible top-level app window.
    ok: True when enumeration succeeded (even if the list is empty).
    Background processes with no visible window never appear here.
    """
    try:
        from mini_kio.platform.window_activation import list_visible_windows
        raw = list_visible_windows()
    except Exception as exc:
        logger.warning("[DESKTOP] native window enumeration unavailable: %s", exc)
        return [], False
    if not raw:
        return [], True

    tracked = _kio_tracked_bases()
    out: list[dict] = []
    for w in raw:
        pid = int(w.get("pid", 0) or 0)
        # Resolve the process image name for this window (generic; the
        # platform layer stays pure Win32).
        exe = _exe_name_for_pid(pid)
        if exe in _SKIP_WRAPPER_EXES:
            continue
        base = exe[:-4] if exe.endswith(".exe") else exe
        raw_title = _clean_title(w.get("title", "") or "")
        if base in _BROWSER_PROC_NAMES:
            # Browser window titles carry the active tab title + brand suffix.
            raw_title = _clean_title(_strip_browser_title_suffix(raw_title))
        if base in _UWP_BROKER_EXES:
            # Broker window title carries the real app identity.
            app = raw_title or "Application"
            base = ""
            title = "" if raw_title and raw_title.lower() == app.lower() else raw_title
        else:
            app = native_app_display_name(base)
            title = "" if raw_title and raw_title.lower() == app.lower() else raw_title
        out.append({
            "app": app,
            "base": base,
            "title": title,
            "pid": pid,
            "is_foreground": bool(w.get("is_foreground", False)),
            "is_browser_host": base in _BROWSER_PROC_NAMES,
            "is_kio_owned": bool(base and base in tracked),
        })
    # UWP broker windows may duplicate the packaged app's own window; collapse
    # identical app+title entries so the broker never doubles the listing.
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for w in out:
        key = (w["app"], w["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(w)
    return deduped, True


# ---------------------------------------------------------------------------
# Browser host resolution for tab grouping
# ---------------------------------------------------------------------------

def _browser_host_name(conn_connected: bool, native: list[dict]) -> str:
    """Best-known name of the browser the connector tabs belong to."""
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt is not None:
            try:
                rt.prune_tracked_processes()
            except Exception:
                pass
            for entry in rt.tracked_processes:
                name = str(entry.get("name", "") or "").lower()
                if name.endswith(".exe"):
                    name = name[:-4]
                if name in _BROWSER_PROC_NAMES:
                    return native_app_display_name(name)
    except Exception:
        pass
    for w in native:
        if w.get("is_browser_host"):
            return w["app"]
    return "Chrome" if conn_connected else ""


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def compose_desktop_state(
    conn,
    *,
    native_windows: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """One canonical live desktop snapshot, composed deterministically.

    conn: the browser connector (or None); tabs come from it when connected,
    falling back to the browser-runtime listing.
    native_windows: injectable list (tests) — defaults to live observation.

    Returns {"success": True, "message": str, "action": "list_tabs",
             "target": "<safe referent>"}. Never an LLM answer; reading is
    side-effect free.
    """
    if native_windows is None:
        native, native_ok = observe_native_windows()
    else:
        native, native_ok = list(native_windows), True

    # --- Tabs (connector is the single source of truth; runtime fallback) ---
    tabs: list[dict] = []
    tabs_ok = False
    conn_connected = False
    if conn is not None:
        try:
            conn_connected = bool(conn.is_connected())
        except Exception:
            conn_connected = False
        if conn_connected:
            from mini_kio.core.async_utils import safe_run_async
            try:
                result = safe_run_async(conn.list_tabs())
                if getattr(result, "success", False):
                    tabs_ok = True
                    tabs = [tab_detail(t) for t in (getattr(result, "tabs", None) or [])]
            except Exception as exc:
                logger.warning("[DESKTOP] list_tabs failed: %s", exc)
    else:
        from mini_kio.core.command_router import _check_br_available, _br_list_tabs
        if _check_br_available():
            try:
                br_result = _br_list_tabs()
                if br_result.get("success"):
                    tabs_ok = True
                    body = br_result.get("message", "").replace("Open tabs:\n", "")
                    for line in body.splitlines():
                        owned = bool(re.search(r"\[Opened by KIO\]", line))
                        cleaned = re.sub(r"^\d+\.\s*", "", line.strip())
                        cleaned = re.sub(r"\s*\[Opened by KIO\]\s*$", "", cleaned)
                        cleaned = _clean_title(cleaned)
                        if cleaned:
                            tabs.append({
                                "identity": "", "detail": cleaned,
                                "is_owned": owned, "active": False,
                            })
            except Exception as exc:
                logger.warning("[DESKTOP] browser-runtime tab listing failed: %s", exc)

    browser_host = _browser_host_name(conn_connected, native)

    # --- Hierarchical composition: browser tabs grouped under the host ---
    # A tab may claim "(active)" only when no non-browser window is actually
    # foreground: the connector's active flag describes the last active tab in
    # the browser window, not the OS foreground — a genuinely foreground
    # native window proves the browser is not on top, so no tab is active.
    non_browser_foreground = any(
        w.get("is_foreground") and not w.get("is_browser_host") for w in native
    )
    tabs_active_allowed = not non_browser_foreground
    lines: list[tuple[str, str, bool]] = []  # (kind, text, is_active)
    active_tab_count = sum(1 for t in tabs if t.get("active"))
    for t in tabs:
        parts = []
        if t.get("identity"):
            parts.append(t["identity"])
        if t.get("detail"):
            parts.append(t["detail"])
        label = " — ".join(parts) if parts else "Untitled tab"
        line = f"{browser_host} — {label}" if browser_host else label
        if t.get("is_owned"):
            line += " (opened by KIO)"
        is_active = bool(t.get("active")) and active_tab_count == 1 and tabs_active_allowed
        lines.append(("tab", line, is_active))

    # Native windows: browser hosts collapse into tab lines when tabs are
    # readable; every other visible window is listed with its title. Titles
    # are re-sanitized at composition time (defense in depth — injected or
    # third-party window data must never leak URLs into the response).
    show_browser_windows = not tabs_ok
    for w in native:
        if w.get("is_browser_host") and not show_browser_windows:
            continue
        line = _clean_title(w.get("app") or "Application") or "Application"
        title = _clean_title(w.get("title") or "")
        if w.get("is_browser_host"):
            title = _clean_title(_strip_browser_title_suffix(title))
        if title:
            line += f" — {title}"
        if w.get("is_kio_owned"):
            line += " (opened by KIO)"
        lines.append(("native", line, bool(w.get("is_foreground"))))

    # --- Deduplicate genuine duplicates (tabs vs windows suffix) ---
    counts: dict[str, int] = {}
    order: list[str] = []
    first: dict[str, tuple[str, str]] = {}
    active_by_key: dict[str, bool] = {}
    for kind, line, is_active in lines:
        key = line.strip().lower()
        if not key:
            continue
        if key not in counts:
            counts[key] = 0
            order.append(key)
            first[key] = (kind, line)
            active_by_key[key] = False
        counts[key] += 1
        active_by_key[key] = active_by_key[key] or is_active

    items: list[str] = []
    for key in order:
        kind, text = first[key]
        suffix = ""
        if counts[key] > 1:
            noun = "tabs" if kind == "tab" else "windows"
            suffix = f" ({counts[key]} {noun})"
        if active_by_key[key]:
            suffix += " (active)"
        items.append(f"{text}{suffix}")

    browser_visible = conn_connected or any(w.get("is_browser_host") for w in native) or bool(browser_host)
    conn_configured = conn is not None

    # --- Truthful short forms ---
    if tabs_ok and items:
        message = "Open right now:\n" + "\n".join("• " + n for n in items)
    elif tabs_ok and not items:
        if browser_visible:
            message = f"{browser_host or 'Chrome'} is open."
        elif native_ok and not native:
            message = "Nothing is open right now."
        else:
            message = "I can't read your current desktop state right now."
    elif items:
        # Tabs unreadable but native state visible — report what we know.
        message = "Open right now:\n" + "\n".join("• " + n for n in items)
    elif browser_visible:
        message = f"{browser_host or 'Chrome'} is open, but I couldn't read its tabs."
    elif conn_configured:
        message = "I can't read your current desktop state right now."
    elif native_ok and not native:
        message = "Nothing is open right now."
    else:
        message = "I can't read your current desktop state right now."

    # Safe referent: only a NON-browser foreground native window becomes a
    # contextual target (browser hosts stay tab-scoped — a process-level
    # referent for Chrome must never be created from a state query).
    referent = ""
    for w in native:
        if w.get("is_foreground") and not w.get("is_browser_host"):
            referent = w.get("base") or ""
            break

    return {"success": True, "message": message, "action": "list_tabs", "target": referent}
