"""Browser checkpoint/restore and workflow recording/replay."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from playwright.async_api import Page

logger = logging.getLogger("browser_runtime.checkpoint")


@dataclass
class Checkpoint:
    """Snapshot of browser state at a moment in time."""
    id: str
    timestamp: float
    workspace: str
    url: str
    title: str
    screenshot_path: str | None = None
    dom_snapshot: str | None = None
    cookies_snapshot: list[dict] | None = None
    tab_id: str | None = None


@dataclass
class WorkflowStep:
    """A single recorded action in a workflow."""
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    duration_ms: float = 0.0
    success: bool = True
    screenshot_before: str | None = None
    screenshot_after: str | None = None


@dataclass
class WorkflowRecording:
    """Complete recording of a browser workflow."""
    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    replay_count: int = 0


class CheckpointManager:
    """Creates and restores browser state checkpoints.

    A checkpoint captures: URL, page title, screenshot, DOM snapshot, and cookies.
    Enables rollback to a known-good state after navigation failures.
    """

    def __init__(self, storage_root: Path) -> None:
        self._storage_root = storage_root / "checkpoints"
        self._storage_root.mkdir(parents=True, exist_ok=True)
        self._checkpoints: dict[str, Checkpoint] = {}

    async def create(self, page: Page, workspace: str, tab_id: str | None = None,
                     *, name: str | None = None, with_screenshot: bool = True,
                     with_dom: bool = False) -> Checkpoint:
        cp_id = name or f"cp_{int(time.time() * 1000)}"
        cp = Checkpoint(
            id=cp_id, timestamp=time.time(), workspace=workspace,
            url=page.url, title=await page.title(), tab_id=tab_id,
        )
        if with_screenshot:
            ss_dir = self._storage_root / "screenshots"
            ss_dir.mkdir(parents=True, exist_ok=True)
            ss_path = ss_dir / f"{cp_id}.png"
            try:
                await page.screenshot(path=str(ss_path), full_page=True)
                cp.screenshot_path = str(ss_path)
            except Exception as exc:
                logger.debug("Checkpoint screenshot failed: %s", exc)
        if with_dom:
            try:
                cp.dom_snapshot = await page.content()
            except Exception as exc:
                logger.debug("Checkpoint DOM snapshot failed: %s", exc)
        # Save cookies
        try:
            cp.cookies_snapshot = await page.context.cookies()
        except Exception:
            pass
        # Persist
        cp_dir = self._storage_root / "data"
        cp_dir.mkdir(parents=True, exist_ok=True)
        (cp_dir / f"{cp_id}.json").write_text(
            json.dumps(asdict(cp), indent=2, default=str), encoding="utf-8"
        )
        self._checkpoints[cp_id] = cp
        logger.info("Checkpoint '%s' created: %s", cp_id, page.url)
        return cp

    async def restore(self, page: Page, cp_id: str) -> bool:
        cp = self._checkpoints.get(cp_id)
        if cp is None:
            cp_dir = self._storage_root / "data"
            cp_file = cp_dir / f"{cp_id}.json"
            if not cp_file.exists():
                logger.warning("Checkpoint '%s' not found", cp_id)
                return False
            cp = Checkpoint(**json.loads(cp_file.read_text(encoding="utf-8")))
        try:
            await page.goto(cp.url, wait_until="domcontentloaded")
            if cp.cookies_snapshot:
                try:
                    await page.context.add_cookies(cp.cookies_snapshot)
                except Exception:
                    pass
            logger.info("Checkpoint '%s' restored: %s", cp_id, cp.url)
            return True
        except Exception as exc:
            logger.warning("Checkpoint restore failed for '%s': %s", cp_id, exc)
            return False

    def list_checkpoints(self, workspace: str | None = None) -> list[Checkpoint]:
        result = list(self._checkpoints.values())
        if workspace:
            result = [cp for cp in result if cp.workspace == workspace]
        return result

    def delete_checkpoint(self, cp_id: str) -> None:
        self._checkpoints.pop(cp_id, None)
        cp_file = self._storage_root / "data" / f"{cp_id}.json"
        if cp_file.exists():
            cp_file.unlink()


class WorkflowRecorder:
    """Records browser interactions as replayable workflows."""

    def __init__(self, storage_root: Path) -> None:
        self._storage_root = storage_root / "workflows"
        self._storage_root.mkdir(parents=True, exist_ok=True)
        self._current: WorkflowRecording | None = None
        self._recordings: dict[str, WorkflowRecording] = {}

    def start_recording(self, name: str) -> None:
        self._current = WorkflowRecording(name=name, created_at=time.time(), updated_at=time.time())
        logger.info("Workflow recording started: '%s'", name)

    def record_step(self, action: str, params: dict[str, Any] | None = None,
                    *, success: bool = True, screenshot_before: str | None = None,
                    screenshot_after: str | None = None) -> None:
        if self._current is None:
            return
        self._current.steps.append(WorkflowStep(
            action=action, params=params or {}, timestamp=time.time(),
            success=success, screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
        ))
        self._current.updated_at = time.time()

    def stop_recording(self) -> WorkflowRecording | None:
        if self._current is None:
            return None
        recording = self._current
        name = recording.name
        path = self._storage_root / f"{name}.json"
        path.write_text(json.dumps(asdict(recording), indent=2, default=str), encoding="utf-8")
        self._recordings[name] = recording
        self._current = None
        logger.info("Workflow recording saved: '%s' (%d steps)", name, len(recording.steps))
        return recording

    def get_recording(self, name: str) -> WorkflowRecording | None:
        if name in self._recordings:
            return self._recordings[name]
        path = self._storage_root / f"{name}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            recording = WorkflowRecording(**data)
            recording.steps = [WorkflowStep(**s) for s in data.get("steps", [])]
            self._recordings[name] = recording
            return recording
        return None

    def list_recordings(self) -> list[str]:
        loaded = list(self._recordings.keys())
        on_disk = [p.stem for p in self._storage_root.glob("*.json")]
        return list(set(loaded + on_disk))

    def delete_recording(self, name: str) -> None:
        self._recordings.pop(name, None)
        path = self._storage_root / f"{name}.json"
        if path.exists():
            path.unlink()


class WorkflowReplayEngine:
    """Replays a recorded workflow against a live page."""

    def __init__(self, dom_controller: Any, navigator: Any) -> None:
        self._dom = dom_controller
        self._navigator = navigator

    async def replay(self, page: Page, recording: WorkflowRecording,
                     *, step_callback: Callable[[int, WorkflowStep], None] | None = None) -> dict[str, Any]:
        """Replay a recorded workflow step by step. Returns summary."""
        results = []
        for i, step in enumerate(recording.steps):
            try:
                if step_callback:
                    step_callback(i, step)
                if step.action == "goto":
                    r = await self._navigator.goto(page, step.params.get("url", ""))
                    results.append({"step": i, "action": step.action, "success": r.success})
                elif step.action == "click":
                    r = await self._dom.click(page, step.params.get("selector", ""))
                    results.append({"step": i, "action": step.action, "success": r.success})
                elif step.action == "fill":
                    r = await self._dom.fill(page, step.params.get("selector", ""), step.params.get("value", ""))
                    results.append({"step": i, "action": step.action, "success": r.success})
                elif step.action == "select":
                    r = await self._dom.select(page, step.params.get("selector", ""), step.params.get("values", []))
                    results.append({"step": i, "action": step.action, "success": r.success})
                elif step.action == "evaluate":
                    try:
                        val = await page.evaluate(step.params.get("expression", ""))
                        results.append({"step": i, "action": step.action, "success": True, "result": val})
                    except Exception as exc:
                        results.append({"step": i, "action": step.action, "success": False, "error": str(exc)})
                else:
                    results.append({"step": i, "action": step.action, "success": False, "error": "unknown_action"})
            except Exception as exc:
                results.append({"step": i, "action": step.action, "success": False, "error": str(exc)})
        success_count = sum(1 for r in results if r.get("success"))
        recording.replay_count += 1
        return {"total": len(results), "success": success_count, "failed": len(results) - success_count,
                "results": results, "replay_count": recording.replay_count}
