"""Deterministic plugin system — lifecycle, deps, hot-swap.

Load order: topological sort on dependencies, ties broken by name (deterministic).
A plugin registers/unregisters its own providers/handlers in ``on_load``/``on_unload``.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Sequence

logger = logging.getLogger(__name__)


class LifecycleState(enum.Enum):
    CREATED = "created"
    LOADING = "loading"
    LOADED = "loaded"
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    STOPPED = "stopped"
    UNLOADING = "unloading"
    UNLOADED = "unloaded"
    FAILED = "failed"


@dataclass
class PluginSpec:
    name: str
    version: str = "0.1.0"
    dependencies: list[str] = field(default_factory=list)
    on_load: Callable[[], Awaitable[None]] | None = None
    on_start: Callable[[], Awaitable[None]] | None = None
    on_stop: Callable[[], Awaitable[None]] | None = None
    on_unload: Callable[[], Awaitable[None]] | None = None


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginSpec] = {}
        self._states: dict[str, LifecycleState] = {}
        self._errors: dict[str, str] = {}

    # ---- Registration -------------------------------------------------------

    def register(self, spec: PluginSpec) -> PluginSpec:
        if spec.name in self._plugins:
            raise ValueError(f"Plugin {spec.name!r} already registered")
        self._plugins[spec.name] = spec
        self._states[spec.name] = LifecycleState.CREATED
        return spec

    def unregister(self, name: str) -> None:
        state = self._states.get(name)
        if state not in (None, LifecycleState.CREATED, LifecycleState.UNLOADED, LifecycleState.FAILED):
            raise RuntimeError(f"Cannot unregister {name!r}: state={state.value}")
        self._plugins.pop(name, None)
        self._states.pop(name, None)
        self._errors.pop(name, None)

    def get(self, name: str) -> PluginSpec | None:
        return self._plugins.get(name)

    def list(self) -> list[str]:
        return sorted(self._plugins)

    # ---- Dependency resolution ----------------------------------------------

    def resolve_order(self, names: Sequence[str] | None = None) -> list[str]:
        graph = {n: list(self._plugins[n].dependencies) for n in (names or self._plugins)}

        in_degree: dict[str, int] = {}
        for n, deps in graph.items():
            in_degree.setdefault(n, 0)
            for d in deps:
                if d in graph:
                    in_degree[n] = in_degree.get(n, 0) + 1

        ready = sorted([n for n, d in in_degree.items() if d == 0])
        result: list[str] = []

        while ready:
            n = ready.pop(0)
            result.append(n)
            for m, deps in graph.items():
                if n in deps:
                    in_degree[m] -= 1
                    if in_degree[m] == 0:
                        ready.append(m)
                        ready.sort()

        if len(result) != len(graph):
            missing = set(graph) - set(result)
            raise RuntimeError(f"Dependency cycle detected involving: {missing}")

        return result

    # ---- Lifecycle ----------------------------------------------------------

    async def load_all(self) -> None:
        for name in self.resolve_order():
            spec = self._plugins[name]
            try:
                self._states[name] = LifecycleState.LOADING
                if spec.on_load:
                    await spec.on_load()
                self._states[name] = LifecycleState.LOADED
            except Exception as e:
                self._states[name] = LifecycleState.FAILED
                self._errors[name] = str(e)
                logger.error("Plugin %r failed to load: %s", name, e)

    async def start_all(self) -> None:
        for name in self.resolve_order():
            if self._states[name] != LifecycleState.LOADED:
                continue
            spec = self._plugins[name]
            try:
                self._states[name] = LifecycleState.STARTING
                if spec.on_start:
                    await spec.on_start()
                self._states[name] = LifecycleState.ACTIVE
            except Exception as e:
                self._states[name] = LifecycleState.FAILED
                self._errors[name] = str(e)
                logger.error("Plugin %r failed to start: %s", name, e)

    async def stop_all(self, reverse: bool = True) -> None:
        order = self.resolve_order()
        if reverse:
            order = list(reversed(order))
        for name in order:
            if self._states[name] != LifecycleState.ACTIVE:
                continue
            spec = self._plugins[name]
            try:
                self._states[name] = LifecycleState.STOPPING
                if spec.on_stop:
                    await spec.on_stop()
                self._states[name] = LifecycleState.STOPPED
            except Exception as e:
                self._states[name] = LifecycleState.FAILED
                self._errors[name] = str(e)
                logger.error("Plugin %r failed to stop: %s", name, e)

    async def unload_all(self) -> None:
        for name in reversed(self.resolve_order()):
            state = self._states[name]
            if state not in (LifecycleState.STOPPED, LifecycleState.LOADED, LifecycleState.FAILED):
                continue
            spec = self._plugins[name]
            try:
                self._states[name] = LifecycleState.UNLOADING
                if spec.on_unload:
                    await spec.on_unload()
                self._states[name] = LifecycleState.UNLOADED
            except Exception as e:
                self._states[name] = LifecycleState.FAILED
                self._errors[name] = str(e)
                logger.error("Plugin %r failed to unload: %s", name, e)

    async def start(self) -> None:
        await self.load_all()
        await self.start_all()

    async def stop(self) -> None:
        await self.stop_all()
        await self.unload_all()

    # ---- Hot-swap ----------------------------------------------------------

    async def hot_swap(self, name: str, new_spec: PluginSpec) -> None:
        """Replace a plugin at runtime. Dependents are NOT restarted."""
        old = self._plugins.get(name)
        if old:
            old_state = self._states.get(name)
            if old_state == LifecycleState.ACTIVE and old.on_stop:
                await old.on_stop()
            if old.on_unload:
                await old.on_unload()
            self._states[name] = LifecycleState.UNLOADED

        self._plugins[name] = new_spec
        self._states[name] = LifecycleState.CREATED
        # ponytail: dependents not restarted; add cascade restart when hot-swap of shared deps is needed

        spec = self._plugins[name]
        self._states[name] = LifecycleState.LOADING
        if spec.on_load:
            await spec.on_load()
        self._states[name] = LifecycleState.LOADED
        self._states[name] = LifecycleState.STARTING
        if spec.on_start:
            await spec.on_start()
        self._states[name] = LifecycleState.ACTIVE
        logger.info("Hot-swapped plugin %r", name)

    # ---- Queries ------------------------------------------------------------

    def state(self, name: str) -> LifecycleState | None:
        return self._states.get(name)

    def error(self, name: str) -> str | None:
        return self._errors.get(name)

    def healthy(self) -> list[str]:
        return [n for n, s in self._states.items() if s == LifecycleState.ACTIVE]

    def failed(self) -> list[str]:
        return [n for n, s in self._states.items() if s == LifecycleState.FAILED]


# ---- Self-check ------------------------------------------------------------

def _demo() -> None:
    """Minimal smoke test — run with ``python -m runtime.plugin``."""
    import asyncio

    async def _append(lst: list[str], val: str) -> None:
        lst.append(val)

    async def _run() -> None:
        reg = PluginRegistry()
        reg.register(PluginSpec(name="a", dependencies=[]))
        reg.register(PluginSpec(name="b", dependencies=["a"]))
        reg.register(PluginSpec(name="c", dependencies=["a"]))
        reg.register(PluginSpec(name="d", dependencies=["b", "c"]))
        order = reg.resolve_order()
        assert order == ["a", "b", "c", "d"] or order == ["a", "c", "b", "d"], f"Unexpected order: {order}"

        reg2 = PluginRegistry()
        loaded: list[str] = []
        reg2.register(PluginSpec(
            name="x", dependencies=[],
            on_load=lambda: _append(loaded, "x"),
        ))
        await reg2.load_all()
        assert loaded == ["x"]
        assert reg2.state("x") == LifecycleState.LOADED
        await reg2.stop()
        assert reg2.state("x") == LifecycleState.UNLOADED

        reg3 = PluginRegistry()
        reg3.register(PluginSpec(name="h", on_load=lambda: _append(loaded, "h_old")))
        await reg3.load_all()
        await reg3.hot_swap("h", PluginSpec(name="h", on_load=lambda: _append(loaded, "h_new")))
        assert "h_old" in loaded and "h_new" in loaded
        assert reg3.state("h") == LifecycleState.ACTIVE

        reg4 = PluginRegistry()
        reg4.register(PluginSpec(name="p", dependencies=["q"]))
        reg4.register(PluginSpec(name="q", dependencies=["p"]))
        try:
            reg4.resolve_order()
            assert False, "Should have raised"
        except RuntimeError:
            pass

        print("All plugin system checks passed.")

    asyncio.run(_run())


if __name__ == "__main__":
    _demo()
