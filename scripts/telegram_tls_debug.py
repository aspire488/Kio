"""
Deep TLS diagnostic for Telegram Bot API on Python 3.14.
Tests various SSL contexts to find what works.
"""

import socket
import ssl
import sys
import os

def test_tls_context(host, port, desc, **ctx_kwargs):
    try:
        ctx = ssl.SSLContext(**ctx_kwargs)
        if "check_hostname" not in ctx_kwargs:
            ctx.check_hostname = True
        if "verify_mode" not in ctx_kwargs:
            ctx.verify_mode = ssl.CERT_REQUIRED
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((host, port))
        ss = ctx.wrap_socket(s, server_hostname="api.telegram.org")
        version = ss.version()
        cipher = ss.cipher()
        cert = ss.getpeercert()
        common_name = ""
        if cert and "subject" in cert:
            for attr in cert["subject"]:
                if attr[0][0] == "commonName":
                    common_name = attr[0][1]
        ss.close()
        s.close()
        print(f"  [PASS] {desc}: TLS={version} cipher={cipher[0]} CN={common_name}")
        return True
    except Exception as e:
        print(f"  [FAIL] {desc}: {type(e).__name__}: {e}")
        return False

hosts_to_test = [
    ("149.154.175.53", "TG DC3"),
    ("91.108.56.100", "TG MTProto"),
    ("api.telegram.org", "DNS-resolved"),
]

print("=" * 70)
print("TELEGRAM TLS DIAGNOSTIC - Python " + sys.version)
print("=" * 70)

for host, desc in hosts_to_test:
    print(f"\n--- {desc} ({host}:443) ---")
    
    # Test 1: Default SSL context
    test_tls_context(host, 443, "Default SSLContext", protocol=ssl.PROTOCOL_TLS_CLIENT)
    
    # Test 2: TLS 1.2 only
    ctx = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((host, 443))
        ss = ctx.wrap_socket(s, server_hostname="api.telegram.org")
        print(f"  [PASS] TLS 1.2 only: version={ss.version()} cipher={ss.cipher()[0]}")
        ss.close()
        s.close()
    except Exception as e:
        print(f"  [FAIL] TLS 1.2 only: {type(e).__name__}: {e}")
    
    # Test 3: TLS 1.3 only
    ctx = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((host, 443))
        ss = ctx.wrap_socket(s, server_hostname="api.telegram.org")
        print(f"  [PASS] TLS 1.3 only: version={ss.version()} cipher={ss.cipher()[0]}")
        ss.close()
        s.close()
    except Exception as e:
        print(f"  [FAIL] TLS 1.3 only: {type(e).__name__}: {e}")
    
    # Test 4: No certificate verification
    ctx = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((host, 443))
        ss = ctx.wrap_socket(s, server_hostname="api.telegram.org")
        print(f"  [PASS] No verify: version={ss.version()} cipher={ss.cipher()[0]}")
        ss.close()
        s.close()
    except Exception as e:
        print(f"  [FAIL] No verify: {type(e).__name__}: {e}")
    
    # Test 5: Legacy default context (pre-3.14 style)
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((host, 443))
        ss = ctx.wrap_socket(s, server_hostname="api.telegram.org")
        print(f"  [PASS] create_default_context: version={ss.version()} cipher={ss.cipher()[0]}")
        ss.close()
        s.close()
    except Exception as e:
        print(f"  [FAIL] create_default_context: {type(e).__name__}: {e}")

print("\n" + "=" * 70)
print("Check for Python 3.14 specific SSL changes")
print("=" * 70)

# Check what ciphers are available
ctx = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
try:
    ciphers = ctx.get_ciphers()
    print(f"Default ciphers available: {len(ciphers)}")
    for c in ciphers[:5]:
        print(f"  {c['name']} (min_version={c['minimum_tls_version']})")
except Exception as e:
    print(f"get_ciphers failed: {e}")

# Check TLS version constants
print(f"\nTLSVersion constants:")
for attr in dir(ssl.TLSVersion):
    if not attr.startswith("_"):
        val = getattr(ssl.TLSVersion, attr)
        print(f"  TLSVersion.{attr} = {val}")

# Check for Python 3.14 specific SSL changes
import sysconfig
print(f"\nPython config:")
print(f"  sysconfig: {sysconfig.get_config_var('py_version_short')}")
print(f"  SSL module: {ssl.OPENSSL_VERSION}")
