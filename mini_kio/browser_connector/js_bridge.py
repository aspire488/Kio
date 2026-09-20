"""
js_bridge.py — WS server for the KIO JS Bridge extension.

Runs a WebSocket server on port 9878.  The extension connects as a client.
Provides execute_js(tab_id, code) → result dict.
"""

import asyncio
import json
import logging
import threading
import uuid
from typing import Optional

try:
    import websockets
except ImportError:
    websockets = None  # type: ignore[assignment]

logger = logging.getLogger("kio.js_bridge")

_JS_BRIDGE_PORT = 9878
_JS_BRIDGE_TOKEN = "kio-js-bridge-v1"
_TIMEOUT = 30.0

_instance: Optional["JSBridge"] = None
_lock = threading.Lock()


class JSBridge:
    """WS server that the JS Bridge extension connects to."""

    def __init__(self, port: int = _JS_BRIDGE_PORT):
        self._port = port
        self._ws = None
        self._pending: dict[str, asyncio.Future] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._ready = threading.Event()

    def start_background(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="kio-jsbridge"
        )
        self._thread.start()
        self._ready.wait(timeout=10)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._ready.set()
        loop.run_until_complete(self._serve_forever())

    async def _keepalive_pinger(self, ws) -> None:
        """Send periodic pings to keep the WebSocket alive and prevent MV3 idle kill."""
        try:
            while True:
                await asyncio.sleep(20)
                if ws.closed:
                    break
                await ws.send(json.dumps({"type": "ping"}))
        except Exception:
            pass

    async def _handler(self, ws) -> None:
        """Handle one WebSocket connection from the extension."""
        logger.info("[JS-BRIDGE] extension connected")
        pinger_task = None
        try:
            pinger_task = asyncio.ensure_future(self._keepalive_pinger(ws))
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_type = msg.get("type", "")

                # Auth
                if msg_type == "connect":
                    token = msg.get("token", "")
                    if token != _JS_BRIDGE_TOKEN:
                        await ws.send(json.dumps({
                            "type": "set_token", "token": _JS_BRIDGE_TOKEN
                        }))
                        continue
                    self._ws = ws
                    await ws.send(json.dumps({
                        "type": "connected", "success": True
                    }))
                    logger.info("[JS-BRIDGE] auth OK")
                    continue

                # Response to pending command
                cid = msg.get("command_id", "")
                if cid and cid in self._pending:
                    fut = self._pending.pop(cid)
                    if not fut.done():
                        fut.set_result(msg)
                    continue

                if msg_type == "pong":
                    continue

        except Exception as exc:
            logger.warning("[JS-BRIDGE] handler error: %s", exc)
        finally:
            if pinger_task and not pinger_task.done():
                pinger_task.cancel()
            self._ws = None
            logger.info("[JS-BRIDGE] extension disconnected")

    async def _serve_forever(self) -> None:
        if websockets is None:
            logger.error("[JS-BRIDGE] websockets not installed")
            return
        logger.info("[JS-BRIDGE] starting server on port %d", self._port)
        async with websockets.serve(self._handler, "127.0.0.1", self._port):
            await asyncio.Future()

    async def _send(self, msg: dict) -> dict:
        if not self._ws:
            return {"success": False, "error": "not connected"}
        cid = uuid.uuid4().hex[:12]
        msg["command_id"] = cid
        fut = self._loop.create_future()
        self._pending[cid] = fut
        await self._ws.send(json.dumps(msg))
        try:
            return await asyncio.wait_for(fut, timeout=_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(cid, None)
            return {"success": False, "error": "timeout"}

    def execute_js(self, tab_id: int, code: str) -> dict:
        """Run arbitrary JS in tab_id, return dict with success/message/error."""
        if not self._loop or not self._started:
            return {"success": False, "error": "bridge not started"}
        coro = self._send({
            "type": "execute_js",
            "tab_id": tab_id,
            "args": [code],
        })
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=_TIMEOUT + 5)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def is_connected(self) -> bool:
        return self._ws is not None


def get_js_bridge() -> JSBridge:
    """Singleton accessor.  Starts background server on first call."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = JSBridge()
                _instance.start_background()
    return _instance
