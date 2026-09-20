"""Extract all ai_reasoning templates from the authoritative library."""
import sys
sys.path.insert(0, r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final")
from pathlib import Path
import yaml

lib = Path(r"C:\Users\joelj\Downloads\kio_final\automation\library")
templates = []
for yml in sorted(lib.rglob("*.yaml")):
    with open(yml) as f:
        t = yaml.safe_load(f)
    if t and any(s.get("capability") == "ai_reasoning" for s in t.get("steps", [])):
        templates.append(t)

print(f"Total ai_reasoning templates: {len(templates)}")
print()
for t in templates:
    tid = t.get("id", "unknown")
    steps = t.get("steps", [])
    ai_steps = [s for s in steps if s.get("capability") == "ai_reasoning"]
    all_caps = sorted(set(s.get("capability") for s in steps))
    print(f"--- {tid} ---")
    print(f"  Category: {t.get('category', '?')}")
    print(f"  Total steps: {len(steps)}")
    print(f"  Capabilities: {all_caps}")
    for s in ai_steps:
        act = s.get("action", "?")
        inp = list(s.get("inputs", {}).keys()) if isinstance(s.get("inputs"), dict) else s.get("inputs", [])
        out = s.get("outputs", [])
        if isinstance(out, dict):
            out = list(out.keys())
        print(f"  AI step: action={act}, inputs={inp}, outputs={out}")
    # Show non-ai steps
    non_ai = [s for s in steps if s.get("capability") != "ai_reasoning"]
    if non_ai:
        print(f"  Non-AI steps:")
        for s in non_ai:
            cap = s.get("capability", "?")
            act = s.get("action", "?")
            print(f"    {cap}.{act}")
    print()
