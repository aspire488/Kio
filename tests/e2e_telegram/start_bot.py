#!/usr/bin/env python3
"""Start KIO Telegram bot in background for E2E validation.

This script bootstraps the KIO runtime and starts the Telegram polling bot.
It is designed to run as a background process during E2E validation.
"""
import os
import sys

# Ensure encoding safety
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Set working directory
ROOT = r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

print("[E2E_BOT] Starting KIO bot...")
from kio_bot import run_bot
run_bot()
