"""Quick test: does the worker's _transcribe_sync work directly?"""
import sys, os, time
sys.path.insert(0, r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final")
os.chdir(r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final")
from dotenv import load_dotenv; load_dotenv()

import mini_kio.voice._stt_worker as w

pcm = open(r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\_test_pcm.raw", "rb").read()
print(f"PCM: {len(pcm)} bytes")

print("Loading model...")
t0 = time.monotonic()
m = w._ensure_model()
print(f"Model loaded ({time.monotonic()-t0:.1f}s)")

print("Transcribing...")
t0 = time.monotonic()
result = w._transcribe_sync(pcm)
print(f"Result ({time.monotonic()-t0:.1f}s): {result!r}")
