"""Probe extension state after reload."""
import os, asyncio, time
os.environ.pop("KIO_TEST_MODE", None)
from mini_kio.browser_connector.connector import Connector
from mini_kio.core.state_verification import VerifiedConnector
from mini_kio.core.async_utils import safe_run_async

raw = Connector(port=9877)
raw.start_background()
time.sleep(3)
conn = VerifiedConnector(raw)

for i in range(15):
    if raw._extension is not None:
        break
    time.sleep(2)

if not conn.is_connected():
    print("Extension not connected")
    exit(1)

print("Connected!")
res = asyncio.run(conn.list_tabs())
print("Tabs:", len(res.tabs) if res.tabs else 0)

if res.tabs:
    tab_id = res.tabs[0].tab_id
    print("Tab:", tab_id, res.tabs[0].url[:60])
    
    # Test existing script to verify extension works
    r0 = safe_run_async(conn.execute_script(tab_id, "get_build_info"))
    print("get_build_info: success={} message={}".format(r0.success, r0.message))
    
    # Test run_js
    js = "(function(){ return 'hello from run_js'; })()"
    r1 = safe_run_async(conn.execute_script(tab_id, "run_js", args=[js]))
    print("run_js: success={} message={} error={}".format(r1.success, r1.message, r1.error))
    
    # Try a different approach: send raw JS directly via the extension protocol
    # by setting msg.script to the actual JS code (old behavior)
    js2 = "(function(){ return document.title; })()"
    r2 = safe_run_async(conn.execute_script(tab_id, js2))
    print("raw_js: success={} message={} error={}".format(r2.success, r2.message, r2.error))
