from __future__ import annotations

import json
import os
import pathlib
import threading
import time
from typing import Any

_TRACE_EVENTS: list[dict[str, Any]] = []
_TRACE_ACTIVE = False
_TRACE_LOCK = threading.Lock()
_TRACE_COMMAND = os.environ.get("KIO_TRACE_COMMAND", "open youtube").strip().lower()
_TRACE_OUTPUT = pathlib.Path(__file__).resolve().parent.parent / "runtime_trace.json"


def start_trace(command: str, channel: str) -> None:
    global _TRACE_ACTIVE
    if _TRACE_ACTIVE:
        return
    if not _TRACE_COMMAND:
        return
    if command.strip().lower() == _TRACE_COMMAND and channel == "telegram":
        _TRACE_ACTIVE = True
        record_trace(
            stage="telegram_update",
            function="handle_message or route",
            file="kio_bot.py or command_router.py",
            details={"command": command, "channel": channel},
        )


def record_trace(
    stage: str,
    function: str,
    file: str,
    provider: str | None = None,
    decision: Any | None = None,
    result: Any | None = None,
    next_stage: str | None = None,
    details: Any | None = None,
) -> None:
    global _TRACE_ACTIVE
    if not _TRACE_ACTIVE:
        return
    if decision is not None and not isinstance(decision, (str, int, float, bool, type(None), dict, list)):
        try:
            decision = repr(decision)
        except Exception:
            decision = str(type(decision))
    if result is not None and not isinstance(result, (str, int, float, bool, type(None), dict, list)):
        try:
            result = repr(result)
        except Exception:
            result = str(type(result))
    event = {
        "timestamp": time.time(),
        "stage": stage,
        "function": function,
        "file": file,
        "provider": provider,
        "decision": decision,
        "result": result,
        "next_stage": next_stage,
        "details": details,
    }
    with _TRACE_LOCK:
        _TRACE_EVENTS.append(event)


def flush_trace(reply: str | None = None) -> None:
    global _TRACE_ACTIVE
    if not _TRACE_ACTIVE:
        return
    payload = {
        "trace_command": _TRACE_COMMAND,
        "timestamp": time.time(),
        "events": _TRACE_EVENTS,
        "telegram_reply": reply,
    }
    try:
        _TRACE_OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass
    _TRACE_ACTIVE = False
