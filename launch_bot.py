"""Detached bot launcher with PID file for clean kill."""
import subprocess
import os
import sys
import time

KIO_DIR = r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final"
PYTHON = os.path.join(KIO_DIR, ".venv", "Scripts", "python.exe")
PID_FILE = os.path.join(KIO_DIR, "kio_bot.pid")
LOG = os.path.join(KIO_DIR, "kio_bot_detached.log")

# Kill any existing bot by PID file
if os.path.exists(PID_FILE):
    with open(PID_FILE) as f:
        old_pid = int(f.read().strip())
    try:
        os.kill(old_pid, 9)
        print(f"Killed old bot PID {old_pid}")
    except OSError:
        pass
    os.remove(PID_FILE)

# Launch new bot detached
proc = subprocess.Popen(
    [PYTHON, "-u", "kio_bot.py"],
    cwd=KIO_DIR,
    stdout=open(LOG, "w"),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
)

with open(PID_FILE, "w") as f:
    f.write(str(proc.pid))

print(f"Bot started PID={proc.pid}, log={LOG}")
time.sleep(5)
# Check if still running
if proc.poll() is None:
    print("Bot is running")
else:
    print(f"Bot exited with code {proc.returncode}")
    with open(LOG) as f:
        print(f.read()[-500:])
