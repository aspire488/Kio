"""
connector.py - Browser Connector V1

WebSocket server that proxies commands between KIO and Chrome Extension.

Architecture:
┌─────────┐  JSON/WS   ┌──────────┐  JSON/WS   ┌──────────┐
│  KIO    │ ←───────→ │ Connector│ ←───────→ │ Extension │
│ (async) │            │ (server) │            │ (Chrome)  │
└─────────┘            └──────────┘            └──────────┘

Connector acts as a transparent proxy: validates KIO commands, sends to
extension, validates responses, returns TabResult.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import sys
import threading
from typing import Any, Optional
from urllib.parse import urlparse

import websockets
from websockets.asyncio.server import serve

from .protocol import (
    Message, MessageType, OwnedTab, TabResult,
    new_command_id, validate_connect, validate_command,
    serialize, deserialize,
)
from .registry import TabRegistry

logger = logging.getLogger(__name__)

_WS_HOST = "127.0.0.1"
_WS_PORT = 9877
_CONNECTOR_THREAD_NAME = "kio-bc-ws"

_MEDIA_DOMAINS = [
    "youtube.com",
    "music.youtube.com",
    "open.spotify.com",
    "soundcloud.com",
    "twitch.tv",
    "netflix.com",
    "primevideo.com",
    "disneyplus.com",
]

# RC1: the extension build the runtime expects. Chrome serves a cached copy
# of an unpacked MV3 service worker, so the loaded build can lag the working
# tree while answering basic DOM reads. The extension sends its build in the
# connect message; a stale/unknown build is REJECTED at registration so a
# current-build service worker always wins the single connection slot (the
# stale one would otherwise keep stealing it via its 3s reconnect loop).
# Single source of truth: mini_kio/browser_connector/build.py (BUG 13).
from mini_kio.browser_connector.build import EXTENSION_BUILD as _EXPECTED_EXTENSION_BUILD

# ── Thread exception hook (global, installed once) ────────────────────

_original_thread_excepthook: Any = None


def _install_thread_excepthook() -> None:
    global _original_thread_excepthook
    if threading.excepthook is _kio_thread_excepthook:
        return
    _original_thread_excepthook = threading.excepthook
    threading.excepthook = _kio_thread_excepthook


def _kio_thread_excepthook(args: Any) -> None:
    name = args.thread.name if args.thread else "unknown"
    logger.critical(
        "[CONNECTOR] Thread '%s' crashed: %s: %s",
        name, args.exc_type.__name__, args.exc_value,
    )
    logger.critical(
        "[CONNECTOR] Thread exception traceback",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    if _original_thread_excepthook and _original_thread_excepthook is not _kio_thread_excepthook:
        _original_thread_excepthook(args)


# ── Mock Extension ───────────────────────────────────────────────────

NOT_CONNECTED = "not_connected"

# R9: server-side extension connection state model.
# DISCONNECTED → HANDSHAKING → REGISTERED → READY. The liveness watchdog
# clears a stale/closed handle back to DISCONNECTED so a fresh extension
# connection (MV3 service worker restart) registers cleanly.
STATE_DISCONNECTED = "DISCONNECTED"
STATE_HANDSHAKING = "HANDSHAKING"
STATE_REGISTERED = "REGISTERED"
STATE_READY = "READY"


class MockExtension:
    """Simulates Chrome Extension responses for offline testing.

    Modes:
    - "reject":  Simulates connection refusal (e.g. bad token)
    - "timeout": Simulates no response (e.g. extension unreachable)
    - "error":   Simulates extension reporting an error
    - "ready":   Full working mock (default)

    The mock answers tab commands with synthetic tab IDs and URLs.
    """

    def __init__(self, mode: str = "ready"):
        self._mode = mode
        self._next_tab_id = 1

    def reject(self) -> bool:
        return self._mode == "reject"

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def _tab_from_command(self, cmd: Message) -> OwnedTab:
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        return OwnedTab(tab_id=tab_id, url=cmd.url or "about:blank",
                        title=f"Mock Tab {tab_id}")

    async def send_command(self, cmd: Message) -> Message:
        if self._mode == "timeout":
            await asyncio.sleep(3600)
            raise asyncio.TimeoutError("mock timeout")

        if self._mode == "error":
            return Message(
                type=MessageType.ERROR, command_id=cmd.command_id,
                success=False, error="mock extension error",
            )

        if self._mode == "reject":
            return Message(
                type=MessageType.RESULT, command_id=cmd.command_id,
                success=False, error="mock extension reject",
            )

        if cmd.type == MessageType.OPEN_TAB:
            tab = self._tab_from_command(cmd)
            return Message(
                type=MessageType.RESULT, command_id=cmd.command_id,
                success=True, tab_id=tab.tab_id, url=tab.url,
                title=tab.title,
            )

        if cmd.type == MessageType.CLOSE_TAB:
            return Message(
                type=MessageType.RESULT, command_id=cmd.command_id,
                success=True, tab_id=cmd.tab_id,
            )

        if cmd.type == MessageType.FOCUS_TAB:
            return Message(
                type=MessageType.RESULT, command_id=cmd.command_id,
                success=True, tab_id=cmd.tab_id,
            )

        if cmd.type == MessageType.NAVIGATE_TAB:
            return Message(
                type=MessageType.RESULT, command_id=cmd.command_id,
                success=True, tab_id=cmd.tab_id, url=cmd.url,
                title=f"Navigated Tab {cmd.tab_id}",
            )

        if cmd.type == MessageType.LIST_TABS:
            return Message(
                type=MessageType.RESULT, command_id=cmd.command_id,
                success=True, tabs=[
                    {"tab_id": 1, "url": "https://example.com",
                     "title": "Example"},
                ],
            )

        if cmd.type == MessageType.EXECUTE_SCRIPT:
            return Message(
                type=MessageType.RESULT, command_id=cmd.command_id,
                success=True, tab_id=cmd.tab_id,
                message=f"mock: script executed on tab {cmd.tab_id}",
            )

        if cmd.type == MessageType.PING:
            return Message(type=MessageType.PONG)

        return Message(
            type=MessageType.RESULT, command_id=cmd.command_id,
            success=False, error=f"mock: unknown type {cmd.type}",
        )


# ── Connector ────────────────────────────────────────────────────────


class Connector:
    """Browser Connector - WebSocket server + command dispatch.

    Two operation modes:
    - **Live** (default): Starts a WebSocket server in background thread,
      waits for Chrome Extension connection, proxies commands.
    - **Mock** (testing): Uses MockExtension internally - no WebSocket
      server, pure Python simulation.
    """

    def __init__(self, *, mock: bool = False, mock_mode: str = "ready", port: int = 9877):
        self._registry = TabRegistry()
        self._token: str = secrets.token_hex(32)
        self._extension: Optional[Any] = None
        self._ws_server: Optional[Any] = None
        self._lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future] = {}
        self._close_tab_command_ids: set[str] = set()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._port = port
        self._extension_state = STATE_DISCONNECTED

        if mock:
            self._mock = MockExtension(mode=mock_mode)
        else:
            self._mock = None

    def _log_browser_trace(self, command_id: str, command: str, success: str, payload: Any) -> None:
        import datetime
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        payload_str = str(payload)
        logger.info(
            f"[BROWSER_TRACE]\n"
            f"command_id={command_id}\n"
            f"command={command}\n"
            f"timestamp={timestamp}\n"
            f"success={success}\n"
            f"payload={payload_str}"
        )

    @property
    def registry(self) -> TabRegistry:
        return self._registry

    @property
    def token(self) -> str:
        return self._token

    def is_connected(self) -> bool:
        """In mock mode, always connected. In live mode, checks extension.

        Self-healing (2026-08-12): a stale extension handle whose WebSocket
        already closed is cleared synchronously here, so callers never wait
        for the 30s liveness watchdog before a command fast-fails. This is
        the shared browser-path latency fix — every consumer (browser_goto,
        execute_capability, focus/close) checks is_connected() first.
        """
        if self._mock:
            return True
        if self._extension is None:
            return False
        self._clear_stale_extension()
        return self._extension is not None

    @property
    def state(self) -> str:
        """R9: current extension connection state."""
        return self._extension_state

    def _clear_stale_extension(self) -> None:
        """R9: drop a closed/stale extension handle so a fresh connection registers.

        MV3 service workers can die without a clean WS close. The liveness
        watchdog calls this periodically; otherwise a dead handle would keep
        is_connected() True and every command would hang until timeout.
        """
        ext = self._extension
        if ext is None:
            return
        ws_state = getattr(ext, "state", None)
        if ws_state is None:
            stale = not bool(getattr(ext, "open", True))
        else:
            stale = getattr(ws_state, "name", str(ws_state)) != "OPEN"
        if stale:
            logger.warning(
                "[CONNECTOR] stale extension handle cleared (ws_state=%s)",
                getattr(ws_state, "name", ws_state),
            )
            self._extension = None
            self._extension_state = STATE_DISCONNECTED

    # ── Public Async API ─────────────────────────────────────────────

    async def open_tab(self, url: str) -> TabResult:
        """Open a URL in a new tab. Returns owned tab info.

        Deduplication (P5):
        Before creating a new tab, check for an existing tab with the
        same domain.  If found, focus that tab instead of creating a
        duplicate.
        """
        # P5: Check for existing tab by domain
        parsed = urlparse(url)
        domain = parsed.hostname
        if domain:
            existing_matches = self._registry.find_by_domain(domain)
            if existing_matches:
                existing = existing_matches[0]
                logger.info("[BROWSER_DEDUP_HIT] target=%s tab_id=%s", url, existing.tab_id)
                # Navigate existing tab to requested URL instead of creating new
                command_id = new_command_id()
                msg = Message(type=MessageType.NAVIGATE_TAB, command_id=command_id,
                              tab_id=existing.tab_id, url=url)
                err = validate_command(msg)
                if err:
                    return TabResult(success=False, command_id=command_id,
                                     error=err)
                logger.info("[BROWSER_NAVIGATE_TAB] tab_id=%s url=%s", existing.tab_id, url)
                return await self._dispatch(msg)

        # P5 fallback: check ALL Chrome tabs (not just owned) for domain match
        if domain:
            try:
                all_tabs_res = await self.list_tabs()
                if all_tabs_res.success and all_tabs_res.tabs:
                    for existing in all_tabs_res.tabs:
                        try:
                            existing_host = (urlparse(existing.url).hostname or "").lower()
                        except Exception:
                            continue
                        target_host = domain.lower().strip().rstrip("/")
                        if (existing_host == target_host or
                            existing_host.endswith("." + target_host) or
                            target_host.endswith("." + existing_host)):
                            # Adopt this tab as owned and navigate
                            self._registry.add(existing)
                            logger.info("[BROWSER_DEDUP_REUSE] target=%s tab_id=%s host=%s",
                                        url, existing.tab_id, existing_host)
                            command_id = new_command_id()
                            msg = Message(type=MessageType.NAVIGATE_TAB,
                                          command_id=command_id,
                                          tab_id=existing.tab_id, url=url)
                            err = validate_command(msg)
                            if err:
                                return TabResult(success=False, command_id=command_id,
                                                 error=err)
                            logger.info("[BROWSER_NAVIGATE_TAB] tab_id=%s url=%s", existing.tab_id, url)
                            return await self._dispatch(msg)
            except Exception:
                logger.warning("[BROWSER_DEDUP_LIST_FAILED] target=%s", url, exc_info=True)

        logger.info("[BROWSER_DEDUP_NEW_TAB] target=%s", url)
        command_id = new_command_id()
        msg = Message(type=MessageType.OPEN_TAB, command_id=command_id,
                      url=url)
        err = validate_command(msg)
        if err:
            return TabResult(success=False, command_id=command_id,
                             error=err)
        return await self._dispatch(msg)

    async def _resolve_target_to_tab(self, target: str) -> Optional[OwnedTab]:
        # Try resolving by index first
        cleaned = target.strip()
        if cleaned.lower().startswith("tab "):
            cleaned = cleaned[4:].strip()
        try:
            val = int(cleaned)
            if 1 <= val <= 100:
                res = await self.list_tabs()
                if res.success and res.tabs and 1 <= val <= len(res.tabs):
                    matched_tab = res.tabs[val - 1]
                    if self._registry.is_owned(matched_tab.tab_id):
                        return self._registry.get(matched_tab.tab_id)
        except Exception:
            pass
        # Fallback to synchronous resolver
        tab = self._tab_from_target(target)
        if tab:
            return tab
        # Fallback: search ALL tabs (not just owned) via list_tabs
        try:
            res = await self.list_tabs()
            if res.success and res.tabs:
                target_norm = target.lower().replace(" ", "")
                for t in res.tabs:
                    if t.url and (target_norm in t.url.lower().replace(" ", "") or
                                  target_norm in t.title.lower().replace(" ", "")):
                        return t
        except Exception:
            pass
        return None

    async def close_tab(self, target: str) -> TabResult:
        """Close a tab by target (URL, domain, text, or tab_id string)."""
        command_id = new_command_id()
        self._log_browser_trace(command_id, "close_tab", "PENDING", f"command created for target: {target}")
        tab = await self._resolve_target_to_tab(target)
        if tab is None:
            self._log_browser_trace(command_id, "close_tab", "FAILURE", f"no owned tab matching: {target}")
            return TabResult(success=False, command_id=command_id,
                             error=f"no owned tab matching: {target}")

        self._close_tab_command_ids.add(command_id)
        msg = Message(type=MessageType.CLOSE_TAB, command_id=command_id,
                      tab_id=tab.tab_id)
        err = validate_command(msg)
        if err:
            self._close_tab_command_ids.discard(command_id)
            self._log_browser_trace(command_id, "close_tab", "FAILURE", f"validation failed: {err}")
            return TabResult(success=False, command_id=command_id,
                             error=err)
        return await self._dispatch(msg)

    async def focus_tab(self, target: str) -> TabResult:
        """Focus (activate) a tab by target."""
        command_id = new_command_id()
        tab = await self._resolve_target_to_tab(target)
        if tab is None:
            return TabResult(success=False, command_id=command_id,
                             error=f"no owned tab matching: {target}")

        msg = Message(type=MessageType.FOCUS_TAB, command_id=command_id,
                      tab_id=tab.tab_id)
        err = validate_command(msg)
        if err:
            return TabResult(success=False, command_id=command_id,
                             error=err)
        return await self._dispatch(msg)

    async def list_tabs(self) -> TabResult:
        """List all owned tabs."""
        command_id = new_command_id()
        msg = Message(type=MessageType.LIST_TABS, command_id=command_id)
        return await self._dispatch(msg)

    async def execute_script(self, tab_id: int, script: str, args: Optional[list] = None) -> TabResult:
        """Execute JavaScript in a browser tab.

        Args:
            tab_id: Chrome tab ID to inject into.
            script: JavaScript code to execute (IIFE returning a value).
            args: Optional arguments to pass to the script.

        Returns:
            TabResult with message containing the script return value.
        """
        command_id = new_command_id()
        msg = Message(type=MessageType.EXECUTE_SCRIPT, command_id=command_id,
                       tab_id=tab_id, script=script, args=args)
        err = validate_command(msg)
        if err:
            return TabResult(success=False, command_id=command_id, error=err)
        logger.info("[BROWSER_EXECUTE_SCRIPT] tab_id=%s", tab_id)
        return await self._dispatch(msg)

    async def _resolve_media_tab(self, domain_hint: str = "") -> Optional[OwnedTab]:
        """Resolve the best media tab for media control actions.

        Resolution order:
        1. Domain hint: find tab matching the specified domain.
        2. Audible tabs: find any tab currently producing audio.
        3. Owned media tabs: find KIO-opened tabs on known media domains.
        4. All media tabs: search ALL browser tabs for media domains.
        5. Fail: return None.
        """
        # 1. Domain hint
        if domain_hint:
            owned = self._registry.find_by_domain(domain_hint)
            if owned:
                return owned[0]
            try:
                res = await self.list_tabs()
                if res.success and res.tabs:
                    for t in res.tabs:
                        if t.url and domain_hint.lower() in t.url.lower():
                            return t
            except Exception:
                pass
            return None

        # 2. Audible tabs (requires extension enhancement — audible field)
        # RC2: ONLY media-domain tabs may be targeted. An active/audible
        # non-media tab (e.g. Telegram Web) must never become the transport
        # target — the extension lacks host permissions for it and KIO would
        # report "Cannot access contents".
        try:
            res = await self.list_tabs()
            if res.success and res.tabs:
                audible_tabs = [
                    t for t in res.tabs
                    if getattr(t, "audible", False) and self._is_media_host(t.url or "")
                ]
                if audible_tabs:
                    # Prefer active tab among audible ones
                    for t in audible_tabs:
                        if getattr(t, "active", False):
                            return t
                    # Prefer owned among audible ones
                    for t in audible_tabs:
                        if t.is_owned:
                            return t
                    # Return first audible
                    return audible_tabs[0]
        except Exception:
            pass

        # 3. Owned media tabs
        for domain in _MEDIA_DOMAINS:
            matches = self._registry.find_by_domain(domain)
            if matches:
                return matches[0]

        # 4. All media tabs (via list_tabs)
        try:
            res = await self.list_tabs()
            if res.success and res.tabs:
                for t in res.tabs:
                    if t.url and self._is_media_host(t.url):
                        return t
        except Exception:
            pass

        return None

    @staticmethod
    def _is_media_host(url: str) -> bool:
        """True when the URL's host is a known media domain."""
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        if not host:
            return False
        return any(host == d or host.endswith("." + d) for d in _MEDIA_DOMAINS)

    # ── Lifecycle ────────────────────────────────────────────────────

    def start_background(self) -> None:
        """Start the WebSocket server in a background daemon thread."""
        if self._mock or self._started:
            logger.info("[INSTRUMENT] start_background skipped (mock=%s _started=%s)", self._mock, self._started)
            return
        self._started = True
        _install_thread_excepthook()
        self._loop = asyncio.new_event_loop()
        logger.info("[INSTRUMENT] event loop created id=%s thread=%s", id(self._loop), threading.current_thread().name)
        self._thread = threading.Thread(
            target=self._run_event_loop, daemon=True,
            name=_CONNECTOR_THREAD_NAME,
        )
        logger.info("[INSTRUMENT] about to start thread target=%s daemon=%s",
                    _CONNECTOR_THREAD_NAME, self._thread.daemon)
        self._thread.start()
        logger.info("[INSTRUMENT] thread started ident=%s alive=%s daemon=%s",
                    self._thread.ident, self._thread.is_alive(), self._thread.daemon)

    def _run_event_loop(self) -> None:
        """Run the WebSocket server event loop (blocking, daemon thread)."""
        logger.info("[INSTRUMENT] _run_event_loop ENTER thread=%s thread_ident=%s",
                    threading.current_thread().name, threading.current_thread().ident)
        asyncio.set_event_loop(self._loop)
        self._loop.set_exception_handler(self._asyncio_exception_handler)
        try:
            logger.info("[INSTRUMENT] loop.run_until_complete ENTER loop_id=%s",
                        id(self._loop))
            self._loop.run_until_complete(self._serve_forever())
            logger.info("[INSTRUMENT] loop.run_until_complete EXIT (serve_forever returned)")
        except asyncio.CancelledError:
            logger.warning("[INSTRUMENT] event loop cancelled: CancelledError")
        except Exception:
            logger.exception("[INSTRUMENT] event loop crashed (Exception)")
        except BaseException as e:
            logger.warning("[INSTRUMENT] event loop interrupted: %s %s", type(e).__name__, e)
            raise
        else:
            logger.info("[INSTRUMENT] _run_event_loop completed without exception")
        finally:
            logger.info("[INSTRUMENT] _run_event_loop EXIT thread=%s loop_closed=%s",
                        threading.current_thread().name,
                        self._loop.is_closed() if self._loop else "N/A")

    async def _serve_forever(self) -> None:
        """Run the websockets server forever."""
        logger.info("[INSTRUMENT] _serve_forever ENTER thread=%s", threading.current_thread().name)
        logger.info("[CONNECTOR] starting WebSocket on %s:%d", _WS_HOST, self._port)
        try:
            self._ws_server = await serve(
                self._handle_ws, _WS_HOST, self._port,
            )
            logger.info("[INSTRUMENT] serve() completed, server=%s", self._ws_server)
        except Exception:
            logger.exception("[CONNECTOR] WebSocket server failed to start")
            raise

        # ── Liveness watchdog ─────────────────────────────────────
        async def _liveness_watchdog():
            beat = 0
            while True:
                await asyncio.sleep(30)
                beat += 1
                self._clear_stale_extension()
                logger.info("[INSTRUMENT] heartbeat=%d thread=%s loop_running=%s ws_server=%s",
                            beat, threading.current_thread().name,
                            self._loop.is_running() if self._loop else "N/A",
                            self._ws_server is not None)

        watchdog_task = asyncio.create_task(_liveness_watchdog())
        logger.info("[INSTRUMENT] _serve_forever await asyncio.Future() — blocking forever")
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            watchdog_task.cancel()
            logger.warning("[INSTRUMENT] _serve_forever asyncio.Future cancelled")
            raise
        finally:
            logger.info("[INSTRUMENT] _serve_forever EXIT thread=%s", threading.current_thread().name)

    def _asyncio_exception_handler(
        self, loop: asyncio.AbstractEventLoop, context: dict,
    ) -> None:
        """Handle asyncio internal errors (task crashes, orphaned futures)."""
        msg = context.get("message", "unknown")
        exc = context.get("exception", None)
        future = context.get("future", None)
        logger.error("[CONNECTOR] asyncio exception: %s", msg)
        if exc:
            logger.error(
                "[CONNECTOR] asyncio exception detail",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
        if future is not None:
            logger.error("[CONNECTOR] asyncio exception future: %s", future)

    async def stop(self) -> None:
        """Stop the connector. Clear all pending futures."""
        logger.info("[INSTRUMENT] stop() ENTER thread=%s _started=%s",
                    threading.current_thread().name, self._started)
        logger.info("[INSTRUMENT] stop() pre-close: thread_alive=%s loop_running=%s ws_server=%s",
                    self._thread.is_alive() if self._thread else "N/A",
                    self._loop.is_running() if self._loop else "N/A",
                    self._ws_server is not None)
        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()
            self._ws_server = None
        if self._loop and self._loop.is_running():
            logger.info("[INSTRUMENT] stop() calling loop.stop_threadsafe")
            self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("[INSTRUMENT] stop() pending futures to cancel: %d", len(self._pending))
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        self._extension = None
        self._extension_state = STATE_DISCONNECTED
        logger.info("[INSTRUMENT] stop() post-cleanup: thread_alive=%s loop_closed=%s",
                    self._thread.is_alive() if self._thread else "N/A",
                    self._loop.is_closed() if self._loop else "N/A")
        logger.info("[CONNECTOR] stopped")

    # ── Internal ─────────────────────────────────────────────────────

    async def _dispatch(self, cmd: Message) -> TabResult:
        """Dispatch a command and return the result."""
        command_id = cmd.command_id or new_command_id()
        cmd.command_id = command_id

        # Mock mode - short-circuit
        if self._mock:
            resp = await self._mock.send_command(cmd)
            return self._process_response(resp, cmd)

        # Live mode - dispatch to background WS thread
        if self._extension is None:
            return TabResult(
                success=False, command_id=command_id,
                error="no extension connected",
            )

        loop = self._loop
        if loop is None or not loop.is_running():
            return TabResult(
                success=False, command_id=command_id,
                error="WebSocket server not running",
            )

        future = asyncio.run_coroutine_threadsafe(
            self._send_and_wait(cmd), loop,
        )
        try:
            resp = await asyncio.wrap_future(future)
            return self._process_response(resp, cmd)
        except asyncio.TimeoutError:
            return TabResult(
                success=False, command_id=command_id,
                error="extension response timeout",
            )
        except Exception as e:
            return TabResult(
                success=False, command_id=command_id,
                error=f"extension error: {e}",
            )

    async def _send_and_wait(self, cmd: Message) -> Message:
        """Send command on the WS event loop and wait for response (runs on WS loop)."""
        command_id = cmd.command_id
        fut = asyncio.get_running_loop().create_future()
        self._pending[command_id] = fut

        ext = self._extension
        if ext is None:
            return Message(
                type=MessageType.RESULT, command_id=command_id,
                success=False, error="extension disconnected",
            )

        try:
            if cmd.type == MessageType.CLOSE_TAB:
                self._log_browser_trace(command_id, "close_tab", "PENDING", f"command sent: {serialize(cmd)}")
            # Latency fast-fail (2026-08-12): a stale extension handle (WS
            # closed but not yet reaped by the 30s liveness watchdog) would
            # otherwise make every browser command hang for the full 30s
            # `wait_for` timeout. Detect a closed handle synchronously and
            # fail immediately — a dead extension must never cost 30 seconds
            # per command.
            ws_state = getattr(ext, "state", None)
            if ws_state is not None:
                if getattr(ws_state, "name", str(ws_state)) != "OPEN":
                    self._pending.pop(command_id, None)
                    return Message(
                        type=MessageType.RESULT, command_id=command_id,
                        success=False, error="extension not connected",
                    )
            elif not bool(getattr(ext, "open", True)):
                self._pending.pop(command_id, None)
                return Message(
                    type=MessageType.RESULT, command_id=command_id,
                    success=False, error="extension not connected",
                )
            await ext.send(serialize(cmd))
            resp = await asyncio.wait_for(fut, timeout=30.0)
            return resp
        except asyncio.TimeoutError:
            self._pending.pop(command_id, None)
            return Message(
                type=MessageType.RESULT, command_id=command_id,
                success=False, error="extension response timeout",
            )
        except Exception as e:
            self._pending.pop(command_id, None)
            return Message(
                type=MessageType.RESULT, command_id=command_id,
                success=False, error=f"extension error: {e}",
            )

    def _process_response(self, resp: Message, cmd: Optional[Message] = None) -> TabResult:
        """Convert an extension response Message to TabResult.
        
        Registry is only updated after a successful extension response.
        """
        ok = resp.success if resp.success is not None else False
        result = TabResult(
            success=ok,
            command_id=resp.command_id or "",
            error=resp.error or "",
            message=resp.message or "",
        )

        if ok and resp.tab_id is not None:
            tab = OwnedTab(
                tab_id=resp.tab_id,
                url=resp.url or "about:blank",
                title=resp.title or "",
                window_id=resp.window_id or 0,
            )
            result.tab = tab
            if resp.type == MessageType.RESULT and cmd:
                if cmd.type == MessageType.OPEN_TAB and resp.url:
                    self._registry.add(tab)
                elif cmd.type == MessageType.CLOSE_TAB:
                    self._registry.remove(resp.tab_id)
                elif cmd.type == MessageType.NAVIGATE_TAB and resp.url:
                    self._registry.update_url(resp.tab_id, resp.url, resp.title or "")
                elif cmd.type == MessageType.EXECUTE_SCRIPT:
                    pass  # No registry state change

        if ok and resp.tabs is not None:
            tabs = []
            for t_dict in resp.tabs:
                tab = OwnedTab.from_dict(t_dict)
                # Check ownership against local registry
                tab.is_owned = self._registry.is_owned(tab.tab_id)
                tabs.append(tab)
            result.tabs = tabs

        return result

    def _tab_from_target(self, target: str) -> Optional[OwnedTab]:
        """Parse target: try as tab_id integer, then resolve.

        Accepts:
        - Integer string: "123" → tab_id lookup
        - URL: "https://example.com" → exact URL match
        - Domain: "youtube.com" → domain match
        - Text: "my doc" → text match
        """
        cleaned = target.strip()
        if cleaned.lower().startswith("tab "):
            cleaned = cleaned[4:].strip()
        try:
            tab_id = int(cleaned)
            tab = self._registry.get(tab_id)
            if tab:
                return tab
        except ValueError:
            pass
        return self._registry.resolve(cleaned)

    # ── WebSocket Connection Handler ─────────────────────────────────

    async def _handle_ws(self, websocket) -> None:
        """Handle a WebSocket connection from the Chrome extension (RFC 6455)."""
        remote = websocket.remote_address
        logger.info("[CONNECTOR] WebSocket connection from %s:%s", remote[0], remote[1])
        self._extension_state = STATE_HANDSHAKING

        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            msg = deserialize(raw)
        except asyncio.TimeoutError:
            logger.warning("[CONNECTOR] timeout waiting for connect from %s", remote)
            return
        except Exception as e:
            logger.warning("[CONNECTOR] invalid connect message from %s: %s", remote, e)
            return

        if msg.type != MessageType.CONNECT:
            await websocket.send(serialize(Message(
                type=MessageType.ERROR, error=f"expected 'connect', got '{msg.type}'",
            )))
            return

        token = msg.token or ""

        # Bootstrap flow: extension connects without token → send set_token
        if not token:
            logger.info("[CONNECTOR] bootstrap connection from %s, sending token", remote)
            await websocket.send(serialize(Message(
                type="set_token", token=self._token,
            )))
            return

        # Validate token
        if token != self._token:
            logger.warning("[CONNECTOR] auth FAILED from %s - token mismatch, sending updated token", remote)
            await websocket.send(serialize(Message(
                type="set_token", token=self._token,
            )))
            return

        # RC1: reject stale/unknown extension builds at registration.
        # The current background.js sends build=<BUILD_VERSION> in the
        # connect message. A missing or mismatched build means Chrome is
        # still executing an old service worker — registering it would
        # reproduce every "non-state payload" / false-failure symptom.
        # Rejecting it lets the current-build SW (which reconnects on its
        # own alarm cadence) claim the slot instead.
        ext_build = (msg.build or "").strip()
        if ext_build != _EXPECTED_EXTENSION_BUILD:
            logger.warning(
                "[CONNECTOR] auth REJECTED stale build from %s "
                "(loaded=%r expected=%r) - keeping slot free for current build",
                remote, ext_build or None, _EXPECTED_EXTENSION_BUILD,
            )
            await websocket.send(serialize(Message(
                type=MessageType.ERROR,
                error=(
                    f"stale extension build (loaded={ext_build or 'unknown'}, "
                    f"expected={_EXPECTED_EXTENSION_BUILD}) - reload the KIO Chrome extension"
                ),
            )))
            return

        # Auth success
        logger.info("[CONNECTOR] auth SUCCESS from %s", remote)
        await websocket.send(serialize(Message(
            type=MessageType.CONNECTED, success=True,
        )))
        self._extension = websocket
        self._extension_state = STATE_REGISTERED
        logger.info("[CONNECTOR] extension registered: remote=%s", remote)
        self._extension_state = STATE_READY

        try:
            async for raw in websocket:
                try:
                    resp = deserialize(raw)
                except ValueError:
                    continue

                # Response to a pending command
                if resp.command_id and resp.command_id in self._pending:
                    if resp.command_id in self._close_tab_command_ids:
                        self._close_tab_command_ids.discard(resp.command_id)
                        self._log_browser_trace(resp.command_id, "close_tab", "SUCCESS" if resp.success else "FAILURE", f"response received: {raw}")
                    fut = self._pending.pop(resp.command_id)
                    if not fut.done():
                        fut.set_result(resp)

                # Unsolicited messages from extension
                elif resp.type == "pong":
                    pass
                elif resp.type == "ping":
                    await websocket.send(serialize(Message(type="pong")))
                elif resp.type == "tab_closed":
                    if resp.tab_id is not None:
                        self._registry.remove(resp.tab_id)
                elif resp.type == "tab_updated":
                    if resp.tab_id is not None:
                        self._registry.update_url(
                            resp.tab_id, resp.url or "", resp.title or "",
                        )
        except websockets.exceptions.ConnectionClosed as cc:
            logger.info("[INSTRUMENT] websocket closed: code=%s reason=%s", cc.code, cc.reason)
        except Exception:
            logger.exception("[INSTRUMENT] websocket handler crashed")
        finally:
            logger.info("[INSTRUMENT] disconnect: remote=%s self._started=%s loop_running=%s thread_alive=%s",
                        remote, self._started,
                        self._loop.is_running() if self._loop else "N/A",
                        self._thread.is_alive() if self._thread else "N/A")
            if self._extension is websocket:
                logger.info("[CONNECTOR] extension disconnected: remote=%s", remote)
                self._extension = None
                self._extension_state = STATE_DISCONNECTED
