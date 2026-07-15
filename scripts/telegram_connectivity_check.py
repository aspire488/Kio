"""
PHASE 3 — Network Diagnostics for Telegram Bot API.

Tests all layers from DNS through TLS to final HTTP endpoint.
"""

import socket
import ssl
import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TOKEN_PREFIX = TOKEN[:15] + "..." if TOKEN else "(EMPTY)"
TOKEN_LENGTH = len(TOKEN)
TOKEN_FORMAT_OK = ":" in TOKEN and TOKEN.split(":")[0].isdigit() if TOKEN else False

results = []

def log(label, status, detail=""):
    results.append({"label": label, "status": status, "detail": detail})
    status_symbol = "PASS" if status == "PASS" else "FAIL" if status == "FAIL" else "INFO"
    print(f"  [{status_symbol}] {label}")
    if detail:
        for line in detail.split("\n"):
            print(f"         {line}")

print("=" * 60)
print("TELEGRAM BOT API — NETWORK DIAGNOSTICS")
print("=" * 60)
print()

# ── 1. Token Validation ────────────────────────────────────────────
print("[1] TOKEN VALIDATION")
print("-" * 40)
log("TELEGRAM_TOKEN present", "PASS" if TOKEN else "FAIL",
    f"length={TOKEN_LENGTH}, prefix={TOKEN_PREFIX}")
log("TELEGRAM_TOKEN format (botID:hash)", "PASS" if TOKEN_FORMAT_OK else "FAIL",
    f"token={TOKEN_PREFIX}")

# ── 2. DNS Resolution ──────────────────────────────────────────────
print()
print("[2] DNS RESOLUTION")
print("-" * 40)
try:
    addrs = socket.getaddrinfo("api.telegram.org", 443)
    addr_strs = [str(a[4]) for a in addrs[:5]]
    log("api.telegram.org DNS", "PASS",
        f"Resolved {len(addrs)} addresses: {', '.join(addr_strs)}")
except Exception as e:
    log("api.telegram.org DNS", "FAIL", str(e))

try:
    addrs4 = socket.getaddrinfo("api.telegram.org", 443, family=socket.AF_INET)
    log("IPv4 resolution", "PASS", str(addrs4[0][4]))
except Exception as e:
    log("IPv4 resolution", "FAIL", str(e))

try:
    addrs6 = socket.getaddrinfo("api.telegram.org", 443, family=socket.AF_INET6)
    log("IPv6 resolution", "PASS", str(addrs6[0][4]))
except Exception as e:
    log("IPv6 resolution", "FAIL", str(e))

# ── 3. TCP Socket Test ─────────────────────────────────────────────
print()
print("[3] TCP SOCKET CONNECTION")
print("-" * 40)

for host, desc in [
    ("api.telegram.org", "api.telegram.org:443 (DNS-resolved)"),
    ("149.154.167.220", "149.154.167.220:443 (TG DC2)"),
    ("149.154.175.53", "149.154.175.53:443 (TG DC3)"),
    ("91.108.56.100", "91.108.56.100:443 (TG MTProto)"),
]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        t0 = time.time()
        s.connect((host, 443))
        elapsed = time.time() - t0
        s.close()
        log(f"TCP {desc}", "PASS", f"connected in {elapsed:.2f}s")
    except Exception as e:
        log(f"TCP {desc}", "FAIL", f"{type(e).__name__}: {e}")

# ── 4. TLS Handshake ───────────────────────────────────────────────
print()
print("[4] TLS HANDSHAKE")
print("-" * 40)

for host, ip in [
    ("api.telegram.org", "api.telegram.org"),
    ("149.154.175.53 (TG DC3)", "149.154.175.53"),
    ("91.108.56.100 (TG MTProto)", "91.108.56.100"),
]:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((ip, 443))
        ss = ctx.wrap_socket(s, server_hostname="api.telegram.org")
        version = ss.version()
        cipher = ss.cipher()
        ss.close()
        s.close()
        log(f"TLS {host}", "PASS", f"version={version} cipher={cipher}")
    except Exception as e:
        log(f"TLS {host}", "FAIL", f"{type(e).__name__}: {e}")

# ── 5. HTTPS via httpx ─────────────────────────────────────────────
print()
print("[5] HTTPS VIA HTTPX")
print("-" * 40)

try:
    import httpx
    import asyncio

    async def test_httpx():
        # Test to working domain first
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                t0 = time.time()
                r = await client.get("https://google.com")
                elapsed = time.time() - t0
                log("httpx google.com", "PASS", f"status={r.status_code} elapsed={elapsed:.2f}s")
        except Exception as e:
            log("httpx google.com", "FAIL", f"{type(e).__name__}: {e}")

        # Test to api.telegram.org
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                t0 = time.time()
                r = await client.get("https://api.telegram.org")
                elapsed = time.time() - t0
                log("httpx api.telegram.org", "PASS" if r.status_code < 400 else "FAIL",
                    f"status={r.status_code} elapsed={elapsed:.2f}s")
        except Exception as e:
            log("httpx api.telegram.org", "FAIL", f"{type(e).__name__}: {e}")

        # Test to known-good Telegram IP
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                t0 = time.time()
                r = await client.get("https://149.154.175.53", headers={"Host": "api.telegram.org"})
                elapsed = time.time() - t0
                log("httpx 149.154.175.53 (Host=api.telegram.org)", "PASS" if r.status_code < 400 else "FAIL",
                    f"status={r.status_code} elapsed={elapsed:.2f}s")
        except Exception as e:
            log("httpx 149.154.175.53 (Host=api.telegram.org)", "FAIL", f"{type(e).__name__}: {e}")

        # Test Telegram Bot API with token
        if TOKEN and TOKEN_FORMAT_OK:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                    t0 = time.time()
                    r = await client.get(f"https://api.telegram.org/bot{TOKEN}/getMe")
                    elapsed = time.time() - t0
                    data = r.json()
                    ok = data.get("ok", False)
                    log(f"https://api.telegram.org/bot{TOKEN_PREFIX}/getMe",
                        "PASS" if ok else "FAIL",
                        f"status={r.status_code} ok={ok} elapsed={elapsed:.2f}s")
            except Exception as e:
                log(f"https://api.telegram.org/bot{TOKEN_PREFIX}/getMe",
                    "FAIL", f"{type(e).__name__}: {e}")

            # Try with known-good IP
            for ip in ["149.154.175.53", "91.108.56.100"]:
                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                        t0 = time.time()
                        url = f"https://{ip}/bot{TOKEN}/getMe"
                        r = await client.get(url, headers={"Host": "api.telegram.org"})
                        elapsed = time.time() - t0
                        data = r.json()
                        ok = data.get("ok", False)
                        log(f"https://{ip}/bot{TOKEN_PREFIX}/getMe (Host=api.telegram.org)",
                            "PASS" if ok else "FAIL",
                            f"status={r.status_code} ok={ok} elapsed={elapsed:.2f}s")
                except Exception as e:
                    log(f"https://{ip}/bot{TOKEN_PREFIX}/getMe (Host=api.telegram.org)",
                        "FAIL", f"{type(e).__name__}: {e}")

    asyncio.run(test_httpx())
except ImportError as e:
    log("httpx tests", "SKIP", f"httpx not available: {e}")

# ── 6. Environment Audit ───────────────────────────────────────────
print()
print("[6] ENVIRONMENT")
print("-" * 40)

# Proxy variables
proxy_vars = ["HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"]
found_proxy = False
for var in proxy_vars:
    val = os.environ.get(var, "")
    if val:
        log(f"ENV {var}", "INFO", f"set to {val}")
        found_proxy = True
if not found_proxy:
    log("Proxy env vars", "INFO", "none set")

# NO_PROXY
no_proxy = os.environ.get("NO_PROXY", "")
if no_proxy:
    log("ENV NO_PROXY", "INFO", no_proxy)

# Python version
import platform
log("Python version", "INFO", platform.python_version())
log("Platform", "INFO", platform.platform())

# telegram and httpx versions
try:
    import telegram
    log("python-telegram-bot", "INFO", telegram.__version__)
except Exception:
    log("python-telegram-bot", "INFO", "not available")

try:
    import httpx
    log("httpx", "INFO", httpx.__version__)
except Exception:
    log("httpx", "INFO", "not available")

try:
    import httpcore
    log("httpcore", "INFO", httpcore.__version__)
except Exception:
    log("httpcore", "INFO", "not available")

# Check hosts file for api.telegram.org
hosts_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "drivers", "etc", "hosts")
try:
    with open(hosts_path, "r") as f:
        hosts_content = f.read()
    if "api.telegram.org" in hosts_content.lower():
        log("Hosts file", "INFO", "api.telegram.org found in hosts file")
        for line in hosts_content.splitlines():
            if "api.telegram.org" in line.lower():
                log("  entry", "INFO", line.strip())
    else:
        log("Hosts file", "INFO", "no api.telegram.org entry")
except Exception as e:
    log("Hosts file", "INFO", f"cannot read: {e}")

# ── 7. Firewall check ──────────────────────────────────────────────
print()
print("[7] FIREWALL CHECK")
print("-" * 40)
try:
    import subprocess
    # Check Windows Firewall rules
    rule_check = subprocess.run(
        ["netsh", "advfirewall", "firewall", "show", "rule", "name=all", "dir=out"],
        capture_output=True, text=True, timeout=10
    )
    lines = rule_check.stdout.splitlines()
    blocking_rules = [l for l in lines if "block" in l.lower() and ("443" in l or "telegram" in l.lower())]
    if blocking_rules:
        log("Firewall outbound rules", "FAIL", f"Found blocking rules: {blocking_rules[:3]}")
    else:
        log("Firewall outbound rules", "INFO", "no obvious blocking rules found")
except Exception as e:
    log("Firewall check", "INFO", f"cannot check: {e}")

# ── SUMMARY ────────────────────────────────────────────────────────
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
skipped = sum(1 for r in results if r["status"] == "SKIP")
print(f"  PASS: {passed}  FAIL: {failed}  SKIP: {skipped}  TOTAL: {len(results)}")
print()

# Save to JSON
output = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "token_valid": TOKEN_FORMAT_OK,
    "token_length": TOKEN_LENGTH,
    "dns_works": any(r["label"] == "api.telegram.org DNS" and r["status"] == "PASS" for r in results),
    "tcp_reachable": any(r["label"].startswith("TCP") and r["status"] == "PASS" for r in results),
    "tls_works": any(r["label"].startswith("TLS") and r["status"] == "PASS" for r in results),
    "httpx_works": any(r["label"].startswith("httpx") and r["status"] == "PASS" for r in results),
    "details": results,
}
output_path = os.path.join(os.path.dirname(__file__), "..", "NETWORK_DIAGNOSTIC_REPORT.md")
with open(output_path, "w") as f:
    f.write("# Network Diagnostic Report\n\n")
    f.write(f"Timestamp: {output['timestamp']}\n\n")
    f.write("## Results\n\n")
    f.write("| Test | Status | Detail |\n")
    f.write("|------|--------|--------|\n")
    for r in results:
        detail_escaped = r["detail"].replace("|", "\\|").replace("\n", "<br>")
        f.write(f"| {r['label']} | {r['status']} | {detail_escaped} |\n")
    f.write("\n## Summary\n\n")
    f.write(f"- PASS: {passed}  FAIL: {failed}  SKIP: {skipped}\n")
    f.write(f"- Token valid: {output['token_valid']}\n")
    f.write(f"- DNS works: {output['dns_works']}\n")
    f.write(f"- TCP reachable: {output['tcp_reachable']}\n")
    f.write(f"- TLS works: {output['tls_works']}\n")
    f.write(f"- httpx works: {output['httpx_works']}\n")

print(f"Full report saved to NETWORK_DIAGNOSTIC_REPORT.md")
