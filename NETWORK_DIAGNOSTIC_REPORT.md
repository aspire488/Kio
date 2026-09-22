# Network Diagnostic Report

Timestamp: 2026-06-16T14:43:01

## Results

| Test | Status | Detail |
|------|--------|--------|
| TELEGRAM_TOKEN present | PASS | length=46, prefix=[REDACTED] |
| TELEGRAM_TOKEN format (botID:hash) | PASS | token=[REDACTED] |
| api.telegram.org DNS | PASS | Resolved 2 addresses: ('2405:200:1607:2820:41::36', 443, 0, 0), ('49.44.79.236', 443) |
| IPv4 resolution | PASS | ('49.44.79.236', 443) |
| IPv6 resolution | PASS | ('2405:200:1607:2820:41::36', 443, 0, 0) |
| TCP api.telegram.org:443 (DNS-resolved) | FAIL | TimeoutError: timed out |
| TCP 149.154.167.220:443 (TG DC2) | FAIL | TimeoutError: timed out |
| TCP 149.154.175.53:443 (TG DC3) | PASS | connected in 0.32s |
| TCP 91.108.56.100:443 (TG MTProto) | PASS | connected in 0.05s |
| TLS api.telegram.org | FAIL | TimeoutError: timed out |
| TLS 149.154.175.53 (TG DC3) | FAIL | SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1081) |
| TLS 91.108.56.100 (TG MTProto) | FAIL | SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1081) |
| httpx google.com | PASS | status=301 elapsed=0.54s |
| httpx api.telegram.org | FAIL | ConnectTimeout:  |
| httpx 149.154.175.53 (Host=api.telegram.org) | FAIL | ConnectError:  |
| https://api.telegram.org/bot[REDACTED]/.../getMe | FAIL | ConnectTimeout:  |
| https://149.154.175.53/bot[REDACTED]/.../getMe (Host=api.telegram.org) | FAIL | ConnectError:  |
| https://91.108.56.100/bot[REDACTED]/.../getMe (Host=api.telegram.org) | FAIL | ConnectError:  |
| Proxy env vars | INFO | none set |
| ENV NO_PROXY | INFO | 127.0.0.1,localhost,::1 |
| Python version | INFO | 3.14.5 |
| Platform | INFO | Windows-11-10.0.26200-SP0 |
| python-telegram-bot | INFO | 22.7 |
| httpx | INFO | 0.28.1 |
| httpcore | INFO | 1.0.9 |
| Hosts file | INFO | no api.telegram.org entry |
| Firewall outbound rules | INFO | no obvious blocking rules found |

## Summary

- PASS: 8  FAIL: 10  SKIP: 0
- Token status: NOT VERIFIED — previously exposed; rotate before live validation
- DNS works: True
- TCP reachable: True
- TLS works: False
- httpx works: True
