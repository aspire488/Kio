"""Phase 3M: Live browser validation of all 5 composite actions."""
import os, time
os.environ.pop("KIO_TEST_MODE", None)

from mini_kio.browser_connector.js_bridge import get_js_bridge
from mini_kio.core.async_utils import safe_run_async
from mini_kio.core.browser_operator import (
    browser_extract_price,
    browser_fetch_region,
    browser_extract_records,
    browser_snapshot_sources,
    browser_crawl_extract,
)
from mini_kio.core.command_router import _get_connector

# Wait for JS Bridge
bridge = get_js_bridge()
print("Waiting for JS Bridge...")
for i in range(20):
    if bridge.is_connected():
        break
    time.sleep(1)
    print(f"  attempt {i+1}/20...", flush=True)
print("JS Bridge:", "CONNECTED" if bridge.is_connected() else "NOT CONNECTED")

# Wait for main connector
conn = _get_connector()
if conn:
    for i in range(10):
        if conn.is_connected():
            break
        time.sleep(1)
    res = safe_run_async(conn.list_tabs())
    print("Tabs available:", len(res.tabs) if res.tabs else 0)
else:
    print("No main connector available")

print("\n" + "="*60)
print("PHASE 3M: LIVE BROWSER VALIDATION")
print("="*60)

# 1. browser_extract_price
print("\n--- 1. browser_extract_price ---")
r1 = browser_extract_price(url="https://example.com", price_selector="p")
print("  success:", r1.get("success"))
print("  message:", r1.get("message", "")[:100])
print("  action:", r1.get("action"))

# 2. browser_fetch_region
print("\n--- 2. browser_fetch_region ---")
r2 = browser_fetch_region(url="https://example.com", region_selector="body")
print("  success:", r2.get("success"))
print("  message:", r2.get("message", "")[:100])
print("  action:", r2.get("action"))

# 3. browser_extract_records
print("\n--- 3. browser_extract_records ---")
r3 = browser_extract_records(url="https://example.com", row_selector="p", fields="text")
print("  success:", r3.get("success"))
print("  message:", r3.get("message", "")[:100])
print("  records:", r3.get("records", [])[:2])
print("  action:", r3.get("action"))

# 4. browser_snapshot_sources
print("\n--- 4. browser_snapshot_sources ---")
r4 = browser_snapshot_sources(urls="https://example.com,https://example.org")
print("  success:", r4.get("success"))
print("  message:", r4.get("message", "")[:100])
print("  snapshots:", len(r4.get("snapshots", [])))
print("  action:", r4.get("action"))

# 5. browser_crawl_extract
print("\n--- 5. browser_crawl_extract ---")
r5 = browser_crawl_extract(url="https://example.com", max_chars=500)
print("  success:", r5.get("success"))
print("  message:", r5.get("message", "")[:100])
print("  char_count:", r5.get("char_count", 0))
print("  link_count:", r5.get("link_count", 0))
print("  action:", r5.get("action"))

print("\n" + "="*60)
passed = sum(1 for r in [r1, r2, r3, r4, r5] if r.get("success"))
print(f"RESULT: {passed}/5 composites returned success")
print("="*60)
