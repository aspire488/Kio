"""AURA integration — strengthened observation emission from all execution paths.

KIO emits structured observations for every execution event.
AURA consumes these for memory, reasoning, learning, and planning.
KIO never implements cognition — only structured emission.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class ObservationStream:
    """Structured observation emission with batching and context enrichment.

    Every execution event produces a structured observation:
      {
        "event_type": "execution.completed",
        "source": "kio.execution",
        "timestamp": 1234567890.123,
        "data": { ... },
        "context": { ... },
        "session_id": "...",
      }
    """

    def __init__(self, session_id: str = "") -> None:
        self._session_id = session_id
        self._batch: list[dict[str, Any]] = []
        self._max_batch_size = 20

    def emit(self, event_type: str, data: dict[str, Any],
             context: dict[str, Any] | None = None) -> None:
        observation = {
            "event_type": event_type,
            "source": "kio.execution",
            "timestamp": time.time(),
            "data": data,
            "context": context or {},
            "session_id": self._session_id,
        }
        self._batch.append(observation)
        try:
            from mini_kio.core.runtime import aura_emit_observation
            aura_emit_observation(event_type, data, context=context or {})
        except Exception:
            pass
        if len(self._batch) >= self._max_batch_size:
            self.flush()

    def execution(self, result: dict[str, Any]) -> None:
        event_type = "execution.completed" if result.get("success") else "execution.failed"
        if result.get("blocked"):
            event_type = "execution.blocked"
        self.emit(event_type, {
            "action": result.get("action", ""),
            "target": result.get("target", ""),
            "status": result.get("outcome_class", ""),
            "outcome_class": result.get("outcome_class", ""),
            "failure_class": result.get("failure_class", ""),
            "message": str(result.get("message", ""))[:500],
            "elapsed_ms": result.get("elapsed_ms", 0),
            "handler": result.get("handler", ""),
            "tool_version": result.get("tool_version", ""),
            "execution_id": result.get("execution_id", ""),
        })

    def browser_action(self, action: str, tab_id: str, url: str,
                       result: dict[str, Any]) -> None:
        self.emit("browser.action", {
            "action": action, "tab_id": tab_id, "url": url[:500],
            "success": result.get("success", False),
            "selector": result.get("selector", ""),
            "duration_ms": result.get("duration_ms", 0),
        }, context={"source": "browser_runtime"})

    def browser_navigation(self, url: str, result: dict[str, Any]) -> None:
        self.emit("browser.navigation", {
            "url": url[:500],
            "success": result.get("success", False),
            "status_code": result.get("status_code"),
            "attempts": result.get("attempts", 1),
            "duration_ms": result.get("duration_ms", 0),
        }, context={"source": "browser_runtime"})

    def browser_tab(self, event: str, tab_id: str, url: str = "") -> None:
        self.emit(f"browser.tab.{event}", {
            "tab_id": tab_id, "url": url[:500] if url else "",
        }, context={"source": "browser_runtime"})

    def browser_crash(self, error: str) -> None:
        self.emit("browser.crash", {"error": error[:500]},
                   context={"source": "browser_runtime", "severity": "critical"})

    def browser_recovery(self, success: bool, attempt: int) -> None:
        self.emit("browser.recovery", {
            "success": success, "attempt": attempt,
        }, context={"source": "browser_runtime", "severity": "high"})

    def browser_agent(self, agent_id: str, agent_type: str,
                      status: str, data: dict[str, Any]) -> None:
        self.emit(f"browser.agent.{status}", {
            "agent_id": agent_id, "agent_type": agent_type, **data,
        }, context={"source": "browser_agents"})

    def workflow(self, wf_id: str, name: str, status: str,
                 progress: dict[str, Any] | None = None) -> None:
        self.emit(f"workflow.{status}", {
            "workflow_id": wf_id, "name": name, **(progress or {}),
        }, context={"source": "execution_engine"})

    def workflow_step(self, wf_id: str, step_name: str, status: str,
                      action: str, target: str) -> None:
        self.emit(f"workflow.step.{status}", {
            "workflow_id": wf_id, "step_name": step_name,
            "action": action, "target": target[:200],
        }, context={"source": "execution_engine"})

    def desktop_action(self, action: str, result: dict[str, Any]) -> None:
        self.emit("desktop.action", {
            "action": action, "success": result.get("success", False),
            "message": str(result.get("message", ""))[:200],
        }, context={"source": "desktop"})

    def mcp_tool(self, server_type: str, tool_name: str,
                 result: dict[str, Any]) -> None:
        self.emit("mcp.tool", {
            "server_type": server_type, "tool_name": tool_name,
            "success": result.get("success", False),
            "message": str(result.get("message", ""))[:200],
        }, context={"source": "mcp"})

    def mcp_connection(self, server_type: str, status: str,
                       error: str = "") -> None:
        self.emit(f"mcp.connection.{status}", {
            "server_type": server_type, "error": error[:200],
        }, context={"source": "mcp", "severity": "high" if status == "failed" else "info"})

    def auth_challenge(self, challenge_type: str, url: str) -> None:
        self.emit("auth.challenge.detected", {
            "challenge_type": challenge_type, "url": url[:500],
        }, context={"source": "browser_runtime.reauth", "severity": "high"})

    def auth_handoff(self, challenge_type: str, url: str) -> None:
        self.emit("auth.handoff.requested", {
            "challenge_type": challenge_type, "url": url[:500],
        }, context={"source": "browser_runtime.reauth", "severity": "high"})

    def checkpoint(self, cp_id: str, action: str, url: str = "") -> None:
        self.emit(f"checkpoint.{action}", {
            "checkpoint_id": cp_id, "url": url[:500],
        }, context={"source": "browser_runtime.checkpoint"})

    def session(self, action: str, workspace: str, count: int = 0) -> None:
        self.emit(f"session.{action}", {
            "workspace": workspace, "count": count,
        }, context={"source": "browser_runtime.session"})

    def flush(self) -> None:
        if not self._batch:
            return
        batch = self._batch
        self._batch = []
        try:
            from mini_kio.core.runtime import aura_emit_observation
            aura_emit_observation("observation_batch", {
                "count": len(batch), "observations": batch,
            })
        except Exception:
            pass

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id


# Global observation stream instance
_stream: ObservationStream | None = None


def get_observation_stream(session_id: str = "") -> ObservationStream:
    global _stream
    if _stream is None:
        _stream = ObservationStream(session_id)
    return _stream


def reset_observation_stream() -> None:
    global _stream
    _stream = None
