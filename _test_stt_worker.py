#!/usr/bin/env python3
"""Quick STT worker test — checks startup, ping, and one transcription."""
import subprocess, sys, json, base64, time, threading

proc = subprocess.Popen(
    [sys.executable, "-m", "mini_kio.voice._stt_worker"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    cwd=r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final",
)
print(f"Worker PID: {proc.pid}")

def read_with_timeout(pipe, timeout_s=30):
    result = [None]
    def _read():
        try:
            result[0] = pipe.readline()
        except Exception as e:
            result[0] = f"ERROR: {e}"
    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return None  # timeout
    return result[0]

time.sleep(3)  # let worker start

# Ping
ping = json.dumps({"id": 0, "ping": True}).encode() + b"\n"
print("Sending ping...")
proc.stdin.write(ping)
proc.stdin.flush()

resp = read_with_timeout(proc.stdout, 10)
print(f"Ping response: {resp!r}")
if resp is None:
    print("PING TIMEOUT - checking stderr...")
    proc.kill()
    stderr = proc.stderr.read(4096)
    print(f"Stderr: {stderr[:1000]!r}")
    sys.exit(1)

# Transcription
pcm = open(r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\_test_pcm.raw", "rb").read()
payload = json.dumps({"id": 1, "pcm": base64.b64encode(pcm).decode("ascii")}).encode() + b"\n"
print(f"Sending transcription ({len(pcm)} bytes PCM)...")
t0 = time.monotonic()
proc.stdin.write(payload)
proc.stdin.flush()

resp = read_with_timeout(proc.stdout, 120)
elapsed = time.monotonic() - t0
if resp is None:
    print(f"TRANSCRIPTION TIMEOUT ({elapsed:.1f}s)")
    proc.kill()
    stderr = proc.stderr.read(4096)
    print(f"Stderr: {stderr[:1000]!r}")
else:
    data = json.loads(resp.strip())
    print(f"Transcription ({elapsed:.1f}s): ok={data.get('ok')} text={data.get('text', '')[:200]!r}")

proc.kill()
