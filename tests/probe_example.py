"""Test run_js on example.com tab."""
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

print("Connected:", conn.is_connected())
res = asyncio.run(conn.list_tabs())
print("Tabs:", len(res.tabs) if res.tabs else 0)

# Find example.com tab
example_tab = None
for t in (res.tabs or []):
    if "example.com" in (t.url or ""):
        example_tab = t
        break

if example_tab:
    tab_id = example_tab.tab_id
    print("\nUsing example.com tab:", tab_id)
    
    js1 = "(function(){ return document.title; })()"
    r1 = safe_run_async(conn.execute_script(tab_id, "run_js", args=[js1]))
    print("title: success={} repr={}".format(r1.success, repr(r1.message)))
    
    js2 = "(function(){ return document.body ? document.body.innerText.substring(0, 200) : 'no body'; })()"
    r2 = safe_run_async(conn.execute_script(tab_id, "run_js", args=[js2]))
    print("body: success={} repr={}".format(r2.success, repr(r2.message)))
    
    js3 = "(function(){ var el = document.querySelector('h1'); return el ? el.innerText : 'no h1'; })()"
    r3 = safe_run_async(conn.execute_script(tab_id, "run_js", args=[js3]))
    print("h1: success={} repr={}".format(r3.success, repr(r3.message)))

    # Also test raw get_build_info
    r4 = safe_run_async(conn.execute_script(tab_id, "get_build_info"))
    print("get_build_info: success={} repr={}".format(r4.success, repr(r4.message)))
else:
    print("No example.com tab found. Opening one...")
    tab_result = safe_run_async(conn.open_tab("https://example.com"))
    print("open_tab: success={}".format(tab_result.success))
    time.sleep(3)
    tab_id = tab_result.tab.tab_id if tab_result.tab else None
    if tab_id:
        js = "(function(){ return document.title; })()"
        r = safe_run_async(conn.execute_script(tab_id, "run_js", args=[js]))
        print("title: success={} repr={}".format(r.success, repr(r.message)))
