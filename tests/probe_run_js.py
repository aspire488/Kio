"""Quick probe: does run_js return a value after sync fix?"""
import os, asyncio, time, uuid
os.environ.pop("KIO_TEST_MODE", None)
from mini_kio.browser_connector.connector import Connector
from mini_kio.browser_connector.protocol import Message, MessageType, serialize
from mini_kio.core.async_utils import safe_run_async

raw = Connector(port=9877)
raw.start_background()
time.sleep(5)
for i in range(15):
    if raw._extension: break
    time.sleep(1)
if not raw._extension:
    print("NOT CONNECTED"); exit(1)

res = safe_run_async(raw.list_tabs())
tab_id = res.tabs[0].tab_id
print("Tab:", tab_id)

# Test 1: run_js with document.title
r1 = safe_run_async(raw.execute_script(tab_id, "run_js", args=["document.title"]))
print("run_js title: success={} message={}".format(r1.success, repr(r1.message)))

# Test 2: run_js returning a number
r2 = safe_run_async(raw.execute_script(tab_id, "run_js", args=["document.querySelectorAll('p').length"]))
print("run_js count: success={} message={}".format(r2.success, repr(r2.message)))

# Test 3: get_build_info (known working)
r3 = safe_run_async(raw.execute_script(tab_id, "get_build_info", args=[]))
print("get_build_info: success={} message={}".format(r3.success, repr(r3.message)))
