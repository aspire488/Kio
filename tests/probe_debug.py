"""Debug probe - intercept raw response."""
import os, asyncio, time, json, uuid
os.environ.pop("KIO_TEST_MODE", None)
from mini_kio.browser_connector.connector import Connector
from mini_kio.browser_connector.protocol import Message, MessageType, serialize
from mini_kio.core.async_utils import safe_run_async

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

print("Extension connected")

# Monkeypatch _process_response to see raw resp
_orig = raw._process_response
def debug_process(resp, cmd=None):
    if cmd and cmd.script == "run_js":
        print("  RAW RESP: success={} message_repr={} error={}".format(
            resp.success, repr(resp.message), resp.error))
        print("  RAW RESP dict:", {k: v for k, v in resp.__dict__.items() if v is not None})
    return _orig(resp, cmd)
raw._process_response = debug_process

# Get first tab
res = asyncio.run(raw.list_tabs())
if not res.tabs:
    print("No tabs")
    exit(1)

tab_id = res.tabs[0].tab_id
print("Tab:", tab_id, res.tabs[0].url[:60])

# Test run_js
js = "(function(){ return document.title; })()"
r1 = safe_run_async(raw.execute_script(tab_id, "run_js", args=[js]))
print("FINAL: success={} message_repr={}".format(r1.success, repr(r1.message)))
