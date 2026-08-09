"""
test_diagnostic_attribution.py — System awareness + diagnostic attribution
==========================================================================
Deterministic, structured system diagnostics (pre-Slice-9 refinement):

- per-volume storage analysis (never one global number)
- bounded storage attribution (depth/time-limited, honest failure)
- application-aware RAM/CPU attribution (grouped, never cross-merged,
  disappeared processes never fabricated)
- structured conditions (severity / evidence / contributors / observed_at)
  — the proactive-condition foundation
- "what's wrong" correlates conditions (never contradicts evidence)
- "why is my computer slow" diagnostic with ranked contributors
- natural response quality (no PIDs / URLs / Error / dev tokens)
- routing family + knowledge queries stay put
"""

import pytest

from mini_kio.core.pipeline import Pipeline
from mini_kio.core.pipeline.types import IntentType
from mini_kio.core import operational_health as ops


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vol(label="C:", mountpoint="C:\\", percent=82, free_gb=46.4,
         pressure="low", total_gb=256.0):
    return {"mountpoint": mountpoint, "label": label, "fstype": "NTFS",
            "total_gb": total_gb, "used_gb": round(total_gb - free_gb, 1),
            "free_gb": free_gb, "percent": percent, "pressure": pressure}


def _patch_metrics(monkeypatch, **kw):
    base = {
        "cpu": 21, "ram_percent": 34, "ram_used_gb": 5.2, "ram_total_gb": 15.9,
        "disk_percent": 46, "disk_free_gb": 612.0, "battery_percent": 67,
        "battery_charging": True, "system_uptime_s": 190000.0, "gpu": 8,
    }
    base.update(kw)
    monkeypatch.setattr(ops, "_system_metrics", lambda: base)


def _patch_volumes(monkeypatch, *vols):
    monkeypatch.setattr(ops, "_storage_volumes", lambda: list(vols))


def _patch_snap(monkeypatch, **kw):
    base = {"state": "running", "integrity_status": "healthy", "integrity_score": 0,
            "health_score": 100, "warning_count": 0, "uptime_s": 60.0,
            "ram_mb": 120.5, "running": True}
    base.update(kw)
    monkeypatch.setattr(ops, "_kio_health_snapshot", lambda: base)


def _patch_comps(monkeypatch, **kw):
    base = {"browser": "connected", "telegram": "connected", "media": "ready",
            "services": "healthy", "tools": "connected"}
    base.update(kw)
    monkeypatch.setattr(ops, "_component_states", lambda: base)


def _decision(text: str):
    return Pipeline()._classifier.classify(text, text)


def _op(text: str):
    d = _decision(text)
    assert d.intent_type == IntentType.OPERATIONAL, (
        f"{text!r} -> {d.intent_type.value}/{d.action}"
    )
    return d.action, d.target


# ---------------------------------------------------------------------------
# Per-volume storage — pressure is per drive, never global
# ---------------------------------------------------------------------------

def test_full_c_empty_d_distinguishes_drive_pressure(monkeypatch):
    _patch_volumes(monkeypatch,
                   _vol(percent=82, free_gb=46.4, pressure="low"),
                   _vol(label="D:", mountpoint="D:\\", percent=0, free_gb=233.4,
                        pressure="ok"))
    msg = ops.format_storage_usage()
    assert "Your C: drive is getting fairly full" in msg
    assert "82% used" in msg
    assert "D: still has plenty of space" in msg
    # The exact global claim the mandate forbids must never appear.
    assert "your storage is nearly full" not in msg.lower()


def test_storage_metric_is_per_volume(monkeypatch):
    _patch_volumes(monkeypatch,
                   _vol(percent=82, free_gb=46.4, pressure="low"),
                   _vol(label="D:", mountpoint="D:\\", percent=0, free_gb=233.4,
                        pressure="ok"))
    msg = ops.format_metric("storage")
    assert "C: drive is getting fairly full" in msg
    assert "D: still has plenty of space" in msg


def test_all_volumes_healthy(monkeypatch):
    _patch_volumes(monkeypatch,
                   _vol(percent=35, free_gb=140.0, pressure="ok"),
                   _vol(label="D:", mountpoint="D:\\", percent=8, free_gb=214.0,
                        pressure="ok"))
    msg = ops.format_storage_usage()
    assert msg.startswith("Storage looks healthy:")
    assert "• C: 35% used (140.0 GB free)" in msg
    assert "• D: 8% used (214.0 GB free)" in msg


def test_multiple_pressured_volumes_listed_individually(monkeypatch):
    _patch_volumes(monkeypatch,
                   _vol(percent=97, free_gb=4.0, pressure="critical"),
                   _vol(label="D:", mountpoint="D:\\", percent=92, free_gb=9.0,
                        pressure="low"),
                   _vol(label="E:", mountpoint="E:\\", percent=20, free_gb=120.0,
                        pressure="ok"))
    msg = ops.format_storage_usage()
    assert "critically low on space" in msg
    assert "getting fairly full" in msg
    assert "E: 20% used, plenty of space" in msg


def test_storage_unavailable(monkeypatch):
    _patch_volumes(monkeypatch)
    monkeypatch.setattr(ops, "_storage_volumes", lambda: [])
    assert ops.format_metric("storage") == "I can't read disk usage right now."


# ---------------------------------------------------------------------------
# Bounded storage attribution (real filesystem fixture)
# ---------------------------------------------------------------------------

def test_storage_contributors_bounded_scan(tmp_path, monkeypatch):
    # Real filesystem: verify the generic bounded scan attributes the largest
    # top-level entry, sums depth-limited descendants, and respects the
    # minimum-size filter.
    big = tmp_path / "bigdata"
    small = tmp_path / "small"
    big.mkdir()
    small.mkdir()
    (big / "a.bin").write_bytes(b"\0" * (6 * 1024 * 1024))          # 6 MB
    (big / "sub").mkdir()
    (big / "sub" / "b.bin").write_bytes(b"\0" * (2 * 1024 * 1024))  # 2 MB
    (small / "c.bin").write_bytes(b"\0" * 1024)
    # Lower the meaningful-size bar to ~2 KB so the byte-scale fixture works:
    # bigdata (8 MB) qualifies, 'small' (1 KB) stays below the bar.
    monkeypatch.setattr(ops, "_STORAGE_CONTRIBUTOR_MIN_GB", 0.000002)
    contributors = ops._storage_contributors(
        {"mountpoint": str(tmp_path), "label": "T:", "percent": 99, "pressure": "critical"}
    )
    assert contributors
    assert contributors[0]["name"] == "bigdata"
    # 'small' is below the meaningful size bar and must not be reported.
    assert all(c["name"] != "small" for c in contributors)


def test_storage_contributors_graceful_on_missing_root():
    assert ops._storage_contributors(
        {"mountpoint": "Z:\\nonexistent", "label": "Z:", "percent": 99,
         "pressure": "critical"}
    ) == []


def test_storage_attribution_uses_contributors(monkeypatch):
    _patch_volumes(monkeypatch,
                   _vol(percent=82, free_gb=46.4, pressure="low"),
                   _vol(label="D:", mountpoint="D:\\", percent=0, free_gb=233.4,
                        pressure="ok"))
    monkeypatch.setattr(ops, "_storage_contributors", lambda v: [
        {"name": "Users", "size_gb": 96.0},
        {"name": "Program Files", "size_gb": 61.5},
    ])
    msg = ops.format_storage_attribution()
    assert "C: 82% used (46.4 GB free) — mostly Users (about 96 GB) and Program Files (about 61.5 GB)" in msg
    assert "D: 0% used, plenty of space" in msg


def test_storage_attribution_honest_when_unidentifiable(monkeypatch):
    _patch_volumes(monkeypatch,
                   _vol(percent=82, free_gb=46.4, pressure="low"),
                   _vol(label="D:", mountpoint="D:\\", percent=0, free_gb=233.4,
                        pressure="ok"))
    monkeypatch.setattr(ops, "_storage_contributors", lambda v: [])
    msg = ops.format_storage_attribution()
    assert "I couldn't pin down a single large folder within a quick scan" in msg
    assert "D: 0% used, plenty of space" in msg


# ---------------------------------------------------------------------------
# RAM / CPU attribution
# ---------------------------------------------------------------------------

def test_ram_attribution_dominant_consumer(monkeypatch):
    _patch_metrics(monkeypatch, ram_percent=95, ram_used_gb=14.4, ram_total_gb=15.2)
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [
        {"name": "DaVinci Resolve", "value": 6.1, "unit": "GB", "processes": 2},
        {"name": "Chrome", "value": 1.8, "unit": "GB", "processes": 31},
    ])
    msg = ops.format_metric("ram")
    assert "RAM usage is 95%" in msg
    assert "DaVinci Resolve is currently using about 6.1 GB, the biggest contributor." in msg


def test_ram_attribution_multiple_contributors(monkeypatch):
    _patch_metrics(monkeypatch, ram_percent=93)
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=5: [
        {"name": "App A", "value": 4.0, "unit": "GB", "processes": 1},
        {"name": "App B", "value": 3.5, "unit": "GB", "processes": 3},
    ])
    msg = ops.format_resources("ram")
    assert "RAM is at 93%" in msg
    assert "App A (about 4 GB)" in msg
    assert "App B (about 3.5 GB) (across 3 instances)" in msg


def test_ram_cheap_query_no_attribution_below_threshold(monkeypatch):
    _patch_metrics(monkeypatch, ram_percent=34)
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [
        {"name": "X", "value": 9.0, "unit": "GB", "processes": 1}])
    msg = ops.format_metric("ram")
    assert "RAM usage is 34%" in msg
    assert "X" not in msg  # attribution is only for genuinely elevated RAM


def test_cpu_attribution(monkeypatch):
    _patch_metrics(monkeypatch, cpu=92)
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=5: [
        {"name": "Build Server", "value": 240.0, "unit": "%", "processes": 1},
    ])
    msg = ops.format_resources("cpu")
    assert "CPU is at about 92%" in msg
    assert "Build Server (about 240%)" in msg


def test_attribution_no_consumer_truthful(monkeypatch):
    _patch_metrics(monkeypatch, ram_percent=95)
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=5: [])
    msg = ops.format_resources("ram")
    assert "couldn't clearly identify" in msg


def test_top_consumers_grouping_never_cross_merges(monkeypatch):
    # Two different binaries must never be merged into one consumer; the
    # friendly identity comes from the canonical desktop identity helper.
    seen = {}

    class _FakeProc:
        def __init__(self, name, rss_gb):
            self._name, self._rss = name, rss_gb
        def name(self):
            return self._name
        def memory_info(self):
            class _MI:
                rss = self._rss * (1024 ** 3)
            return _MI()
        def cpu_percent(self, interval=None):
            return 1.0

    import psutil
    monkeypatch.setattr(psutil, "process_iter", lambda: [
        _FakeProc("python.exe", 6.1),
        _FakeProc("python.exe", 1.2),
        _FakeProc("node.exe", 0.8),
        _FakeProc("spotify.exe", 0.3),
    ])
    top = ops._top_consumers("ram", limit=5)
    by_name = {c["name"]: c for c in top}
    assert by_name["Python"]["processes"] == 2
    assert by_name["Python"]["value"] == 7.3  # 6.1 + 1.2 grouped, never merged with Node
    assert by_name["Node"]["processes"] == 1
    assert by_name["Spotify"]["processes"] == 1
    assert len(top) == 3  # the two identical python.exe instances form one app group


# ---------------------------------------------------------------------------
# Structured conditions (proactive foundation)
# ---------------------------------------------------------------------------

def test_conditions_carry_structured_evidence(monkeypatch):
    _patch_metrics(monkeypatch, ram_percent=95, cpu=92)
    _patch_volumes(monkeypatch, _vol(percent=82, free_gb=46.4, pressure="low"))
    monkeypatch.setattr(ops, "_storage_contributors", lambda v: [])
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [])
    conds = {c["id"]: c for c in ops._system_conditions()}
    ram = conds["ram"]
    assert ram["severity"] == "high"
    assert ram["current_value"] == 95 and ram["threshold"] == 95
    assert ram["evidence"] == "virtual_memory"
    assert ram["observed_at"] > 0
    assert "explanation" in ram
    assert conds["cpu"]["severity"] == "high"
    stor = conds["storage_c"]
    assert stor["severity"] == "medium"
    assert stor["volume"] == "C:" and stor["free_gb"] == 46.4
    assert stor["contributors"] == []
    assert "getting fairly full" in stor["explanation"]


def test_condition_severity_mapping(monkeypatch):
    _patch_volumes(monkeypatch, _vol(percent=82, free_gb=46.4, pressure="low"))
    monkeypatch.setattr(ops, "_storage_contributors", lambda v: [])
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [])
    for ram_pct, expected in ((95, "high"), (90, "medium"), (80, "low"), (30, "info")):
        _patch_metrics(monkeypatch, ram_percent=ram_pct, cpu=5)
        conds = {c["id"]: c for c in ops._system_conditions()}
        assert conds["ram"]["severity"] == expected, ram_pct


def test_conditions_include_contributors_when_attributed(monkeypatch):
    _patch_metrics(monkeypatch, ram_percent=95, cpu=5)
    _patch_volumes(monkeypatch)
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [
        {"name": "DaVinci Resolve", "value": 6.1, "unit": "GB", "processes": 1}])
    conds = {c["id"]: c for c in ops._system_conditions()}
    assert "DaVinci Resolve (about 6.1 GB) the biggest consumer" in conds["ram"]["explanation"]


def test_battery_low_condition(monkeypatch):
    _patch_metrics(monkeypatch, ram_percent=34, cpu=5, battery_percent=8,
                   battery_charging=False)
    _patch_volumes(monkeypatch)
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [])
    conds = {c["id"]: c for c in ops._system_conditions()}
    assert conds["battery"]["severity"] == "low"
    assert "Battery is down to 8%" in conds["battery"]["explanation"]


# ---------------------------------------------------------------------------
# "What's wrong?" correlates conditions — never contradicts evidence
# ---------------------------------------------------------------------------

def test_whats_wrong_correlates_conditions(monkeypatch):
    _patch_snap(monkeypatch)
    _patch_comps(monkeypatch)
    _patch_metrics(monkeypatch, ram_percent=95, cpu=5)
    _patch_volumes(monkeypatch, _vol(percent=82, free_gb=46.4, pressure="low"))
    monkeypatch.setattr(ops, "_storage_contributors", lambda v: [])
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [])
    msg = ops.format_whats_wrong()
    assert "RAM is running high at 95%" in msg
    assert "C: drive is getting fairly full" in msg
    assert "nothing" not in msg.lower()  # never contradicts verified conditions


def test_whats_wrong_nothing_serious(monkeypatch):
    _patch_snap(monkeypatch)
    _patch_comps(monkeypatch)
    _patch_metrics(monkeypatch, cpu=21, ram_percent=34)
    monkeypatch.setattr(ops, "_storage_volumes", lambda: [])
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [])
    assert ops.format_whats_wrong() == "I don't see anything seriously wrong right now."


def test_whats_wrong_kio_and_system_together(monkeypatch):
    _patch_snap(monkeypatch, state="degraded")
    _patch_comps(monkeypatch, browser="disconnected")
    _patch_metrics(monkeypatch, ram_percent=95, cpu=5)
    _patch_volumes(monkeypatch, _vol(percent=82, free_gb=46.4, pressure="low"))
    monkeypatch.setattr(ops, "_storage_contributors", lambda v: [])
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [])
    msg = ops.format_whats_wrong()
    assert "RAM is running high at 95%" in msg
    assert "KIO is running in a degraded state." in msg
    assert "The browser connection is down." in msg


# ---------------------------------------------------------------------------
# "Why is my computer slow?" — ranked diagnostic
# ---------------------------------------------------------------------------

def test_diagnostic_single_bottleneck(monkeypatch):
    _patch_metrics(monkeypatch, ram_percent=95, cpu=21)
    monkeypatch.setattr(ops, "_storage_volumes", lambda: [])
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [
        {"name": "X", "value": 6.1, "unit": "GB", "processes": 1}])
    msg = ops.format_diagnostic()
    assert "RAM is running high at 95%" in msg
    assert "main bottleneck" in msg


def test_diagnostic_multiple_conditions_ranked(monkeypatch):
    _patch_metrics(monkeypatch, ram_percent=95, cpu=92)
    _patch_volumes(monkeypatch, _vol(percent=82, free_gb=46.4, pressure="low"))
    monkeypatch.setattr(ops, "_storage_contributors", lambda v: [])
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [])
    msg = ops.format_diagnostic()
    assert "RAM is running high at 95%" in msg
    assert "worth noting" in msg
    assert "C: drive is getting fairly full" in msg


def test_diagnostic_no_clear_bottleneck(monkeypatch):
    _patch_metrics(monkeypatch, cpu=21, ram_percent=34)
    monkeypatch.setattr(ops, "_storage_volumes", lambda: [])
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [])
    assert ops.format_diagnostic() == "I don't see a clear resource bottleneck right now."


# ---------------------------------------------------------------------------
# Routing family + knowledge queries stay put
# ---------------------------------------------------------------------------

def test_resources_routing():
    assert _op("resources")[0] == "resources"
    assert _op("/resources")[0] == "resources"
    assert _op("resource usage")[0] == "resources"


def test_diagnostic_routing():
    assert _op("why is my computer slow")[0] == "diagnostic"
    assert _op("why is my pc slow")[0] == "diagnostic"
    assert _op("why is my system laggy")[0] == "diagnostic"
    assert _op("why is everything slow")[0] == "diagnostic"
    # "slow to boot" is a temporal troubleshooting question with no boot-time
    # telemetry — it still routes deterministically to the diagnostic family,
    # where KIO truthfully reports no current resource bottleneck.
    assert _op("why is my computer slow to boot")[0] == "diagnostic"


def test_resource_attribution_routing():
    assert _op("what's using my ram")[0] == "resources_ram"
    assert _op("what is using my memory")[0] == "resources_ram"
    assert _op("what's eating my ram")[0] == "resources_ram"
    assert _op("what's using my cpu")[0] == "resources_cpu"
    assert _op("what is consuming my processor")[0] == "resources_cpu"
    assert _op("what's using my storage")[0] == "resources_storage"
    assert _op("what's using up my storage")[0] == "resources_storage"
    assert _op("what's taking up space")[0] == "resources_storage"
    assert _op("what is taking up my disk space")[0] == "resources_storage"
    assert _op("which drive is full")[0] == "resources_storage"
    assert _op("which drives are full")[0] == "resources_storage"
    assert _op("why is my disk full")[0] == "resources_storage"
    assert _op("why is my drive full")[0] == "resources_storage"
    assert _op("is my disk full")[0] == "storage"
    assert _op("how much space do i have")[0] == "storage"
    assert _op("how much free space is left")[0] == "storage"


def test_knowledge_queries_stay_knowledge():
    for q in (
        "what is ram",
        "what is system health",
        "what is vs code",
        "why does storage matter",
        "which drive is best for gaming",
        "what is taking up space in the universe",
        "how much space does the movie need",
        "what is cpu usage in computers",
    ):
        d = _decision(q)
        assert d.intent_type != IntentType.OPERATIONAL, q


def test_kio_prefixed_attribution_variants():
    assert _op("kio, why is my computer slow")[0] == "diagnostic"
    assert _op("KIO — what's using my ram?")[0] == "resources_ram"


# ---------------------------------------------------------------------------
# Response quality — no leaks, natural voice
# ---------------------------------------------------------------------------

_FORBIDDEN = ("runtime", "provider", "connector", "mcp", "pipeline",
              "capability", "::", "http://", "https://", "Error:", "pid=")


def test_diagnostic_responses_are_clean(monkeypatch):
    _patch_snap(monkeypatch)
    _patch_comps(monkeypatch)
    _patch_metrics(monkeypatch, ram_percent=95, cpu=92)
    _patch_volumes(monkeypatch, _vol(percent=82, free_gb=46.4, pressure="low"))
    monkeypatch.setattr(ops, "_storage_contributors", lambda v: [
        {"name": "Users", "size_gb": 96.0}])
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [
        {"name": "DaVinci Resolve", "value": 6.1, "unit": "GB", "processes": 1}])
    for action in ("storage", "whats_wrong", "diagnostic", "resources_ram",
                   "resources_cpu", "resources_storage", "resources"):
        msg = ops.operational_result(action)["message"]
        low = msg.lower()
        for token in _FORBIDDEN:
            assert token not in low, f"{action}: leak {token!r} in {msg!r}"


def test_pipeline_end_to_end_diagnostic_actions(monkeypatch):
    # The real pipeline (classifier -> coordinator -> composer) must route the
    # new family deterministically and survive _ResponseComposer._strip_leaks
    # / _contains_dev_terms intact — no leak tokens, message preserved.
    _patch_snap(monkeypatch)
    _patch_comps(monkeypatch)
    _patch_metrics(monkeypatch, ram_percent=95, cpu=5)
    _patch_volumes(monkeypatch,
                   _vol(percent=82, free_gb=46.4, pressure="low"),
                   _vol(label="D:", mountpoint="D:\\", percent=0, free_gb=233.4,
                        pressure="ok"))
    monkeypatch.setattr(ops, "_storage_contributors", lambda v: [])
    monkeypatch.setattr(ops, "_top_consumers", lambda kind, limit=3: [])
    p = Pipeline()
    for q in ("what's wrong", "storage", "why is my computer slow",
              "what's using my ram"):
        result = p.run(q, session_id="diag_test")
        assert result.get("success") is True, q
        msg = result.get("message", "")
        low = msg.lower()
        for token in _FORBIDDEN:
            assert token not in low, (q, token, msg)
    # The correlated per-volume answer survives the composer verbatim enough
    # to identify the actual drive under pressure.
    result = p.run("storage", session_id="diag_test")
    assert "C: drive is getting fairly full" in result.get("message", "")
    result = p.run("what's wrong", session_id="diag_test")
    assert "RAM is running high at 95%" in result.get("message", "")
