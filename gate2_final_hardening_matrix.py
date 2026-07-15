from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import psutil

from mini_kio.core.runtime import (
    bootstrap_runtime,
    dispatch_channel_input,
    get_runtime,
    get_runtime_health_score,
    get_runtime_integrity_snapshot,
    get_runtime_snapshot,
)


RESULT_PATH = Path("gate2_final_hardening_results.json")

PROCESS_FAMILIES: dict[str, set[str]] = {
    "edge": {"msedge.exe"},
    "firefox": {"firefox.exe"},
    "chrome": {"chrome.exe"},
    "comet": {"comet.exe"},
    "calculator": {"calc.exe", "calculatorapp.exe", "win32calculator.exe"},
    "calc": {"calc.exe", "calculatorapp.exe", "win32calculator.exe"},
    "settings": {"systemsettings.exe"},
    "microsoft store": {"winstore.app.exe"},
    "store": {"winstore.app.exe"},
    "explorer": {"explorer.exe"},
    "file explorer": {"explorer.exe"},
    "word": {"winword.exe"},
    "excel": {"excel.exe"},
    "powerpoint": {"powerpnt.exe"},
}

WRAPPER_PROCESSES = {"applicationframehost.exe"}


def _canonical_target(name: str) -> str:
    lowered = name.lower().strip()
    aliases = {
        "calc": "calculator",
        "store": "microsoft store",
        "file explorer": "explorer",
    }
    return aliases.get(lowered, lowered)


def _process_names_for(target: str) -> set[str]:
    canonical = _canonical_target(target)
    return set(PROCESS_FAMILIES.get(canonical, {f"{canonical}.exe"}))


def _live_family_pids(target: str, *, include_wrappers: bool = False) -> list[int]:
    names = _process_names_for(target)
    if include_wrappers:
        names = names | WRAPPER_PROCESSES
    pids: list[int] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            proc_name = (proc.info.get("name") or "").lower()
            if proc_name in names:
                pids.append(int(proc.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            continue
    return sorted(pids)


def _runtime_registry_snapshot() -> list[dict[str, Any]]:
    rt = get_runtime()
    if not rt:
        return []
    return [dict(entry) for entry in rt.tracked_processes]


def _duplicate_registry_names(entries: list[dict[str, Any]]) -> list[str]:
    names = [str(entry.get("name", "")) for entry in entries]
    counts = Counter(name for name in names if name)
    return sorted(name for name, count in counts.items() if count > 1)


def _ram_mb() -> float:
    return psutil.Process().memory_info().rss / 1024 / 1024


def _make_scenarios() -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []

    def add(category: str, command: str, *, expectation: str, target: str = "", repeat: int = 1) -> None:
        for idx in range(repeat):
            scenarios.append(
                {
                    "category": category,
                    "command": command,
                    "expectation": expectation,
                    "target": target,
                    "repeat_index": idx + 1,
                }
            )

    for command in [
        "open edge", "close edge",
        "open firefox", "close firefox",
        "open comet", "close comet",
        "open calc", "close calc",
        "open settings", "close settings",
        "open store", "close store",
    ]:
        add("basic_lifecycle", command, expectation="live")

    for command in [
        "open github in chrome",
        "open reddit in firefox",
        "open claude in comet",
        "open figma in edge",
        "open notion in chrome",
    ]:
        add("routed_browser_opens", command, expectation="live", repeat=4)

    for command in [
        "open notion in chrome and then open vercel in edge",
        "open github in chrome and then open reddit in firefox",
        "open youtube in edge and then open claude in comet",
        "search weather in chrome and then search ai news in comet",
        "open figma in chrome and then open notion in edge",
    ]:
        add("multi_step", command, expectation="live", repeat=4)

    for command in [
        "open google.com in chrome",
        "open docs.github.com in firefox",
        "open mail.google.com in edge",
        "open chat.qwen.ai in chrome",
    ]:
        add("explicit_domains", command, expectation="live", repeat=5)

    for command in [
        "open youtube/feed in chrome",
        "open canva/design in firefox",
        "open github/docs in edge",
        "open amazon/payments in chrome",
    ]:
        add("url_paths", command, expectation="live", repeat=5)

    for command in [
        "open downloads folder", "close file explorer",
        "open videos folder", "close explorer",
        "open kio folder", "close file explorer",
    ]:
        add("explorer_ownership", command, expectation="live", repeat=5)

    for command in [
        "open word", "close word",
        "open excel", "close excel",
        "open powerpoint", "close powerpoint",
        "open settings", "close settings",
        "open store", "close store",
    ]:
        add("office_uwp", command, expectation="live", repeat=3)

    for command in [
        "open cmd",
        "open powershell",
        "open regedit",
        "open taskmgr",
        "open msconfig",
        "open cmd&&chrome in edge",
        "open ../../windows in chrome",
        "open /// in chrome",
    ]:
        add("invalid_security", command, expectation="blocked", repeat=5)

    for command in [
        "recover",
        "status",
    ]:
        add("recovery", command, expectation="success", repeat=8)

    for _ in range(12):
        for command in [
            "open firefox", "close firefox",
            "open edge", "close edge",
        ]:
            add("repeated_browser_cycles", command, expectation="live")

    for _ in range(8):
        for command in [
            "open downloads folder", "close explorer",
        ]:
            add("repeated_explorer_cycles", command, expectation="live")

    for command in [
        "ping",
        "status",
        "who created you",
        "what are your features",
    ]:
        add("long_session", command, expectation="success", repeat=15)

    return scenarios


def _evaluate_result(command: str, target: str, expectation: str, result: dict[str, Any]) -> tuple[str, list[str]]:
    issues: list[str] = []
    success = bool(result.get("success"))
    message = str(result.get("message", ""))
    verification_status = str(result.get("verification_status", ""))
    lowered_command = command.lower()

    if expectation == "blocked":
        if success:
            issues.append("blocked_command_succeeded")
        elif "forbidden" not in message.lower() and "blocked" not in message.lower() and "invalid" not in message.lower():
            issues.append("blocked_command_wrong_message")
        return ("pass" if not issues else "fail", issues)

    if expectation == "success":
        if not success:
            issues.append("expected_success_failed")
        return ("pass" if not issues else "fail", issues)

    if expectation == "live":
        if not success:
            failure_class = str(result.get("failure_class", ""))
            if failure_class in {"not_installed", "launch_failed", "browser_not_found"} or "not found" in message.lower():
                return ("soft_fail", ["environment_availability"])
            issues.append("live_command_failed")
            return ("fail", issues)

        if lowered_command.startswith("close "):
            live_pids = _live_family_pids(target)
            if verification_status == "passed" and live_pids:
                issues.append("false_close_success")
            if verification_status == "passed_with_residuals" and not live_pids:
                issues.append("false_residual_classification")
            return ("pass" if not issues else "fail", issues)

        if lowered_command.startswith("open ") and target:
            live_pids = _live_family_pids(target)
            if not live_pids and "folder" not in lowered_command and " in " not in lowered_command:
                canonical = _canonical_target(target)
                if canonical not in {"word", "excel", "powerpoint"}:
                    issues.append("open_success_without_live_family")
            return ("pass" if not issues else "fail", issues)

        return ("pass", issues)

    return ("pass", issues)


def main() -> int:
    bootstrap_runtime()
    scenarios = _make_scenarios()
    results: list[dict[str, Any]] = []
    issue_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    peak_ram = _ram_mb()
    start = time.monotonic()

    for index, scenario in enumerate(scenarios, start=1):
        command = scenario["command"]
        expectation = scenario["expectation"]
        inferred_target = scenario["target"]
        if not inferred_target:
            lower = command.lower()
            if lower.startswith("open "):
                inferred_target = command[5:].strip()
                for sep in [" in ", " on ", " using "]:
                    if sep in inferred_target.lower():
                        inferred_target = inferred_target.rsplit(sep, 1)[0].strip()
                        break
            elif lower.startswith("close "):
                inferred_target = command[6:].strip()
        result = dispatch_channel_input(command, channel="telegram", user_id=999)
        time.sleep(0.45)

        rt_snapshot = get_runtime_snapshot()
        integrity = get_runtime_integrity_snapshot()
        tracked = _runtime_registry_snapshot()
        duplicates = _duplicate_registry_names(tracked)
        if duplicates:
            issue_counter.update({"duplicate_registry_names": 1})

        status, issues = _evaluate_result(command, inferred_target, expectation, result)
        for issue in issues:
            issue_counter.update({issue: 1})
        status_counter.update({status: 1})
        category_counter.update({scenario["category"]: 1})

        ram = _ram_mb()
        peak_ram = max(peak_ram, ram)
        results.append(
            {
                "index": index,
                "category": scenario["category"],
                "command": command,
                "expectation": expectation,
                "status": status,
                "issues": issues,
                "result": result,
                "runtime": rt_snapshot,
                "integrity": integrity,
                "tracked_processes": tracked,
                "duplicate_names": duplicates,
                "ram_mb": round(ram, 2),
                "health_score": get_runtime_health_score(),
            }
        )

    duration_s = round(time.monotonic() - start, 2)
    final_runtime = get_runtime_snapshot()
    final_integrity = get_runtime_integrity_snapshot()
    summary = {
        "scenario_count": len(scenarios),
        "duration_s": duration_s,
        "status_counts": dict(status_counter),
        "category_counts": dict(category_counter),
        "issue_counts": dict(issue_counter),
        "peak_ram_mb": round(peak_ram, 2),
        "final_runtime": final_runtime,
        "final_integrity": final_integrity,
    }

    payload = {"summary": summary, "results": results}
    RESULT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"Results written to {RESULT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
