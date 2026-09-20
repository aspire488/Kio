"""Raw WS probe to see extension response format."""
import os, asyncio, time, json, uuid
os.environ.pop("KIO_TEST_MODE", None)
from mini_kio.browser_connector.connector import Connector
from mini_kio.core.async_utils import safe_run_async
from mini_kio.browser_connector.protocol import Message, MessageType, serialize

raw = Connector(port=9877)
raw.start_background()
time.sleep(4)

# Wait for extension
for i in range(20):
    if raw._extension is not None:
        break
    time.sleep(1)

if raw._extension is None:
    print("Extension not connected")
    exit(1)

print("Extension connected")

# Manually send commands and capture raw WS responses
async def raw_test(ws, tab_id, script, args=None):
    cid = uuid.uuid4().hex[:12]
    msg = Message(type=MessageType.EXECUTE_SCRIPT, command_id=cid,
                  tab_id=tab_id, script=script, args=args or [])
    fut = asyncio.get_event_loop().create_future()
    raw._pending[cid] = fut
    await ws.send(serialize(msg))
    resp = await asyncio.wait_for(fut, timeout=30)
    # Show the raw Message fields
    print("  command_id:", resp.command_id)
    print("  success:", resp.success)
    print("  message repr:", repr(resp.message))
    print("  error:", resp.error)
    print("  All non-None fields:", {k: v for k, v in resp.__dict__.items() if v is not None and v != "" and v != False})
    return resp

async def main():
    ws = raw._extension
    res = await ws._dispatch(Message(type=MessageType.LIST_TABS, command_id=uuid.uuid4().hex[:12]))
    # Actually use the raw ws
    tab_id = None
    cid = uuid.uuid4().hex[:12]
    msg = Message(type=MessageType.LIST_TABS, command_id=cid)
    fut = asyncio.get_event_loop().create_future()
    raw._pending[cid] = fut
    await ws.send(serialize(msg))
    list_resp = await asyncio.wait_for(fut, timeout=30)
    if list_resp.tabs:
        tab_id = list_resp.tabs[0].get("tab_id")
        print("First tab:", tab_id, list_resp.tabs[0].get("url", "")[:60])
    
    if not tab_id:
        print("No tabs")
        return
    
    # Test 1: existing script
    print("\n--- get_build_info ---")
    await raw_test(ws, tab_id, "get_build_info")
    
    # Test 2: run_js with title
    print("\n--- run_js: document.title ---")
    await raw_test(ws, tab_id, "run_js", args=["(function(){ return document.title; })()"])
    
    # Test 3: run_js with simple string
    print("\n--- run_js: literal string ---")
    await raw_test(ws, tab_id, "run_js", args=["(function(){ return 'hello world'; })()"])
    
    # Test 4: run_js with number
    print("\n--- run_js: number ---")
    await raw_test(ws, tab_id, "run_js", args=["(function(){ return 42; })()"])

asyncio.run(main())
