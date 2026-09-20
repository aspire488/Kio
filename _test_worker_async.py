"""Test: run the worker's _serve() with simulated stdin/stdout to isolate the async issue."""
import asyncio, sys, io, os, json, base64, threading, time
sys.path.insert(0, r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final")
os.chdir(r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final")
from dotenv import load_dotenv; load_dotenv()

import mini_kio.voice._stt_worker as w

pcm = open(r"_test_pcm.raw", "rb").read()

# Simulate stdin/stdout with pipes
r_pipe, w_pipe = os.pipe()
r_f = os.fdopen(r_pipe, "r", buffering=1)  # line-buffered text
w_f = os.fdopen(w_pipe, "w", buffering=1)

# Write requests in a thread (simulating the parent)
def _sender():
    # Ping
    w_f.write(json.dumps({"id": 0, "ping": True}) + "\n")
    w_f.flush()
    time.sleep(0.5)
    # Transcription
    payload = json.dumps({"id": 1, "pcm": base64.b64encode(pcm).decode("ascii")}) + "\n"
    print(f"SENDING {len(pcm)} bytes PCM...", flush=True)
    w_f.write(payload)
    w_f.flush()
    # Wait then close
    time.sleep(30)
    w_f.close()

sender = threading.Thread(target=_sender, daemon=True)
sender.start()

# Capture output
output_lines = []
class Capturer:
    def write(self, s):
        if s.strip():
            output_lines.append(s.strip())
        sys.__stderr__.write(s)
    def flush(self):
        sys.__stderr__.flush()

capturer = Capturer()

print("Starting _serve()...", flush=True)
t0 = time.monotonic()

async def run():
    # Patch wfile to capture output
    original_serve = w._serve
    
    async def patched_serve(rfile, wfile):
        class CaptureWfile:
            def write(self, s):
                capturer.write(s)
                wfile.write(s)
            def flush(self):
                wfile.flush()
        return await original_serve(rfile, CaptureWfile())
    
    loop = asyncio.get_running_loop()
    # Run serve in executor with our simulated stdin
    result = await asyncio.wait_for(
        w._serve(r_f, capturer),
        timeout=45
    )
    return result

try:
    asyncio.run(run())
except asyncio.TimeoutError:
    print(f"TIMEOUT after {time.monotonic()-t0:.1f}s", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
finally:
    elapsed = time.monotonic() - t0
    print(f"Elapsed: {elapsed:.1f}s", flush=True)
    print(f"Output lines: {output_lines}", flush=True)
