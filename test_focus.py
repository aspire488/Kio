
import logging
import sys
import os

# Mock dependencies to avoid side effects
sys.path.append(os.getcwd())

from mini_kio.core import config
# Ensure connector is enabled for test
config.BROWSER_CONNECTOR_ENABLED = True

from mini_kio.core.command_router import handle_command

logging.basicConfig(level=logging.INFO)

print("--- Testing Focus GitHub ---")
res = handle_command("Focus GitHub")
print(f"Result: {res}")

print("\n--- Testing Switch to GitHub ---")
res = handle_command("Switch to GitHub")
print(f"Result: {res}")
