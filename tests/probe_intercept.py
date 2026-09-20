"""Intercept raw WS messages to see what the extension sends."""
import os, asyncio, time, json, uuid
os.environ.pop("KIO_TEST_MODE", None)
from mini_kio.browser_connector.connector import Connector
from mini_kio.browser_connector.protocol import Message, MessageType, serialize

raw = Connector(port=9877)
raw.start_background()
time.sleep(4)

for i in range(20):
    if raw._extension is not None:
        break
    time.sleep(1)

if raw._extension is None:
    print("Extension not connected")
    exit(1)

ws = raw._extension
print("Extension connected")

# Monkey-patch _handle_ws to intercept raw messages
orig_handle = raw._handle_ws.__func__ if hasattr(raw._handle_ws, '__func__') else None

# Instead, let's monkeypatch deserialize to see raw messages
import mini_kio.browser_connector.protocol as proto
orig_deserialize = proto.deserialize
def debug_deserialize(raw_str):
    msg = orig_deserialize(raw_str)
    if hasattr(msg, 'script') and msg.script:
        print("  [RECV RAW]", raw_str[:500])
    return msg
proto.deserialize = debug_deserialize

# Get tabs
cid = uuid.uuid4().hex[:12]
msg = Message(type=MessageType.LIST_TABS, command_id=cid)
fut = asyncio.get_event_loop().create_future()
raw._pending[cid] = fut
await_coro = ws.send(serialize(msg))
loop = asyncio.new_event_loop()
loop.run_until_complete(await_coro)
resp = loop.run_until_complete(asyncio.wait_for(fut, timeout=10))
loop.close()

if resp.tabs:
    tab_id = resp.tabs[0].get("tab_id")
    print("Tab:", tab_id, resp.tabs[0].get("url", "")[:60])

    # Now send run_js
    print("\nSending run_js...")
    cid2 = uuid.uuid4().hex[:12]
    js = "(function(){ return 'hello_test_123'; })()"
    msg2 = Message(type=MessageType.EXECUTE_SCRIPT, command_id=cid2,
                   tab_id=tab_id, script="run_js", args=[js])
    fut2 = asyncio.get_event_loop().create_future()
    raw._pending[cid2] = fut2
    loop2 = asyncio.new_event_loop()
    loop2.run_until_complete(ws.send(serialize(msg2)))
    resp2 = loop2.run_until_complete(asyncio.wait_for(fut2, timeout=30))
    loop2.close()

    print("Response:", resp2.__dict__)
