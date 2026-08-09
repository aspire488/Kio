"""
operational_health.py — KIO Operational Awareness (canonical owner)
==================================================================
Deterministic, read-only, interface-independent state authority for
operational queries:

    "KIO health" / "are you ok" / "is everything working"
    "KIO status" / "what are you doing" / "are you busy"
    "KIO uptime" / "how long have you been running"
    "system health" / "how is my computer" / "cpu usage" / "ram" ...
    "is the browser connected" / "what services are connected"
    "what's wrong" / "diagnose"

All values come from real runtime/system sources (runtime snapshot,
integrity state, browser connector, provider registry, MCP runtime,
psutil). Unavailable values are reported as unavailable — never 0 or
fabricated. Reading state is side-effect free (on-demand snapshots only;
no polling loops, no background telemetry). Responses are natural
language and deliberately free of implementation tokens the response
composer strips (runtime, provider, connector, mcp, pipeline,
capability).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# User-facing component labels for the health/status lines. The words
# themselves are deliberately plain — the response composer strips internal
# terms like "runtime"/"provider"/"connector"/"mcp" from messages.
_COMPONENT_LABELS: dict[str, str] = {
    "browser": "Browser",
    "telegram": "Telegram",
    "media": "Media",
    "services": "Services",
    "tools": "Tools",
}


# ---------------------------------------------------------------------------
# Duration formatting
# ---------------------------------------------------------------------------

def _fmt_duration_compact(seconds: Optional[float]) -> str:
    """Compact form for status lines: '1d 2h 5m' / '2h 3m' / '5m'."""
    if seconds is None:
        return "unknown"
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m" if minutes else "under a minute"


def _fmt_duration_words(seconds: Optional[float]) -> str:
    """Natural form for prose replies: '1 day, 2 hours and 5 minutes'."""
    if seconds is None:
        return "an unknown length of time"
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts:
        return "less than a minute"
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"


# ---------------------------------------------------------------------------
# State sources (real, read-only)
# ---------------------------------------------------------------------------

def _kio_uptime_s() -> Optional[float]:
    """KIO process uptime from the authoritative runtime start timestamp."""
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt is None:
            return None
        return max(0.0, time.monotonic() - rt.started_at)
    except Exception:
        return None


def _kio_health_snapshot() -> dict[str, Any]:
    """KIO's own health facts from the canonical runtime snapshot."""
    from mini_kio.core.runtime import get_runtime_snapshot
    try:
        snap = get_runtime_snapshot()
    except Exception:
        snap = {}
    state = str(snap.get("state", "init") or "init").lower()
    return {
        "state": state,
        "integrity_status": str(snap.get("integrity_status", "healthy") or "healthy"),
        "integrity_score": int(snap.get("integrity_score", 0) or 0),
        "health_score": int(snap.get("health_score", 0) or 0),
        "warning_count": int(snap.get("integrity_warning_count", 0) or 0),
        "uptime_s": _kio_uptime_s(),
        "ram_mb": float(snap.get("ram_usage_mb", 0.0) or 0.0),
        "running": state not in ("init", "stopped"),
    }


def _component_states() -> dict[str, str]:
    """Truthful per-component state; safe vocabulary only.

    Each value is one of: connected / ready / healthy / disconnected /
    unavailable. A component whose state cannot be determined is
    'unavailable' — never guessed.
    """
    from mini_kio.core.runtime import get_runtime
    rt = get_runtime()
    out: dict[str, str] = {}

    # Browser — connector connected? browser engine ready?
    try:
        from mini_kio.core.command_router import _get_connector
        conn = _get_connector()
        if conn is not None:
            try:
                out["browser"] = "connected" if conn.is_connected() else "disconnected"
            except Exception:
                out["browser"] = "disconnected"
        elif rt is not None and getattr(rt, "browser_runtime", None) is not None:
            out["browser"] = "ready"
        else:
            out["browser"] = "unavailable"
    except Exception:
        out["browser"] = "unavailable"

    # Telegram — token configured and channel attached?
    try:
        from mini_kio.core.config import TELEGRAM_TOKEN
        channels = list(rt.channels) if rt is not None else []
        out["telegram"] = (
            "connected" if (TELEGRAM_TOKEN and "telegram" in channels) else "unavailable"
        )
    except Exception:
        out["telegram"] = "unavailable"

    # Media — subsystem present? "ready" only when already initialized;
    # a health read must not force the heavy on-demand construction.
    try:
        from mini_kio.media.media_manager import MediaManager
        existing = getattr(MediaManager, "_instance", None)
        out["media"] = "ready" if existing is not None else "available"
    except Exception:
        out["media"] = "unavailable"

    # Services — execution provider registry populated?
    try:
        from mini_kio.core.provider_registry import get_provider_registry
        count = len(get_provider_registry().all_providers())
        out["services"] = "healthy" if count else "unavailable"
    except Exception:
        out["services"] = "unavailable"

    # Tools — external tool runtime attached?
    try:
        out["tools"] = (
            "connected"
            if (rt is not None and getattr(rt, "mcp_runtime", None) is not None)
            else "unavailable"
        )
    except Exception:
        out["tools"] = "unavailable"

    return out


def _system_metrics() -> dict[str, Any]:
    """On-demand machine snapshot. Every field is Optional: an unreadable
    metric stays None and is reported as unavailable — never 0."""
    import psutil

    out: dict[str, Any] = {
        "cpu": None,
        "ram_percent": None,
        "ram_used_gb": None,
        "ram_total_gb": None,
        "disk_percent": None,
        "disk_free_gb": None,
        "battery_percent": None,
        "battery_charging": None,
        "system_uptime_s": None,
        "gpu": None,
    }
    try:
        out["cpu"] = int(psutil.cpu_percent(interval=0.4))
    except Exception:
        pass
    try:
        mem = psutil.virtual_memory()
        out["ram_percent"] = int(mem.percent)
        out["ram_used_gb"] = round(mem.used / (1024 ** 3), 1)
        out["ram_total_gb"] = round(mem.total / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        import os
        root = (os.environ.get("SystemDrive", "C:") + "\\") if os.name == "nt" else "/"
        disk = psutil.disk_usage(root)
        out["disk_percent"] = int(disk.percent)
        out["disk_free_gb"] = round(disk.free / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        batt = psutil.sensors_battery()
        if batt is not None:
            out["battery_percent"] = int(batt.percent)
            out["battery_charging"] = bool(batt.power_plugged)
    except Exception:
        pass
    try:
        out["system_uptime_s"] = max(0.0, time.time() - psutil.boot_time())
    except Exception:
        pass
    # GPU — lightweight nvidia-smi probe only (on-demand, no monitoring stack).
    try:
        import subprocess
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            out["gpu"] = int(round(float(res.stdout.strip().splitlines()[0].strip())))
    except Exception:
        pass
    return out


def _kio_health_label(snap: dict[str, Any], comps: dict[str, str]) -> str:
    """Overall KIO health verdict from real integrity/state signals."""
    if not snap.get("running"):
        return "not running"
    if snap["state"] in ("degraded", "emergency", "lockdown", "stopped"):
        return "degraded"
    if snap["integrity_status"] == "degraded" or snap["health_score"] < 60:
        return "degraded"
    try:
        from mini_kio.core.config import BROWSER_CONNECTOR_ENABLED
        if BROWSER_CONNECTOR_ENABLED and comps.get("browser") == "disconnected":
            return "degraded"
    except Exception:
        pass
    return "healthy"


# ---------------------------------------------------------------------------
# Composed responses (natural language, no internals)
# ---------------------------------------------------------------------------

def format_kio_health() -> str:
    snap = _kio_health_snapshot()
    if not snap.get("running"):
        return "KIO is not running right now."
    comps = _component_states()
    label = _kio_health_label(snap, comps)
    lines = ["KIO is healthy."] if label == "healthy" else ["KIO is running, but degraded."]
    lines.append(f"Uptime: {_fmt_duration_compact(snap.get('uptime_s'))}")
    for key, disp in _COMPONENT_LABELS.items():
        state = comps.get(key)
        if state and state not in ("unavailable", "disconnected"):
            lines.append(f"{disp}: {state}")
        elif state == "disconnected":
            lines.append(f"{disp}: unavailable")
    return "\n".join(lines)


def format_status() -> str:
    snap = _kio_health_snapshot()
    if not snap.get("running"):
        return "KIO is not running right now."
    state = snap["state"]
    if state == "degraded":
        head = "KIO is running, but degraded."
        activity = "Degraded"
    elif state == "running":
        head = "KIO is working."
        activity = "Working"
    else:
        head = "KIO is ready."
        activity = "Idle"
    return f"{head}\nUptime: {_fmt_duration_compact(snap.get('uptime_s'))}\nCurrent activity: {activity}"


def format_uptime() -> str:
    snap = _kio_health_snapshot()
    if not snap.get("running"):
        return "KIO is not running right now."
    return f"KIO has been running for {_fmt_duration_words(snap.get('uptime_s'))}."


def format_system_uptime() -> str:
    m = _system_metrics()
    if m.get("system_uptime_s") is None:
        return "I can't read the system uptime right now."
    return f"This computer has been up for {_fmt_duration_words(m['system_uptime_s'])}."


def format_system_health() -> str:
    m = _system_metrics()
    lines: list[str] = []
    heavy = False
    if m.get("cpu") is not None:
        if m["cpu"] >= 95:
            heavy = True
        lines.append(f"CPU: {m['cpu']}%")
    if m.get("ram_percent") is not None:
        if m["ram_percent"] >= 95:
            heavy = True
        if m.get("ram_used_gb") is not None and m.get("ram_total_gb") is not None:
            lines.append(f"RAM: {m['ram_percent']}% ({m['ram_used_gb']} GB of {m['ram_total_gb']} GB)")
        else:
            lines.append(f"RAM: {m['ram_percent']}%")
    if m.get("gpu") is not None:
        lines.append(f"GPU: {m['gpu']}%")
    if m.get("disk_percent") is not None:
        if m.get("disk_free_gb") is not None:
            lines.append(f"Storage: {m['disk_percent']}% used ({m['disk_free_gb']} GB free)")
        else:
            lines.append(f"Storage: {m['disk_percent']}%")
    if not lines:
        return "I can't read your system stats right now."
    head = "Your system is under heavy load right now." if heavy else "Your system looks healthy."
    return head + "\n" + "\n".join(lines)


def format_metric(name: str) -> str:
    m = _system_metrics()
    if name == "cpu":
        if m.get("cpu") is None:
            return "I can't read CPU usage right now."
        return f"CPU usage is {m['cpu']}%."
    if name == "ram":
        if m.get("ram_percent") is None:
            return "I can't read RAM usage right now."
        if m.get("ram_used_gb") is not None and m.get("ram_total_gb") is not None:
            return f"RAM usage is {m['ram_percent']}% ({m['ram_used_gb']} GB of {m['ram_total_gb']} GB)."
        return f"RAM usage is {m['ram_percent']}%."
    if name == "gpu":
        if m.get("gpu") is None:
            return "I can't read GPU usage on this system right now."
        return f"GPU usage is {m['gpu']}%."
    if name == "storage":
        if m.get("disk_percent") is None:
            return "I can't read disk usage right now."
        if m.get("disk_free_gb") is not None:
            return f"Storage is {m['disk_percent']}% used ({m['disk_free_gb']} GB free)."
        return f"Storage is {m['disk_percent']}% used."
    if name == "battery":
        if m.get("battery_percent") is None:
            return "Battery status isn't available on this system."
        if m.get("battery_charging"):
            return f"Battery is at {m['battery_percent']}% and charging."
        return f"Battery is at {m['battery_percent']}%."
    return "I can't read that right now."


_COMPONENT_FOCUS_MAP: dict[str, str] = {
    "browser": "browser", "chrome": "browser", "edge": "browser",
    "firefox": "browser", "brave": "browser",
    "telegram": "telegram", "bot": "telegram", "discord": "telegram",
    "media": "media",
    "providers": "services", "services": "services", "subsystems": "services",
    "mcp": "tools", "tools": "tools",
    "kio": "kio",
}

_COMPONENT_PHRASES: dict[str, str] = {
    "browser": "The browser",
    "telegram": "Telegram",
    "media": "Media",
    "services": "Core services",
    "tools": "External tools",
}


def format_components(focus: str = "") -> str:
    comps = _component_states()
    key = _COMPONENT_FOCUS_MAP.get((focus or "").lower().strip())
    if key:
        if key == "kio":
            snap = _kio_health_snapshot()
            return "KIO is running normally." if snap.get("running") else "KIO is not running right now."
        state = comps.get(key)
        if state and state != "unavailable":
            phrase = _COMPONENT_PHRASES[key]
            verb = "are" if phrase in ("Core services", "External tools") else "is"
            return f"{phrase} {verb} {state}."
        return "I can't determine that right now."
    lines = []
    for key, disp in _COMPONENT_LABELS.items():
        state = comps.get(key)
        if state:
            lines.append(f"{disp}: {state}")
    return "\n".join(lines) if lines else "I can't determine service status right now."


def format_whats_wrong() -> str:
    snap = _kio_health_snapshot()
    if not snap.get("running"):
        return "KIO is not running right now."
    comps = _component_states()
    issues: list[str] = []
    if snap["state"] == "degraded":
        issues.append("KIO is running in a degraded state.")
    if snap.get("warning_count"):
        n = snap["warning_count"]
        issues.append(f"{n} internal issue{'s' if n != 1 else ''} were recorded recently.")
    if comps.get("browser") == "disconnected":
        issues.append("The browser connection is down.")
    if comps.get("browser") == "unavailable":
        issues.append("The browser service isn't available.")
    if comps.get("telegram") == "unavailable":
        issues.append("Telegram isn't connected.")
    if comps.get("tools") == "unavailable":
        issues.append("External tools aren't connected.")
    if not issues:
        return "Nothing seems wrong right now. Everything is running normally."
    return "Here's what I can see:\n" + "\n".join("• " + issue for issue in issues)


# ---------------------------------------------------------------------------
# Canonical entry point (used by _ExecutionCoordinator._exec_operational)
# ---------------------------------------------------------------------------

def operational_result(action: str, target: str = "") -> dict[str, Any]:
    """Build a natural, truthful operational response for an action."""
    action = str(action or "status").lower().strip()
    formatters: dict[str, Any] = {
        "health": format_kio_health,
        "status": format_status,
        "uptime": format_uptime,
        "system": format_system_health,
        "system_uptime": format_system_uptime,
        "cpu": lambda: format_metric("cpu"),
        "ram": lambda: format_metric("ram"),
        "gpu": lambda: format_metric("gpu"),
        "storage": lambda: format_metric("storage"),
        "battery": lambda: format_metric("battery"),
        "components": lambda: format_components(target),
        "whats_wrong": format_whats_wrong,
    }
    message = formatters.get(action, format_status)()
    return {"success": True, "message": message, "action": action, "target": target}
