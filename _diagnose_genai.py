"""
Diagnose Gemini provider initialization — expose the hidden exception.
"""
import os, sys, logging

logging.basicConfig(level=logging.DEBUG)

for mod in list(sys.modules.keys()):
    if "mini_kio" in mod:
        del sys.modules[mod]

from mini_kio.core import config

# Directly test the google.generativeai calls
try:
    import google.generativeai as genai
    print("genai module version:", getattr(genai, "__version__", "unknown"))
    print()
    
    print("Step 1: genai.configure(api_key=...)")
    genai.configure(api_key=config.GEMINI_API_KEY)
    print("  OK — no exception")
    print()

    print("Step 2: genai.GenerativeModel('gemini-2.5-flash')")
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        print("  OK — model =", model)
    except Exception as e:
        print("  FAILED:", type(e).__name__, str(e)[:200])
    print()

    print("Step 3: genai.GenerativeModel('gemini-2.0-flash')")
    try:
        fallback = genai.GenerativeModel("gemini-2.0-flash")
        print("  OK — model =", fallback)
    except Exception as e:
        print("  FAILED:", type(e).__name__, str(e)[:200])

except ImportError as e:
    print("FAILED: google.generativeai not installed:", e)
except Exception as e:
    import traceback
    traceback.print_exc()
