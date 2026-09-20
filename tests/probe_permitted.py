"""Probe extension with permitted URLs."""
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
for t in (res.tabs or []):
    print("  {} {}".format(t.tab_id, t.url[:80]))

# Find a tab on a permitted domain
permitted = ["youtube.com", "127.0.0.1"]
target_tab = None
for t in (res.tabs or []):
    for p in permitted:
        if p in (t.url or ""):
            target_tab = t
            break
    if target_tab:
        break

if not target_tab:
    # Open youtube.com in a new tab
    print("\nOpening youtube.com...")
    tab_result = safe_run_async(conn.open_tab("https://www.youtube.com"))
    print("open_tab: success={} tab_id={}".format(tab_result.success, tab_result.tab.tab_id if tab_result.tab else None))
    time.sleep(3)
    res = asyncio.run(conn.list_tabs())
    for t in (res.tabs or []):
        if "youtube" in (t.url or ""):
            target_tab = t
            break

if target_tab:
    tab_id = target_tab.tab_id
    print("\nUsing tab: {} {}".format(tab_id, target_tab.url[:60]))
    
    # Test run_js
    js = "(function(){ return document.title; })()"
    r1 = safe_run_async(conn.execute_script(tab_id, "run_js", args=[js]))
    print("run_js title: success={} message={}".format(r1.success, r1.message))
    
    js2 = "(function(){ return document.body.innerText.substring(0, 300); })()"
    r2 = safe_run_async(conn.execute_script(tab_id, "run_js", args=[js2]))
    print("run_js body: success={} len={}".format(r2.success, len(str(r2.message))))
    
    js3 = '(function(){ var links = []; document.querySelectorAll("a[href]").forEach(function(a){ links.push({href: a.href, text: a.innerText.trim().substring(0,100)}); }); return JSON.stringify(links); })()'
    r3 = safe_run_async(conn.execute_script(tab_id, "run_js", args=[js3]))
    print("run_js links: success={} len={}".format(r3.success, len(str(r3.message))))
else:
    print("No permitted tab found")
