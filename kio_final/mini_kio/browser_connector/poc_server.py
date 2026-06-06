"""
poc_server.py - Browser Connector V1 Proof of Concept

Validates that a Python WebSocket server can communicate with a Chrome
Extension over localhost.

Protocol:
  Client → Server: {"type": "connect", "token": "<token>"}
  Server → Client: {"type": "connected"}
  Client → Server: {"type": "ping"}
  Server → Client: {"type": "pong"}

Usage:
    python poc_server.py --token demo123
"""

import argparse
import asyncio
import json
import logging

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("poc_server")

HOST = "127.0.0.1"
PORT = 9877


async def handler(websocket):
    remote = websocket.remote_address
    logger.info("client connected from %s:%s", remote[0], remote[1])

    try:
        raw = await websocket.recv()
        msg = json.loads(raw)
    except Exception as exc:
        logger.error("invalid connect message: %s", exc)
        await websocket.close(1002, "invalid connect message")
        return

    if msg.get("type") != "connect":
        logger.warning("expected 'connect', got '%s'", msg.get("type"))
        await websocket.close(1002, "first message must be 'connect'")
        return

    token = msg.get("token", "")
    if token != CONNECTION_TOKEN:
        logger.warning("auth FAILED - token mismatch")
        await websocket.close(4001, "invalid token")
        return

    logger.info("auth SUCCESS - token accepted")
    await websocket.send(json.dumps({"type": "connected"}))

    async for raw in websocket:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("invalid JSON received, ignoring")
            continue

        msg_type = msg.get("type")
        if msg_type == "ping":
            logger.info("ping received")
            await websocket.send(json.dumps({"type": "pong"}))
            logger.info("pong sent")
        elif msg_type == "pong":
            logger.info("pong received (extension heartbeat)")
        else:
            logger.warning("unknown message type: %s", msg_type)

    logger.info("client disconnected")


async def main():
    global CONNECTION_TOKEN
    parser = argparse.ArgumentParser(description="KIO Browser Connector POC")
    parser.add_argument("--token", default=None, help="Connection token (auto-generated if omitted)")
    args = parser.parse_args()

    CONNECTION_TOKEN = args.token or __import__("uuid").uuid4().hex[:16]
    logger.info("=" * 50)
    logger.info("KIO Browser Connector POC Server")
    logger.info("Bind:  %s:%s", HOST, PORT)
    logger.info("Token: %s", CONNECTION_TOKEN)
    logger.info("=" * 50)

    async with websockets.serve(handler, HOST, PORT):
        logger.info("Server started. Waiting for extension connection...")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
