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
import os
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


# ---------------------------------------------------------------------------
# Per-volume storage (the canonical storage view — never one global number)
# ---------------------------------------------------------------------------

# Conservative, generic pressure thresholds (documented, not arbitrary): a
# drive with <20% free or <20 GB free is "getting full"; <10% free or <5 GB
# free is "critically low". These are stated in explanations.
_VOLUME_LOW_FREE_PCT = 20
_VOLUME_CRITICAL_FREE_PCT = 10
_VOLUME_LOW_FREE_GB = 20.0
_VOLUME_CRITICAL_FREE_GB = 5.0

# Bounded storage attribution: depth-limited scan with a hard time budget,
# so a full-disk diagnosis never scans the whole drive or blocks the bot.
_STORAGE_SCAN_BUDGET_S = 1.5
_STORAGE_SCAN_DEPTH = 2
_STORAGE_CONTRIBUTOR_MIN_GB = 5.0
_STORAGE_CONTRIBUTOR_LIMIT = 3


def _volume_label(mountpoint: str) -> str:
    """Friendly volume label: 'C:\\' -> 'C:', '/' -> 'system'."""
    mp = (mountpoint or "").strip()
    if not mp:
        return "disk"
    if len(mp) >= 2 and mp[1] == ":":
        return mp[:2].upper()
    if mp == "/":
        return "system"
    return mp.rstrip("/\\") or "disk"


def _storage_volumes() -> list[dict[str, Any]]:
    """Per-volume usage snapshot (read-only). Returns
    [{mountpoint, label, fstype, total_gb, used_gb, free_gb, percent,
    pressure}] with pressure in ('critical', 'low', 'ok'). Unreadable
    volumes are skipped — storage is never collapsed into one global
    number."""
    import psutil
    volumes: list[dict[str, Any]] = []
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception:
        return volumes
    for part in partitions:
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except Exception:
            continue
        percent = int(usage.percent)
        free_gb = round(usage.free / (1024 ** 3), 1)
        free_pct = 100 - percent
        if free_pct < _VOLUME_CRITICAL_FREE_PCT or free_gb <= _VOLUME_CRITICAL_FREE_GB:
            pressure = "critical"
        elif free_pct < _VOLUME_LOW_FREE_PCT or free_gb <= _VOLUME_LOW_FREE_GB:
            pressure = "low"
        else:
            pressure = "ok"
        volumes.append({
            "mountpoint": part.mountpoint,
            "label": _volume_label(part.mountpoint),
            "fstype": part.fstype or "",
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "used_gb": round(usage.used / (1024 ** 3), 1),
            "free_gb": free_gb,
            "percent": percent,
            "pressure": pressure,
        })
    return volumes


def _storage_contributors(volume: dict[str, Any]) -> list[dict[str, Any]]:
    """Bounded top-level contributors on one volume.

    Scans only the volume root to a limited depth with a hard time budget
    — never the whole disk. Returns [{name, size_gb}] for the largest
    entries; [] when the scan fails, times out, or finds nothing large —
    the caller then reports the volume pressure honestly instead of
    guessing.
    """
    root = (volume.get("mountpoint") or "").strip()
    if not root:
        return []
    deadline = time.monotonic() + _STORAGE_SCAN_BUDGET_S
    top: dict[str, float] = {}

    def _sum_under(path: str, depth: int, key: str) -> None:
        if time.monotonic() > deadline:
            return
        try:
            entries = list(os.scandir(path))
        except Exception:
            return
        for entry in entries:
            if time.monotonic() > deadline:
                return
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth < _STORAGE_SCAN_DEPTH:
                        _sum_under(entry.path, depth + 1, key)
                else:
                    top[key] = top.get(key, 0.0) + entry.stat(follow_symlinks=False).st_size
            except Exception:
                continue

    try:
        entries = list(os.scandir(root))
    except Exception:
        return []
    for entry in entries:
        if time.monotonic() > deadline:
            break
        try:
            if entry.is_dir(follow_symlinks=False):
                top[entry.name] = 0.0
                _sum_under(entry.path, 1, entry.name)
            else:
                top[entry.name] = top.get(entry.name, 0.0) + entry.stat(follow_symlinks=False).st_size
        except Exception:
            continue
    out = [
        {"name": name, "size_gb": round(bytes_ / (1024 ** 3), 1)}
        for name, bytes_ in top.items()
        if bytes_ / (1024 ** 3) >= _STORAGE_CONTRIBUTOR_MIN_GB
    ]
    out.sort(key=lambda c: c["size_gb"], reverse=True)
    return out[:_STORAGE_CONTRIBUTOR_LIMIT]


# ---------------------------------------------------------------------------
# Resource attribution (application-aware, never merged across binaries)
# ---------------------------------------------------------------------------

def _top_consumers(kind: str, limit: int = 5) -> list[dict[str, Any]]:
    """Top application-grouped RAM/CPU consumers.

    kind='ram' reads instantaneous RSS; kind='cpu' takes a two-sample
    reading (~0.6s) so a single transient spike is not over-interpreted.
    Processes are grouped by identical executable image only (never merged
    across different binaries); the friendly application name comes from
    the canonical desktop identity helper. Raw process identity is kept
    internally for correctness and never exposed in responses.
    Returns [{name, base, value, unit, processes}] sorted descending.
    """
    import psutil
    from mini_kio.core.desktop_state import native_app_display_name

    procs: list[Any] = []
    for proc in psutil.process_iter():
        try:
            procs.append(proc)
        except Exception:
            continue
    if kind == "cpu":
        for p in procs:
            try:
                p.cpu_percent(None)  # prime the sample window
            except Exception:
                pass
        time.sleep(0.6)
    groups: dict[str, dict[str, Any]] = {}
    for p in procs:
        try:
            name = str(p.name() or "").lower()
            base = name[:-4] if name.endswith(".exe") else name
            if kind == "ram":
                value = p.memory_info().rss / (1024 ** 3)
            else:
                value = p.cpu_percent(None)
            if value <= 0:
                continue
            g = groups.setdefault(base, {
                "name": native_app_display_name(base), "base": base,
                "value": 0.0, "processes": 0,
            })
            g["value"] += value
            g["processes"] += 1
        except Exception:
            continue  # process disappeared mid-sample — never fabricate
    unit = "GB" if kind == "ram" else "%"
    items = [
        {"name": g["name"], "base": g["base"], "value": round(g["value"], 1),
         "unit": unit, "processes": g["processes"]}
        for g in groups.values()
    ]
    items.sort(key=lambda c: c["value"], reverse=True)
    return items[:limit]


# ---------------------------------------------------------------------------
# Structured diagnostic conditions (the proactive foundation)
# ---------------------------------------------------------------------------

def _fmt_gb(value: float) -> str:
    """'6.1' -> '6.1', '6.0' -> '6' — friendly size formatting."""
    s = f"{value:.1f}".rstrip("0").rstrip(".")
    return s


def _join_names(names: list[str]) -> str:
    """['A', 'B'] -> 'A and B'; ['A', 'B', 'C'] -> 'A, B and C'."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def _ram_explanation(pct: int, severity: str) -> str:
    # Truthfulness in the structured model: "running high" is only claimed
    # for genuinely elevated bands (medium+). A healthy/info condition must
    # never record a false "running high" statement — future proactive
    # consumers iterate these records.
    if severity in ("high", "medium"):
        base = f"RAM is running high at {pct}%"
        top = [c for c in _top_consumers("ram", limit=3) if c["value"] >= 0.5]
        if top:
            names = [f"{c['name']} (about {_fmt_gb(c['value'])} GB)" for c in top]
            if len(names) == 1:
                return f"{base}, with {names[0]} the biggest consumer."
            return f"{base}. The biggest consumers right now are {_join_names(names)}."
        return f"{base}."
    return f"RAM usage is at {pct}%."


def _cpu_explanation(cpu: int, severity: str) -> str:
    if severity in ("high", "medium"):
        top = [c for c in _top_consumers("cpu", limit=3) if c["value"] >= 1.0]
        if top:
            names = [f"{c['name']} (about {_fmt_gb(c['value'])}%)" for c in top]
            verb = "is" if len(names) == 1 else "are"
            noun = "thing" if len(names) == 1 else "things"
            return f"CPU usage is {cpu}%. The busiest {noun} right now {verb} {_join_names(names)}."
    return f"CPU usage is {cpu}%."


def _storage_explanation(vol: dict[str, Any], contributors: list[dict[str, Any]]) -> str:
    label, pct, free = vol["label"], vol["percent"], vol["free_gb"]
    if vol["pressure"] == "critical":
        msg = f"Your {label} drive is critically low on space — {pct}% used, with about {free} GB free."
    elif vol["pressure"] == "low":
        msg = f"Your {label} drive is getting fairly full — {pct}% used, with about {free} GB free."
    else:
        return f"Your {label} drive has plenty of space ({pct}% used)."
    if contributors:
        names = [f"{c['name']} (about {_fmt_gb(c['size_gb'])} GB)" for c in contributors]
        msg += f" Most of the used space is coming from {_join_names(names)}."
    return msg


def _system_conditions() -> list[dict[str, Any]]:
    """Structured diagnostic conditions from real sources.

    Every condition carries: id, severity (critical/high/medium/low/info),
    metric, current_value, threshold, contributor(s), evidence,
    explanation and observed_at. This is the proactive-condition
    foundation: future KIO behavior ("warn me when C: is low") can consume
    these records directly. Reading is side-effect free.
    """
    m = _system_metrics()
    conditions: list[dict[str, Any]] = []
    observed_at = time.time()

    ram_pct = m.get("ram_percent")
    if ram_pct is not None:
        # threshold records the band's own trigger so a future consumer can
        # tell exactly what tripped the severity level.
        if ram_pct >= 95:
            sev, thr = "high", 95
        elif ram_pct >= 90:
            sev, thr = "medium", 90
        elif ram_pct >= 80:
            sev, thr = "low", 80
        else:
            sev, thr = "info", 80
        cond = {
            "id": "ram", "severity": sev, "metric": "ram",
            "current_value": ram_pct, "threshold": thr,
            "evidence": "virtual_memory", "observed_at": observed_at,
        }
        cond["explanation"] = _ram_explanation(ram_pct, sev)
        conditions.append(cond)

    cpu = m.get("cpu")
    if cpu is not None:
        if cpu >= 90:
            sev, thr = "high", 90
        elif cpu >= 75:
            sev, thr = "medium", 75
        elif cpu >= 60:
            sev, thr = "low", 60
        else:
            sev, thr = "info", 60
        cond = {
            "id": "cpu", "severity": sev, "metric": "cpu",
            "current_value": cpu, "threshold": thr,
            "evidence": "cpu_percent", "observed_at": observed_at,
        }
        cond["explanation"] = _cpu_explanation(cpu, sev)
        conditions.append(cond)

    for v in _storage_volumes():
        sev = {"critical": "high", "low": "medium", "ok": "info"}[v["pressure"]]
        contributors = _storage_contributors(v) if v["pressure"] != "ok" else []
        cond = {
            "id": f"storage_{v['label'].lower().rstrip(':')}", "severity": sev,
            "metric": "storage", "current_value": v["percent"], "threshold": 80,
            "volume": v["label"], "free_gb": v["free_gb"],
            "contributors": contributors,
            "evidence": "disk_usage per volume", "observed_at": observed_at,
        }
        cond["explanation"] = _storage_explanation(v, contributors)
        conditions.append(cond)

    batt = m.get("battery_percent")
    if batt is not None and batt <= 20 and not m.get("battery_charging"):
        conditions.append({
            "id": "battery", "severity": "low", "metric": "battery",
            "current_value": batt, "threshold": 20,
            "explanation": f"Battery is down to {batt}% and not charging.",
            "evidence": "sensors_battery", "observed_at": observed_at,
        })
    return conditions


def _notable_conditions() -> list[dict[str, Any]]:
    """Conditions worth reporting (severity medium+; excludes info)."""
    return [
        c for c in _system_conditions()
        if c["severity"] in ("critical", "high", "medium")
    ]


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


def _system_boot_ts() -> Optional[float]:
    """Authoritative OS boot/session timestamp (unix)."""
    try:
        import psutil
        return float(psutil.boot_time())
    except Exception:
        return None


def _fast_startup_enabled() -> Optional[bool]:
    """Windows Fast Startup / Hiberboot state (None = cannot determine)."""
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Power",
        ) as key:
            val, _ = winreg.QueryValueEx(key, "HiberbootEnabled")
            return bool(int(val))
    except Exception:
        return None


def format_system_uptime() -> str:
    """OS session uptime reported truthfully: session duration + boot timestamp,
    with the Fast Startup/hibernation caveat where the OS enables it. The user's
    own recollection of a shutdown is never contradicted from uptime alone."""
    m = _system_metrics()
    boot_ts = _system_boot_ts()
    if m.get("system_uptime_s") is None or boot_ts is None:
        return "I can't read the system uptime right now."
    try:
        import datetime
        boot_dt = datetime.datetime.fromtimestamp(boot_ts).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        boot_dt = ""
    base = f"Windows reports the current system session has been running for {_fmt_duration_words(m['system_uptime_s'])}."
    if boot_dt:
        base += f" It started on {boot_dt}."
    fs = _fast_startup_enabled()
    if fs:
        base += (" Fast Startup is enabled, so a shutdown can resume the same session — "
                 "I can't confirm from uptime alone when the machine was last physically shut down.")
    return base


def format_lock_state() -> str:
    """Truthful workstation lock state (real OS detection, never guessed)."""
    try:
        from mini_kio.core.system_operator import is_workstation_locked
        locked = is_workstation_locked()
    except Exception:
        locked = None
    if locked is None:
        return "I can't confirm the lock state right now."
    return "Your computer is locked." if locked else "Your computer isn't locked."


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
    volumes = _storage_volumes()
    if volumes:
        for v in volumes:
            lines.append(f"{v['label']} {v['percent']}% used ({v['free_gb']} GB free)")
    elif m.get("disk_percent") is not None:
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
            base = f"RAM usage is {m['ram_percent']}% ({m['ram_used_gb']} GB of {m['ram_total_gb']} GB)."
        else:
            base = f"RAM usage is {m['ram_percent']}%."
        # Attribution only when RAM is genuinely elevated (never a blind
        # threshold diagnosis) — a cheap "ram" query stays cheap otherwise.
        if m["ram_percent"] >= 90:
            top = [c for c in _top_consumers("ram", limit=3) if c["value"] >= 0.5]
            if top:
                base += f" {top[0]['name']} is currently using about {_fmt_gb(top[0]['value'])} GB, the biggest contributor."
        return base
    if name == "gpu":
        if m.get("gpu") is None:
            return "I can't read GPU usage on this system right now."
        return f"GPU usage is {m['gpu']}%."
    if name == "storage":
        volumes = _storage_volumes()
        if not volumes:
            return "I can't read disk usage right now."
        return format_storage_usage(volumes)
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
    kio_issues: list[str] = []
    if snap["state"] == "degraded":
        kio_issues.append("KIO is running in a degraded state.")
    if snap.get("warning_count"):
        n = snap["warning_count"]
        kio_issues.append(
            f"{n} internal issue{'s' if n != 1 else ''} "
            f"{'was' if n == 1 else 'were'} recorded recently."
        )
    if comps.get("browser") == "disconnected":
        kio_issues.append("The browser connection is down.")
    if comps.get("telegram") == "unavailable":
        kio_issues.append("Telegram isn't connected.")

    # Correlate KIO health AND system conditions (RAM/CPU/storage/battery)
    # from the structured diagnostic model — never "nothing is wrong" while
    # verified serious system conditions exist.
    conditions = _notable_conditions()
    if not kio_issues and not conditions:
        return "I don't see anything seriously wrong right now."
    parts = ["Here's what I can see:"]
    for c in conditions:
        parts.append("• " + c["explanation"])
    for issue in kio_issues:
        parts.append("• " + issue)
    return "\n".join(parts)


def format_storage_usage(volumes: Optional[list[dict[str, Any]]] = None) -> str:
    """Per-volume storage view — pressure is per drive, never global."""
    if volumes is None:
        volumes = _storage_volumes()
    if not volumes:
        return "I can't read disk usage right now."
    pressured = [v for v in volumes if v["pressure"] != "ok"]
    roomy = [v for v in volumes if v["pressure"] == "ok"]
    if len(pressured) == 1 and roomy:
        p = pressured[0]
        others = _join_names([v["label"] for v in roomy[:2]])
        verb = "have" if len(roomy[:2]) > 1 else "has"
        level = "critically low on space" if p["pressure"] == "critical" else "getting fairly full"
        return (
            f"Your {p['label']} drive is {level} — {p['percent']}% used, "
            f"with about {p['free_gb']} GB free. {others} still {verb} plenty of space."
        )
    if pressured:
        lines = []
        for v in pressured:
            level = "critically low on space" if v["pressure"] == "critical" else "getting fairly full"
            lines.append(f"• {v['label']} {v['percent']}% used, about {v['free_gb']} GB free ({level})")
        for v in roomy:
            lines.append(f"• {v['label']} {v['percent']}% used, plenty of space")
        return "Here's how your storage looks:\n" + "\n".join(lines)
    return "Storage looks healthy:\n" + "\n".join(
        f"• {v['label']} {v['percent']}% used ({v['free_gb']} GB free)" for v in volumes
    )


def format_storage_attribution() -> str:
    """'what's using my storage' / 'why is my disk full' — per-volume view
    with bounded contributor attribution where safely observable."""
    volumes = _storage_volumes()
    if not volumes:
        return "I can't read disk usage right now."
    pressured = [v for v in volumes if v["pressure"] != "ok"]
    lines = []
    for v in pressured:
        base = f"{v['label']} {v['percent']}% used ({v['free_gb']} GB free)"
        contributors = _storage_contributors(v)
        if contributors:
            names = [f"{c['name']} (about {_fmt_gb(c['size_gb'])} GB)" for c in contributors]
            base += f" — mostly {_join_names(names)}"
        else:
            base += " — I couldn't pin down a single large folder within a quick scan"
        lines.append("• " + base)
    for v in volumes:
        if v["pressure"] == "ok":
            lines.append(f"• {v['label']} {v['percent']}% used, plenty of space")
    if pressured:
        return "Here's what's using your storage:\n" + "\n".join(lines)
    return "Storage looks healthy:\n" + "\n".join(
        f"• {v['label']} {v['percent']}% used ({v['free_gb']} GB free)" for v in volumes
    )


def format_resources(kind: str) -> str:
    """'what's using my RAM/CPU' — attribution from real sources."""
    kind = (kind or "").strip().lower()
    if kind == "ram":
        m = _system_metrics()
        if m.get("ram_percent") is None:
            return "I can't read RAM usage right now."
        top = [c for c in _top_consumers("ram", limit=5) if c["value"] >= 0.5]
        if not top:
            return f"RAM is at {m['ram_percent']}%. I couldn't clearly identify a single big consumer right now."
        names = []
        for c in top:
            extra = f" (across {c['processes']} instances)" if c["processes"] > 1 else ""
            names.append(f"{c['name']} (about {_fmt_gb(c['value'])} GB){extra}")
        return f"RAM is at {m['ram_percent']}%. The biggest consumers right now are {_join_names(names)}."
    if kind == "cpu":
        m = _system_metrics()
        if m.get("cpu") is None:
            return "I can't read CPU usage right now."
        top = [c for c in _top_consumers("cpu", limit=5) if c["value"] >= 1.0]
        if not top:
            return f"CPU usage is around {m['cpu']}% right now, but nothing stands out as a single heavy consumer."
        names = [f"{c['name']} (about {_fmt_gb(c['value'])}%)" for c in top]
        return f"CPU is at about {m['cpu']}%. The busiest things right now are {_join_names(names)}."
    return "I can't read that right now."


def format_resources_all() -> str:
    """Compact aggregate view for '/resources'."""
    m = _system_metrics()
    lines: list[str] = []
    if m.get("cpu") is not None:
        lines.append(f"CPU: {m['cpu']}%")
    if m.get("ram_percent") is not None:
        lines.append(f"RAM: {m['ram_percent']}%")
    if m.get("gpu") is not None:
        lines.append(f"GPU: {m['gpu']}%")
    for v in _storage_volumes():
        lines.append(f"{v['label']} {v['percent']}% used")
    if m.get("battery_percent") is not None:
        lines.append(f"Battery: {m['battery_percent']}%")
    if not lines:
        return "I can't read resource usage right now."
    return "Current resource usage:\n" + "\n".join("• " + l for l in lines)


def format_diagnostic() -> str:
    """'why is my computer slow' — ranked conditions, strongest
    contributors first, never an invented diagnosis."""
    conditions = _notable_conditions()
    if not conditions:
        return "I don't see a clear resource bottleneck right now."
    order = {"critical": 4, "high": 3, "medium": 2}
    conditions.sort(key=lambda c: order.get(c["severity"], 0), reverse=True)
    lead = conditions[0]["explanation"]
    if len(conditions) == 1:
        return lead + " That's the main bottleneck I can point to right now."
    rest = " ".join(c["explanation"] for c in conditions[1:])
    return lead + " There's more worth noting: " + rest


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
        "lock_state": format_lock_state,
        "cpu": lambda: format_metric("cpu"),
        "ram": lambda: format_metric("ram"),
        "gpu": lambda: format_metric("gpu"),
        "storage": lambda: format_metric("storage"),
        "battery": lambda: format_metric("battery"),
        "components": lambda: format_components(target),
        "whats_wrong": format_whats_wrong,
        "resources": format_resources_all,
        "resources_ram": lambda: format_resources("ram"),
        "resources_cpu": lambda: format_resources("cpu"),
        "resources_storage": format_storage_attribution,
        "diagnostic": format_diagnostic,
        "app_installed": lambda: _format_app_installed(target),
    }
    message = formatters.get(action, format_status)()
    return {"success": True, "message": message, "action": action, "target": target}


def _format_app_installed(target: str) -> str:
    """Deterministic installed-app existence answer — real OS probe, never an
    LLM guess. "I couldn't find X installed" when discovery cannot prove it;
    truthful affirmative with the resolved name when it can.
    """
    from mini_kio.core.routing_utils import probe_app_existence
    app = (target or "").strip()
    if not app:
        return "What app would you like me to check?"
    if probe_app_existence(app):
        return f"Yes — {app} is installed."
    return f"I couldn't find {app} installed on your computer."
