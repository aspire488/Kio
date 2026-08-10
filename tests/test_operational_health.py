"""
test_operational_health.py — Operational Awareness (Capability G)
==================================================================
Deterministic KIO health / status / uptime / system-health /
component-status / "what's wrong" queries.

Invariants under test:
  - every natural variant routes to OPERATIONAL (no LLM fallback)
  - values come from real (patched) state providers, never fabricated
  - unavailable metrics stay unavailable — never 0
  - responses survive the response composer (no stripped implementation
    tokens, no URLs, no "::", no internal ids)
  - knowledge/state/media queries keep their existing deterministic routing
"""

import pytest

from mini_kio.core.pipeline import Pipeline
from mini_kio.core.pipeline.types import IntentType
from mini_kio.core import operational_health as ops


# ---------------------------------------------------------------------------
# Classifier: the semantic family
# ---------------------------------------------------------------------------

def _decision(text: str):
    p = Pipeline()
    return p._classifier.classify(text, text)


def _op(text: str):
    d = _decision(text)
    assert d.intent_type == IntentType.OPERATIONAL, (
        f"{text!r} -> {d.intent_type.value}/{d.action} (expected OPERATIONAL)"
    )
    return d.action, d.target


def test_kio_health_variants():
    assert _op("health")[0] == "health"
    # Explicit slash command requests the full per-component report.
    assert _op("/health")[0] == "health_detail"
    assert _op("KIO health")[0] == "health"
    assert _op("kio, health")[0] == "health"
    assert _op("kio's health")[0] == "health"
    assert _op("are you ok")[0] == "health"
    assert _op("are you healthy")[0] == "health"
    assert _op("is everything working")[0] == "health"
    assert _op("is everything okay")[0] == "health"
    assert _op("how is kio")[0] == "health"
    assert _op("what's going on")[0] == "health"


def test_kio_status_variants():
    assert _op("status")[0] == "status"
    assert _op("/status")[0] == "status"
    assert _op("ping")[0] == "status"
    assert _op("are you busy")[0] == "status"
    assert _op("are you there")[0] == "status"
    assert _op("what are you doing")[0] == "status"
    assert _op("what is kio currently doing")[0] == "status"
    assert _op("what's your status")[0] == "status"
    assert _op("what is kio's status")[0] == "status"


def test_uptime_variants():
    assert _op("uptime")[0] == "uptime"
    assert _op("/uptime")[0] == "uptime"
    assert _op("kio uptime")[0] == "uptime"
    assert _op("what's your uptime")[0] == "uptime"
    assert _op("how long have you been running")[0] == "uptime"
    assert _op("how long has kio been running")[0] == "uptime"


def test_system_health_variants():
    assert _op("system")[0] == "system"
    assert _op("/system")[0] == "system"
    assert _op("systemhealth")[0] == "system"
    assert _op("/systemhealth")[0] == "system"
    assert _op("system health")[0] == "system"
    assert _op("system status")[0] == "system"
    assert _op("how is my computer")[0] == "system"
    assert _op("how is my pc doing")[0] == "system"
    assert _op("computer health")[0] == "system"
    assert _op("system uptime")[0] == "system_uptime"
    assert _op("how long has my computer been on")[0] == "system_uptime"


def test_metric_variants():
    assert _op("cpu")[0] == "cpu"
    assert _op("cpu usage")[0] == "cpu"
    assert _op("what's my cpu usage")[0] == "cpu"
    assert _op("how much cpu am i using")[0] == "cpu"
    assert _op("ram")[0] == "ram"
    assert _op("memory")[0] == "ram"
    assert _op("ram usage")[0] == "ram"
    assert _op("how much ram am i using")[0] == "ram"
    assert _op("how much memory is left")[0] == "ram"
    assert _op("gpu usage")[0] == "gpu"
    assert _op("is my gpu being used")[0] == "gpu"
    assert _op("storage")[0] == "storage"
    assert _op("how much storage do i have")[0] == "storage"
    assert _op("is my battery charging")[0] == "battery"
    assert _op("battery status")[0] == "battery"


def test_component_variants():
    assert _op("is the browser connected") == ("components", "browser")
    assert _op("is telegram connected") == ("components", "telegram")
    assert _op("is media working") == ("components", "media")
    assert _op("are the providers healthy") == ("components", "services")
    assert _op("is mcp connected") == ("components", "tools")
    assert _op("is kio's runtime okay") == ("components", "kio")
    assert _op("what services are connected")[0] == "components"


def test_whats_wrong_variants():
    assert _op("what's wrong")[0] == "whats_wrong"
    assert _op("what is wrong")[0] == "whats_wrong"
    assert _op("is something wrong")[0] == "whats_wrong"
    assert _op("why are you unhealthy")[0] == "whats_wrong"
    assert _op("why isn't something working")[0] == "whats_wrong"
    assert _op("diagnose")[0] == "whats_wrong"
    assert _op("diagnose your status")[0] == "whats_wrong"


def test_knowledge_and_state_queries_stay_put():
    # Greeting stays conversational.
    assert _decision("how are you").intent_type == IntentType.GREETING
    # Desktop-state family unchanged.
    assert _decision("what's open").intent_type == IntentType.BROWSER_TABS
    assert _decision("what's active").intent_type == IntentType.BROWSER_TABS
    assert _decision("what am i using").intent_type == IntentType.BROWSER_TABS
    # Media state unchanged.
    assert _decision("what's playing").intent_type == IntentType.MEDIA_TRANSPORT
    # Knowledge/conversation queries never hijacked by the operational family.
    for q in (
        "what is chatgpt",
        "what's open source",
        "what is running time",
        "how long is the movie",
        "how much does the ram cost",
        "what should i use for coding",
        "tell me about chrome",
        "what's your name",
        "what's going on in the match",
        "what's wrong with the build",
    ):
        assert _decision(q).intent_type != IntentType.OPERATIONAL, q
    # Imperative app control unchanged.
    assert _decision("open chrome").intent_type == IntentType.DESKTOP_OPEN


# ---------------------------------------------------------------------------
# Formatters: real state, honest unavailable values
# ---------------------------------------------------------------------------

def _patch_snap(monkeypatch, **kw):
    base = {
        "state": "running", "integrity_status": "healthy", "integrity_score": 0,
        "health_score": 100, "warning_count": 0, "uptime_s": 12960.0,
        "ram_mb": 120.5, "running": True,
    }
    base.update(kw)
    monkeypatch.setattr(ops, "_kio_health_snapshot", lambda: base)


def _patch_comps(monkeypatch, **kw):
    base = {
        "browser": "connected", "telegram": "connected", "media": "ready",
        "services": "healthy", "tools": "connected",
    }
    base.update(kw)
    monkeypatch.setattr(ops, "_component_states", lambda: base)


def _patch_metrics(monkeypatch, **kw):
    base = {
        "cpu": 21, "ram_percent": 34, "ram_used_gb": 5.2, "ram_total_gb": 15.9,
        "disk_percent": 46, "disk_free_gb": 612.0, "battery_percent": 67,
        "battery_charging": True, "system_uptime_s": 190000.0, "gpu": 8,
    }
    base.update(kw)
    monkeypatch.setattr(ops, "_system_metrics", lambda: base)


def _patch_volumes(monkeypatch, *vols):
    if not vols:
        vols = ({"mountpoint": "C:\\", "label": "C:", "fstype": "NTFS",
                 "total_gb": 256.0, "used_gb": 117.8, "free_gb": 138.2,
                 "percent": 46, "pressure": "ok"},)
    monkeypatch.setattr(ops, "_storage_volumes", lambda: list(vols))


def test_kio_health_healthy(monkeypatch):
    _patch_snap(monkeypatch)
    _patch_comps(monkeypatch)
    msg = ops.format_kio_health()
    # 2026-08-10 response policy: natural short prose by default.
    assert msg == "KIO's healthy and running normally."
    # The explicit /health command still gets the full per-component detail.
    detail = ops.format_health_detail()
    assert detail.startswith("KIO is healthy.")
    assert "Browser: connected" in detail
    assert "Uptime: 3h 36m" in detail


def test_kio_health_degraded(monkeypatch):
    _patch_snap(monkeypatch, integrity_status="degraded", health_score=40)
    _patch_comps(monkeypatch, browser="disconnected")
    msg = ops.format_kio_health()
    assert msg.startswith("KIO's running, but some things need attention.")
    assert "The browser connection is down." in msg


def test_kio_health_not_running(monkeypatch):
    _patch_snap(monkeypatch, state="init", running=False)
    assert ops.format_kio_health() == "KIO is not running right now."


def test_status_ready_vs_working(monkeypatch):
    _patch_snap(monkeypatch, state="ready")
    assert ops.format_status() == "KIO is ready.\nUptime: 3h 36m\nCurrent activity: Idle"
    _patch_snap(monkeypatch, state="running")
    msg = ops.format_status()
    assert msg.startswith("KIO is working.")
    assert "Current activity: Working" in msg


def test_uptime_words(monkeypatch):
    _patch_snap(monkeypatch)
    assert ops.format_uptime() == "KIO has been running for 3 hours and 36 minutes."
    _patch_snap(monkeypatch, uptime_s=30.0)
    assert ops.format_uptime() == "KIO has been running for less than a minute."


def test_system_health_full(monkeypatch):
    _patch_metrics(monkeypatch)
    _patch_volumes(monkeypatch)
    msg = ops.format_system_health()
    assert msg.startswith("Your system looks healthy.")
    assert "CPU: 21%" in msg
    assert "RAM: 34% (5.2 GB of 15.9 GB)" in msg
    assert "GPU: 8%" in msg
    assert "C: 46% used (138.2 GB free)" in msg


def test_system_health_heavy(monkeypatch):
    _patch_metrics(monkeypatch, cpu=97)
    assert ops.format_system_health().startswith("Your system is under heavy load right now.")


def test_unavailable_never_zero(monkeypatch):
    monkeypatch.setattr(ops, "_storage_volumes", lambda: [])
    _patch_metrics(
        monkeypatch, cpu=None, ram_percent=None, ram_used_gb=None, ram_total_gb=None,
        disk_percent=None, disk_free_gb=None, battery_percent=None,
        battery_charging=None, system_uptime_s=None, gpu=None,
    )
    assert ops.format_system_health() == "I can't read your system stats right now."
    assert ops.format_metric("cpu") == "I can't read CPU usage right now."
    assert ops.format_metric("ram") == "I can't read RAM usage right now."
    assert ops.format_metric("gpu") == "I can't read GPU usage on this system right now."
    assert ops.format_metric("storage") == "I can't read disk usage right now."
    assert ops.format_metric("battery") == "Battery status isn't available on this system."
    assert ops.format_system_uptime() == "I can't read the system uptime right now."


def test_single_metrics(monkeypatch):
    _patch_metrics(monkeypatch)
    _patch_volumes(monkeypatch)
    assert ops.format_metric("cpu") == "CPU usage is 21%."
    assert ops.format_metric("gpu") == "GPU usage is 8%."
    assert ops.format_metric("storage") == "Storage looks healthy:\n• C: 46% used (138.2 GB free)"
    assert ops.format_metric("battery") == "Battery is at 67% and charging."


def test_components_focused(monkeypatch):
    _patch_comps(monkeypatch)
    assert ops.format_components("browser") == "The browser is connected."
    assert ops.format_components("telegram") == "Telegram is connected."
    assert ops.format_components("media") == "Media is ready."
    assert ops.format_components("providers") == "Core services are healthy."
    assert ops.format_components("mcp") == "External tools are connected."
    _patch_comps(monkeypatch, browser="unavailable")
    assert ops.format_components("browser") == "I can't determine that right now."


def test_whats_wrong_none_and_degraded(monkeypatch):
    _patch_snap(monkeypatch)
    _patch_comps(monkeypatch)
    _patch_metrics(monkeypatch)
    _patch_volumes(monkeypatch)  # healthy volume -> no storage condition
    assert ops.format_whats_wrong() == "I don't see anything seriously wrong right now."
    _patch_snap(monkeypatch, state="degraded", warning_count=3)
    _patch_comps(monkeypatch, browser="disconnected", tools="unavailable")
    msg = ops.format_whats_wrong()
    assert "KIO is running in a degraded state." in msg
    assert "3 internal issues were recorded recently." in msg
    assert "The browser connection is down." in msg


# ---------------------------------------------------------------------------
# End-to-end: pipeline classification + composer survival
# ---------------------------------------------------------------------------

_FORBIDDEN = ("runtime", "provider", "connector", "mcp", "pipeline",
              "capability", "::", "http://", "https://", "Error:")


def _assert_clean(text: str):
    low = text.lower()
    for token in _FORBIDDEN:
        assert token not in low, f"leak token {token!r} in {text!r}"


def test_all_operational_results_clean(monkeypatch):
    _patch_snap(monkeypatch)
    _patch_comps(monkeypatch)
    _patch_metrics(monkeypatch)
    _patch_volumes(monkeypatch)
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=5: [])
    monkeypatch.setattr(ops, "_storage_contributors", lambda v: [])
    for action in ("health", "status", "uptime", "system", "system_uptime",
                   "cpu", "ram", "gpu", "storage", "battery",
                   "components", "whats_wrong", "resources", "resources_ram",
                   "resources_cpu", "resources_storage", "diagnostic"):
        result = ops.operational_result(action, target="browser")
        assert result.get("success") is True
        _assert_clean(result.get("message", ""))


def test_pipeline_end_to_end(monkeypatch):
    _patch_snap(monkeypatch)
    _patch_comps(monkeypatch)
    _patch_metrics(monkeypatch)
    p = Pipeline()
    result = p.run("KIO health", session_id="ops_test")
    assert result.get("success") is True
    msg = result.get("message", "")
    assert "KIO's healthy and running normally." in msg
    _assert_clean(msg)
    # Slash-command form routes identically.
    result = p.run("/status", session_id="ops_test")
    assert "KIO is" in result.get("message", "")
    _assert_clean(result.get("message", ""))


def test_pipeline_truthful_when_not_running(monkeypatch):
    # A not-running snapshot must yield a truthful answer, never a
    # fabricated healthy report.
    _patch_snap(monkeypatch, state="init", running=False)
    p = Pipeline()
    result = p.run("status", session_id="ops_test")
    assert result.get("success") is True
    assert result.get("message") == "KIO is not running right now."
    result = p.run("what's wrong", session_id="ops_test")
    assert result.get("message") == "KIO is not running right now."
