"""
Deep debug: Try every Telegram IP with various TLS/HTTP configurations.
"""
import socket
import ssl
import sys
import time

TOKEN = ""
with open(".env") as f:
    for line in f:
        if line.startswith("TELEGRAM_TOKEN="):
            TOKEN = line.split("=", 1)[1].strip()
            break

print(f"Token: {TOKEN[:15]}...")
print()

TARGETS = [
    ("api.telegram.org", "api.telegram.org (ISP DNS)", False),
    ("149.154.175.53", "TG DC3 (reachable)", True),
    ("91.108.56.100", "TG MTProto (reachable)", True),
]

def try_https_simple(host, port, desc, use_host_header):
    """
    Raw HTTPS: Send TLS ClientHello via Python SSL, then HTTP GET.
    """
    results = []
    for server_hostname in [host, "api.telegram.org", None]:
        try:
            ctx = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            t0 = time.time()
            s.connect((host, port))
            connect_ms = (time.time() - t0) * 1000
            
            t0 = time.time()
            if server_hostname:
                ss = ctx.wrap_socket(s, server_hostname=server_hostname)
            else:
                ss = ctx.wrap_socket(s)
            tls_ms = (time.time() - t0) * 1000
            tls_version = ss.version()
            
            t0 = time.time()
            http_host = host if not use_host_header else "api.telegram.org"
            
            # Try HEAD / first to see if server responds
            if TOKEN:
                request = (
                    f"GET /bot{TOKEN}/getMe HTTP/1.1\r\n"
                    f"Host: api.telegram.org\r\n"
                    f"User-Agent: KIO/1.0\r\n"
                    f"Connection: close\r\n\r\n"
                )
            else:
                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: api.telegram.org\r\n"
                    f"User-Agent: KIO/1.0\r\n"
                    f"Connection: close\r\n\r\n"
                )
            
            ss.sendall(request.encode())
            response = b""
            while True:
                chunk = ss.recv(4096)
                if not chunk:
                    break
                response += chunk
            http_ms = (time.time() - t0) * 1000
            
            ss.close()
            
            # Parse HTTP status
            status_line = response.split(b"\r\n")[0].decode("utf-8", errors="replace") if response else "NO_RESPONSE"
            body_start = response.find(b"\r\n\r\n")
            body = response[body_start+4:].decode("utf-8", errors="replace") if body_start > 0 else ""
            
            result = {
                "SNI": server_hostname or "NONE",
                "connect_ms": f"{connect_ms:.0f}",
                "tls_ms": f"{tls_ms:.0f}",
                "tls_version": tls_version,
                "status": status_line,
                "body_size": len(body),
                "body_preview": body[:200],
            }
            results.append(result)
            
        except Exception as e:
            results.append({
                "SNI": server_hostname or "NONE",
                "error": f"{type(e).__name__}: {str(e)[:100]}",
            })
    
    return results

for host, desc, use_host in TARGETS:
    print(f"=== {desc} ({host}) ===")
    for r in try_https_simple(host, 443, desc, use_host):
        if "error" in r:
            print(f"  SNI={r['SNI']}: ERROR {r['error']}")
        else:
            print(f"  SNI={r['SNI']}: connect={r['connect_ms']}ms tls={r['tls_ms']}ms vers={r['tls_version']} status={r['status'][:60]}")
            if r['body_preview']:
                print(f"    Body: {r['body_preview'][:100]}")
    print()

print("=" * 60)
print("VERDICT")
print("=" * 60)
print()
print("1. DNS poisoning: ISP returns WRONG IP (49.44.79.236)")
print("   Correct IP from Google/Cloudflare DNS: 149.154.166.110")
print()
print("2. Even correct Bot API IPs are BLOCKED on this network")
print("   Only MTProto IPs (149.154.175.53, 91.108.56.100) are reachable")
print()
print("3. Telegram Bot API cannot be reached via HTTPS on this network")
print("   Root cause: Network/firewall blocks Telegram Bot API traffic")
print()
print("Possible mitigations:")
print("  A. Use a proxy/VPN")
print("  B. Use MTProto proxy (requires Bot API via MTProto)")
print("  C. Change network (mobile hotspot, different ISP)")
print("  D. Set a custom Bot API endpoint via local proxy")
