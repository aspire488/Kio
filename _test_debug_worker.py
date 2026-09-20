"""Debug: test the worker with added prints to isolate the hang."""
import subprocess, sys, json, base64, time, threading, os

# Patch the worker with debug prints before running
import importlib.util
spec = importlib.util.spec_from_file_location(
    "_stt_worker_debug",
    r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\voice\_stt_worker.py",
)
mod = importlib.util.module_from_spec(spec)

# Read source and inject prints
src = open(r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\voice\_stt_worker.py", encoding="utf-8").read()
src = src.replace(
    "def _transcribe_sync(pcm: bytes) -> str:",
    "def _transcribe_sync(pcm: bytes) -> str:\n    import sys as _sys; print(f'[WORKER] _transcribe_sync called, {len(pcm)} bytes', file=_sys.__stderr__, flush=True)",
)
src = src.replace(
    "model = _ensure_model()",
    "print('[WORKER] calling _ensure_model', file=_sys.__stderr__, flush=True); model = _ensure_model(); print('[WORKER] model ready', file=_sys.__stderr__, flush=True)",
)
src = src.replace(
    "result = await asyncio.to_thread(_transcribe_sync, raw)",
    "print(f'[WORKER] about to call to_thread, {len(raw)} bytes', file=sys.__stderr__, flush=True); result = await asyncio.to_thread(_transcribe_sync, raw); print(f'[WORKER] to_thread returned: {result!r}', file=sys.__stderr__, flush=True)",
)

# Write patched version
patched = r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\_stt_worker_debug.py"
with open(patched, "w", encoding="utf-8") as f:
    f.write(src.replace(
        '"""Standalone Whisper STT worker',
        '"""DEBUG PATCHED Whisper STT worker',
    ))

proc = subprocess.Popen(
    [sys.executable, patched],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    cwd=r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final",
    env={**os.environ, "PYTHONUNBUFFERED": "1"},
)
time.sleep(2)
print(f"Worker alive: {proc.poll() is None}", flush=True)

# Collect stderr
stderr_lines = []
def _read_stderr():
    for line in proc.stderr:
        stderr_lines.append(line.decode(errors="replace").rstrip())
        sys.stderr.write(f"[STDERR] {stderr_lines[-1]}\n")
        sys.stderr.flush()
t = threading.Thread(target=_read_stderr, daemon=True)
t.start()

# Ping
proc.stdin.write(json.dumps({"id": 0, "ping": True}).encode() + b"\n")
proc.stdin.flush()
resp = proc.stdout.readline()
print(f"Ping: {resp}", flush=True)

# PCM
pcm = open(r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\_test_pcm.raw", "rb").read()
payload = json.dumps({"id": 1, "pcm": base64.b64encode(pcm).decode("ascii")}) + "\n"
print(f"Sending PCM ({len(payload)} bytes)...", flush=True)
proc.stdin.write(payload.encode())
proc.stdin.flush()

resp = [None]
def _read():
    resp[0] = proc.stdout.readline()
t2 = threading.Thread(target=_read, daemon=True)
t2.start()
t2.join(45)

if resp[0] is None:
    print("TIMEOUT", flush=True)
else:
    print(f"Result: {resp[0]}", flush=True)

proc.kill()
time.sleep(0.5)
print("\n=== STDERR ===", flush=True)
for line in stderr_lines:
    print(line, flush=True)
os.remove(patched)
