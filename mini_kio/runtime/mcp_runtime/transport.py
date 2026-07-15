"""Newline-delimited JSON transport over a subprocess's stdio, matching the
MCP stdio transport convention: one JSON-RPC message per line on stdout,
messages written to stdin the same way. stderr is captured for diagnostics."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from .exceptions import ServerStartError, TransportError
from .types import ServerConfig

logger = logging.getLogger("mcp_runtime.transport")

LineHandler = Callable[[str], Awaitable[None]]


class StdioTransport:
    """Owns a subprocess and pumps its stdout lines to a handler while
    exposing an async write() for outgoing messages."""

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._on_line: Optional[LineHandler] = None
        self._on_exit: Optional[Callable[[int], Awaitable[None]]] = None
        self._write_lock = asyncio.Lock()
        self._stderr_buffer: list[str] = []

    def set_line_handler(self, handler: LineHandler) -> None:
        self._on_line = handler

    def set_exit_handler(self, handler: Callable[[int], Awaitable[None]]) -> None:
        self._on_exit = handler

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._config.command,
                *self._config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._config.env or None,
                cwd=self._config.cwd,
            )
        except (OSError, FileNotFoundError) as exc:
            raise ServerStartError(f"failed to start server '{self._config.server_id}': {exc}") from exc

        self._reader_task = asyncio.create_task(self._pump_stdout())
        self._stderr_task = asyncio.create_task(self._pump_stderr())

    async def _pump_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        stdout = self._process.stdout
        try:
            while True:
                line = await stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                if self._on_line is not None:
                    try:
                        await self._on_line(text)
                    except Exception:  # noqa: BLE001
                        logger.exception("line handler raised for server %s", self._config.server_id)
        except asyncio.CancelledError:
            return
        finally:
            code = self._process.returncode if self._process else None
            logger.info("server %s stdout closed (exit code=%s)", self._config.server_id, code)
            if self._on_exit is not None:
                await self._on_exit(code if code is not None else -1)

    async def _pump_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        stderr = self._process.stderr
        try:
            while True:
                line = await stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    self._stderr_buffer.append(text)
                    if len(self._stderr_buffer) > 200:
                        self._stderr_buffer.pop(0)
                    logger.debug("[%s stderr] %s", self._config.server_id, text)
        except asyncio.CancelledError:
            return

    def recent_stderr(self) -> list[str]:
        return list(self._stderr_buffer)

    async def write(self, raw: str) -> None:
        if self._process is None or self._process.stdin is None:
            raise TransportError(f"server '{self._config.server_id}' has no active stdin")
        async with self._write_lock:
            try:
                self._process.stdin.write((raw + "\n").encode("utf-8"))
                await self._process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                raise TransportError(f"write failed, pipe broken for server '{self._config.server_id}': {exc}") from exc

    async def stop(self, *, timeout_s: float = 5.0) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()
        if self._process is None:
            return
        if self._process.returncode is None:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=timeout_s)
            except asyncio.TimeoutError:
                logger.warning("server %s did not terminate in time; killing", self._config.server_id)
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass
        self._process = None

    @property
    def pid(self) -> Optional[int]:
        return self._process.pid if self._process else None
