"""Test the JS Bridge extension (port 9878)."""
import os, time
os.environ.pop("KIO_TEST_MODE", None)
from mini_kio.browser_connector.js_bridge import get_js_bridge

bridge = get_js_bridge()
print("Waiting for bridge to connect...")
time.sleep(5)
for i in range(15):
    if bridge.is_connected():
        break
    time.sleep(1)

if not bridge.is_connected():
    print("JS Bridge NOT CONNECTED on port 9878")
    exit(1)

print("JS Bridge CONNECTED")

# Get a tab from the main connector
from mini_kio.browser_connector.connector import Connector
from mini_kio.core.async_utils import safe_run_async
main = Connector(port=9877)
main.start_background()
time.sleep(4)
for i in range(15):
    if main._extension:
        break
    time.sleep(1)

if not main._extension:
    print("Main connector not available")
    exit(1)

res = safe_run_async(main.list_tabs())
if not res.tabs:
    print("No tabs open")
    exit(1)

tab_id = res.tabs[0].tab_id
print("Tab:", tab_id, res.tabs[0].url[:60])

# Test 1: document.title
r1 = bridge.execute_js(tab_id, "(function(){ return document.title; })()")
print("title: ", r1)

# Test 2: innerText
r2 = bridge.execute_js(tab_id, "(function(){ return document.body.innerText.substring(0, 200); })()")
print("body:  ", r2)

# Test 3: number
r3 = bridge.execute_js(tab_id, "(function(){ return document.querySelectorAll('p').length; })()")
print("count: ", r3)

# Test 4: get_build_info
r4 = bridge.execute_js(tab_id, "(function(){ return JSON.stringify({build: 'test'}); })()")
print("json:  ", r4)
