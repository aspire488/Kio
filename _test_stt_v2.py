#!/usr/bin/env python3
"""Minimal STT worker test."""
import subprocess, sys, json, base64, time, threading

proc = subprocess.Popen(
    [sys.executable, "-m", "mini_kio.voice._stt_worker"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    cwd=r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final",
)
print(f"Worker PID: {proc.pid}", flush=True)
time.sleep(3)

# Check alive
if proc.poll() is not None:
    stderr = proc.stderr.read(4096).decode(errors="replace")
    print(f"Worker died! stderr: {stderr[:1000]}", flush=True)
    sys.exit(1)
print("Worker alive", flush=True)

# Send ping
ping = json.dumps({"id": 0, "ping": True}) + "\n"
print(f"Sending ping: {ping.strip()!r}", flush=True)
proc.stdin.write(ping.encode())
proc.stdin.flush()

# Read response in background thread
resp_line = [None]
def _read():
    try:
        resp_line[0] = proc.stdout.readline()
    except Exception as e:
        resp_line[0] = f"ERR:{e}"
t = threading.Thread(target=_read, daemon=True)
t.start()
t.join(15)

if resp_line[0] is None:
    print("Ping TIMEOUT (15s)", flush=True)
    # Check if worker died
    if proc.poll() is not None:
        stderr = proc.stderr.read(4096).decode(errors="replace")
        print(f"Worker died during ping! stderr: {stderr[:500]}", flush=True)
    else:
        print("Worker still alive but no response", flush=True)
else:
    print(f"Ping response: {resp_line[0]!r}", flush=True)

proc.kill()
