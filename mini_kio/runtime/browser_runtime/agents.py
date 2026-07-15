"""Parallel browser agents — research, monitoring, and background execution."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from playwright.async_api import Page

logger = logging.getLogger("browser_runtime.agents")


@dataclass
class AgentResult:
    """Result from a single browser agent execution."""
    agent_id: str
    agent_type: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_ms: float = 0.0


class ResearchAgent:
    """Autonomous browser research agent.

    Given a query, navigates to sources, extracts content,
    and returns structured research results.
    """

    def __init__(self, navigator: Any, scripting: Any, dom: Any, ocr: Any | None = None) -> None:
        self._navigator = navigator
        self._scripting = scripting
        self._dom = dom
        self._ocr = ocr

    async def research(self, page: Page, query: str, *,
                       sources: list[str] | None = None,
                       max_pages: int = 5,
                       timeout_per_source_s: float = 30.0) -> AgentResult:
        """Execute a multi-source research workflow on a single page.

        The agent navigates through search results or provided URLs,
        extracts content, and returns structured findings.
        """
        agent_id = f"research_{int(time.time() * 1000)}"
        start = time.time()
        findings: list[dict[str, Any]] = []

        try:
            url = f"https://www.google.com/search?q={__import__('urllib').parse.quote_plus(query)}"
            nav_result = await self._navigator.goto(page, url, timeout_ms=int(timeout_per_source_s * 1000))
            if not nav_result.success:
                return AgentResult(agent_id=agent_id, agent_type="research", success=False,
                                   error=f"Navigation failed: {nav_result.error}",
                                   started_at=start, completed_at=time.time())

            # Extract search result URLs
            links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href^="/url"]'))
                    .map(a => {
                        const params = new URLSearchParams(a.getAttribute('href')?.split('?')[1] || '');
                        return params.get('q') || a.href;
                    })
                    .filter(h => h && h.startsWith('http'))
                    .slice(0, $max_pages)
            """) or []

            for url in links[:max_pages]:
                try:
                    r = await self._navigator.goto(page, url, timeout_ms=int(timeout_per_source_s * 1000))
                    if not r.success:
                        continue
                    text = await self._scripting.extract_text(page)
                    title = await page.title()
                    findings.append({"url": url, "title": title, "text": text[:5000],
                                     "status_code": r.status_code})
                except Exception as exc:
                    findings.append({"url": url, "error": str(exc)})

            return AgentResult(agent_id=agent_id, agent_type="research", success=True,
                               data={"query": query, "sources_visited": len(links),
                                     "findings": findings, "total_findings": len(findings)},
                               started_at=start, completed_at=time.time(),
                               duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            return AgentResult(agent_id=agent_id, agent_type="research", success=False,
                               error=str(exc), started_at=start, completed_at=time.time())


class MonitoringAgent:
    """Background browser monitoring agent.

    Periodically checks a page for changes, content, or conditions.
    Emits observations when conditions are met.
    """

    def __init__(self, runtime: Any, check_interval_s: float = 30.0) -> None:
        self._runtime = runtime
        self._check_interval_s = check_interval_s
        self._tasks: dict[str, asyncio.Task] = {}
        self._observers: dict[str, Callable] = {}

    async def monitor(self, agent_id: str, page: Page,
                      check_fn: Callable[[Page], Awaitable[dict[str, Any]]],
                      *, interval_s: float | None = None,
                      max_checks: int = 0) -> None:
        """Run a periodic check function on a page."""
        interval = interval_s or self._check_interval_s
        checks = 0
        while True:
            if max_checks and checks >= max_checks:
                break
            try:
                result = await check_fn(page)
                if result.get("triggered"):
                    observer = self._observers.get(agent_id)
                    if observer:
                        await observer(result)
                checks += 1
            except Exception as exc:
                logger.warning("Monitoring agent '%s' check failed: %s", agent_id, exc)
            await asyncio.sleep(interval)

    def start(self, agent_id: str, page: Page,
              check_fn: Callable[[Page], Awaitable[dict[str, Any]]],
              *, on_trigger: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
              interval_s: float | None = None,
              max_checks: int = 0) -> None:
        if agent_id in self._tasks:
            logger.warning("Monitoring agent '%s' already running", agent_id)
            return
        if on_trigger:
            self._observers[agent_id] = on_trigger
        self._tasks[agent_id] = asyncio.create_task(
            self.monitor(agent_id, page, check_fn, interval_s=interval_s, max_checks=max_checks)
        )
        logger.info("Monitoring agent '%s' started (interval=%.1fs)", agent_id, interval_s or self._check_interval_s)

    def stop(self, agent_id: str) -> None:
        task = self._tasks.pop(agent_id, None)
        if task:
            task.cancel()
            self._observers.pop(agent_id, None)
            logger.info("Monitoring agent '%s' stopped", agent_id)

    def stop_all(self) -> None:
        for agent_id in list(self._tasks.keys()):
            self.stop(agent_id)


class ParallelAgentManager:
    """Manages parallel execution of multiple browser agents.

    Each agent gets its own tab/page within a shared workspace.
    Agents run concurrently and results are collected asynchronously.
    """

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._agents: dict[str, asyncio.Task] = {}
        self._results: dict[str, AgentResult] = {}

    async def run_agent(self, agent_id: str, agent_fn: Callable, *,
                        workspace: str = "default") -> AgentResult:
        """Run an agent function with its own tab in the given workspace."""
        try:
            tab = await self._runtime.new_tab(workspace)
            page = self._runtime.page(tab.tab_id)
            result = await agent_fn(page)
            self._results[agent_id] = result
            return result
        except Exception as exc:
            result = AgentResult(agent_id=agent_id, agent_type="parallel", success=False, error=str(exc))
            self._results[agent_id] = result
            return result

    async def run_parallel(self, agents: dict[str, Callable], *,
                           workspace: str = "default") -> dict[str, AgentResult]:
        """Run multiple agents in parallel, each in its own tab."""
        tasks = {}
        for agent_id, fn in agents.items():
            task = asyncio.create_task(self.run_agent(agent_id, fn, workspace=workspace))
            tasks[agent_id] = task
        results = {}
        for agent_id, task in tasks.items():
            try:
                results[agent_id] = await task
            except Exception as exc:
                results[agent_id] = AgentResult(agent_id=agent_id, agent_type="parallel",
                                                 success=False, error=str(exc))
        self._results.update(results)
        return results

    def get_result(self, agent_id: str) -> AgentResult | None:
        return self._results.get(agent_id)

    def all_results(self) -> dict[str, AgentResult]:
        return dict(self._results)

    def clear_results(self) -> None:
        self._results.clear()


from typing import Awaitable
