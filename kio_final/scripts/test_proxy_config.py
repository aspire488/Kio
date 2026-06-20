"""
Verify TELEGRAM_PROXY env var flows through config correctly.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["TELEGRAM_PROXY"] = "socks5://127.0.0.1:1080"

import importlib
from mini_kio.core import config
importlib.reload(config)

print(f"TELEGRAM_PROXY from config: {config.TELEGRAM_PROXY}")
assert config.TELEGRAM_PROXY == "socks5://127.0.0.1:1080", f"Unexpected: {config.TELEGRAM_PROXY}"

# Test clean
del os.environ["TELEGRAM_PROXY"]
importlib.reload(config)
print(f"TELEGRAM_PROXY after unset: {config.TELEGRAM_PROXY}")
assert config.TELEGRAM_PROXY is None, f"Should be None: {config.TELEGRAM_PROXY}"

# Test HTTPS_PROXY fallback
os.environ["HTTPS_PROXY"] = "http://proxy.local:8080"
importlib.reload(config)
print(f"TELEGRAM_PROXY via HTTPS_PROXY: {config.TELEGRAM_PROXY}")
assert config.TELEGRAM_PROXY == "http://proxy.local:8080"

print("ALL OK")
