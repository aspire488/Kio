"""
execution/workflows.py — GENERAL WORKFLOW/AUTOMATION capability
(multi-step composition over every existing KIO action).

The WorkflowEngine (parallel steps, dependencies, retries, approval gates,
rollback, checkpoints, persistence) already exists but nothing routed to it.
This module makes it USER-REACHABLE through the canonical utility seam:

    create a workflow to open chrome and search for python   -> parse steps,
                                                                run engine
    run the workflow                                         -> execute
    workflow status                                          -> list + state
    cancel the workflow                                      -> cancel
    pause the workflow / resume the workflow                 -> pause/resume

Steps are parsed from natural language by the SAME command parser used for
multi-step commands, so any action KIO can already do (open/close/search/
play/remind/watch/research/file) becomes a workflow step. Consequential
actions (close/system) get approval gates so nothing irreversible happens
without explicit consent. One general mechanism — never per-domain.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_engine = None

# Actions that are consequential/irreversible enough to require explicit
# approval before a workflow executes them. General categories, never per-app.
_APPROVAL_ACTIONS = frozenset({
    "close", "close_app", "close_all", "close_all_apps",
    "lock_system", "shutdown", "restart", "unlock_system",
    "delete", "delete_file", "send_message",
})

_CREATE_RE = re.compile(
    r"^\s*(?:create|set\s+up|make|build|start|begin)\s+(?:a\s+)?workflow\s+(?:to|that|which)?\s*(.+)$",
    re.I,
)
_CREATE_RE2 = re.compile(
    r"^\s*(?:workflow|automation)\s*:\s*(.+)$", re.I,
)
_RUN_RE = re.compile(
    r"^\s*(?:run|execute|start|fire|launch)\s+(?:the\s+|my\s+|this\s+)?workflow\s*$", re.I,
)
_STATUS_RE = re.compile(
    r"^\s*(?:what'?s|what\s+is|show|list)\s+(?:the\s+)?workflow\s*(?:status|state)?\s*$"
    r"|^\s*workflow\s+(?:status|list|state)\s*$",
    re.I,
)
_CANCEL_RE = re.compile(
    r"^\s*(?:cancel|stop|abort|kill)\s+(?:the\s+|my\s+|this\s+)?workflow\s*$", re.I,
)
_PAUSE_RE = re.compile(r"^\s*(?:pause|hold|freeze)\s+(?:the\s+|my\s+|this\s+)?workflow\s*$", re.I)
_RESUME_RE = re.compile(r"^\s*(?:resume|continue|unpause)\s+(?:the\s+|my\s+|this\s+)?workflow\s*$", re.I)


def _get_engine():
    global _engine
    if _engine is None:
        from mini_kio.execution.engine import WorkflowEngine
        from mini_kio.core.execution_boundary import execute_action
        _engine = WorkflowEngine(execute_fn=lambda action, target="", **kw: execute_action(action, target))
    return _engine


def _extract_workflow_command(query: str):
    """(sub_action, steps_text) for the workflow family."""
    low = query.lower().strip()
    if _RUN_RE.search(low):
        return "run", ""
    if _STATUS_RE.search(low):
        return "status", ""
    if _CANCEL_RE.search(low):
        return "cancel", ""
    if _PAUSE_RE.search(low):
        return "pause", ""
    if _RESUME_RE.search(low):
        return "resume", ""
    m = _CREATE_RE.match(query) or _CREATE_RE2.match(query)
    if m:
        return "create", m.group(1).strip()
    return None, None


def looks_like_workflow(query: str) -> bool:
    """Routing hook: True for the workflow family (create/run/status/cancel/
    pause/resume). A 'create' needs step text; the control verbs stand alone."""
    action, steps = _extract_workflow_command(query)
    if action in ("run", "status", "cancel", "pause", "resume"):
        return True
    if action == "create":
        return bool(steps)
    return False


def _parse_steps(steps_text: str):
    """Parse natural step text into workflow step dicts using the same
    command parser as multi-step execution. Consequential actions get
    approval_required=True."""
    from mini_kio.core.command_parser import parse_command
    parsed = parse_command(steps_text)
    steps = []
    for p in parsed:
        action = p.get("action", "")
        target = p.get("target", "")
        if not action:
            continue
        step = {
            "name": ("%s %s" % (action, target)).strip(),
            "action": action,
            "target": target,
            "approval_required": action in _APPROVAL_ACTIONS,
        }
        steps.append(step)
    return steps


def workflow_answer(query: str, ctx=None, decision=None) -> dict:
    """Canonical workflow owner: create / run / status / cancel / pause /
    resume. Composes any existing KIO action into an engine-executed workflow
    with approval gates on consequential steps."""
    action, steps_text = _extract_workflow_command(query)
    engine = _get_engine()

    if action == "status":
        wfs = engine.list_workflows()
        if not wfs:
            return {"success": True, "message": "No workflows have been created yet.",
                    "type": "workflow", "action": "status", "workflows": []}
        parts = []
        for w in wfs[-5:]:
            done = sum(1 for s in w.steps if s.status.name in ("COMPLETED", "SKIPPED", "CANCELLED"))
            parts.append("%s [%s] (%d/%d steps)" % (w.name or w.id, w.status.value, done, len(w.steps)))
        return {"success": True, "message": "Workflows: " + "; ".join(parts) + ".",
                "type": "workflow", "action": "status", "workflows": [w.id for w in wfs]}

    if action == "cancel":
        wfs = engine.list_workflows()
        target = next((w for w in reversed(wfs) if w.status.name in ("PENDING", "RUNNING", "PAUSED")), None)
        if target is None or not engine.cancel_workflow(target.id):
            return {"success": False, "message": "There's no running workflow to cancel.",
                    "type": "workflow", "action": "cancel"}
        return {"success": True, "message": "Workflow cancelled.",
                "type": "workflow", "action": "cancel", "id": target.id}

    if action == "pause":
        target = next((w for w in reversed(engine.list_workflows()) if w.status.name == "RUNNING"), None)
        if target is None or not engine.pause_workflow(target.id):
            return {"success": False, "message": "There's no running workflow to pause.",
                    "type": "workflow", "action": "pause"}
        return {"success": True, "message": "Workflow paused.",
                "type": "workflow", "action": "pause", "id": target.id}

    if action == "resume":
        target = next((w for w in reversed(engine.list_workflows()) if w.status.name == "PAUSED"), None)
        if target is None or not engine.resume_workflow(target.id):
            return {"success": False, "message": "There's no paused workflow to resume.",
                    "type": "workflow", "action": "resume"}
        return {"success": True, "message": "Workflow resumed.",
                "type": "workflow", "action": "resume", "id": target.id}

    if action == "run":
        wfs = engine.list_workflows()
        target = next((w for w in reversed(wfs) if w.status.name in ("PENDING", "PAUSED", "FAILED")), None)
        if target is None:
            return {"success": False,
                    "message": "Create a workflow first — like 'create a workflow to open chrome and search for python'.",
                    "type": "workflow", "action": "run"}
        return _run_workflow(engine, target.id)

    if action == "create":
        if not steps_text:
            return {"success": False,
                    "message": "Tell me the steps — like 'create a workflow to open chrome and search for python'.",
                    "type": "workflow", "action": "create"}
        steps = _parse_steps(steps_text)
        if not steps:
            return {"success": False,
                    "message": "I couldn't pick out any steps from that. Try 'create a workflow to open chrome and search for python'.",
                    "type": "workflow", "action": "create"}
        wf = engine.create_workflow(name=steps_text[:60], steps=steps)
        need_approval = [s["name"] for s in steps if s.get("approval_required")]
        msg = "Workflow created with %d step(s)." % len(steps)
        if need_approval:
            msg += " The step(s) %s need your approval before running." % ", ".join(need_approval)
        else:
            msg += " Say 'run the workflow' to execute it."
        return {"success": True, "message": msg, "type": "workflow",
                "action": "create", "id": wf.id, "steps": [s["name"] for s in steps],
                "approval_required": bool(need_approval)}

    return {"success": False,
            "message": "Tell me what workflow to set up — like 'create a workflow to open chrome and search for python'.",
            "type": "workflow"}


def _run_workflow(engine, wf_id: str) -> dict:
    """Execute a workflow through the engine (async -> sync via the runtime
    bridge). Returns honest per-step results; approval-pending steps wait."""
    wf = engine.get_workflow(wf_id)
    if wf is None:
        return {"success": False, "message": "Workflow not found.", "type": "workflow", "action": "run"}
    pending_approval = [s for s in wf.steps if s.approval_required and not s.approved]
    if pending_approval:
        return {"success": False,
                "message": "Waiting for approval on: %s. Approve before running." % ", ".join(s.name for s in pending_approval),
                "type": "workflow", "action": "run", "id": wf_id, "awaiting_approval": True}
    try:
        from mini_kio.core.async_utils import safe_run_async
        result = safe_run_async(engine.execute(wf_id))
    except Exception as exc:
        logger.warning("[WORKFLOW] execute failed: %s", exc)
        return {"success": False, "message": "Workflow execution failed: %s" % exc,
                "type": "workflow", "action": "run", "id": wf_id}
    if result is None:
        result = wf
    if getattr(result, "status", None) is not None:
        st = result.status.value
        done = sum(1 for s in result.steps if s.status.name in ("COMPLETED", "SKIPPED"))
        msg = "Workflow %s — %s (%d/%d steps)." % (
            "completed" if st == "completed" else ("ended as %s" % st), result.name, done, len(result.steps))
        return {"success": st == "completed", "message": msg, "type": "workflow",
                "action": "run", "id": wf_id, "status": st, "steps": len(result.steps)}
    return {"success": bool(result.get("success")), "message": str(result.get("message", "Workflow ran.")),
            "type": "workflow", "action": "run", "id": wf_id}
