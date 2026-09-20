"""Test worker subprocess with stderr capture."""
import subprocess, sys, json, base64, time, threading, os

proc = subprocess.Popen(
    [sys.executable, "-m", "mini_kio.voice._stt_worker"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    cwd=r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final",
    env={**os.environ, "PYTHONUNBUFFERED": "1"},
)
time.sleep(2)
print(f"Worker alive: {proc.poll() is None}", flush=True)

# Collect stderr in background
stderr_lines = []
def _read_stderr():
    for line in proc.stderr:
        stderr_lines.append(line.decode(errors="replace").rstrip())
stderr_t = threading.Thread(target=_read_stderr, daemon=True)
stderr_t.start()

# Send ping
print("Sending ping...", flush=True)
proc.stdin.write(json.dumps({"id": 0, "ping": True}).encode() + b"\n")
proc.stdin.flush()

resp = proc.stdout.readline()
print(f"Ping response: {resp}", flush=True)

# Send PCM transcription
pcm = open(r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\_test_pcm.raw", "rb").read()
payload = json.dumps({"id": 1, "pcm": base64.b64encode(pcm).decode("ascii")}) + "\n"
print(f"Sending {len(pcm)} bytes PCM ({len(payload)} bytes payload)...", flush=True)
t0 = time.monotonic()
proc.stdin.write(payload.encode())
proc.stdin.flush()

# Wait for response with timeout
resp = [None]
def _read():
    resp[0] = proc.stdout.readline()
t = threading.Thread(target=_read, daemon=True)
t.start()
t.join(30)
elapsed = time.monotonic() - t0

if resp[0] is None:
    print(f"TIMEOUT ({elapsed:.1f}s)", flush=True)
    print(f"Stderr so far:", flush=True)
    for line in stderr_lines[-20:]:
        print(f"  {line}", flush=True)
else:
    data = json.loads(resp[0].strip())
    print(f"Result ({elapsed:.1f}s): {data}", flush=True)

proc.kill()
# Print all stderr
print("\n=== ALL STDERR ===", flush=True)
for line in stderr_lines:
    print(line, flush=True)
