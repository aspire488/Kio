"""
Forensic Runtime Validation — Gate 5 Final

Tests all 4 chains from the user's failure report.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["KIO_TEST_MODE"] = "1"
os.environ["BROWSER_CONNECTOR_ENABLED"] = "true"

from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input
from mini_kio.core.continuity_resolver import ContinuityResolver

rt = bootstrap_runtime()

def chain(label, prompts):
    print(f"\n{'='*60}")
    print(f"CHAIN {label}")
    print(f"{'='*60}")
    for i, p in enumerate(prompts, 1):
        r = dispatch_channel_input(p, channel="test", user_id=0)
        ok = r.get("success", False)
        msg = str(r.get("message", ""))
        subj = r.get("subject", "")
        topic = r.get("topic", "")
        print(f"\n  [{i}] {p}")
        print(f"       ok={ok}")
        if msg:
            print(f"       msg={msg[:120]}")
        if subj:
            print(f"       subject={subj[:60]}")
        if topic:
            print(f"       topic={topic}")
        # Check continuity state
        ss = ContinuityResolver._session_state
        if ss:
            print(f"       active_entity={ss.active_entity}")
            print(f"       active_domain={ss.active_domain}")
            if ss.last_action:
                print(f"       last_action={ss.last_action}")
            if ss.last_action_target:
                print(f"       last_action_target={ss.last_action_target}")

# ── CHAIN A: Interstellar continuity ──
chain("A: Interstellar -> him -> he -> similar -> trailer -> youtube", [
    "Who directed Interstellar?",
    "Tell me about him",
    "What else has he directed?",
    "Which one is most similar to Interstellar?",
    "Show trailer",
    "youtube",
])

# ── CHAIN B: FIFA highlights ──
chain("B: FIFA updates -> highlights -> youtube", [
    "Latest FIFA World Cup updates",
    "Play highlights",
    "youtube",
])

# ── CHAIN C: Book recommendations ──
chain("C: Atomic Habits -> similar books -> first one -> author", [
    "I loved Atomic Habits",
    "Recommend similar books",
    "Tell me about the first one",
    "Who wrote it?",
])

# ── CHAIN D: Music recommendations ──
chain("D: Imagine Dragons -> similar artists -> play popular song", [
    "I enjoy Imagine Dragons",
    "Recommend similar artists",
    "Play their most popular song",
])

print(f"\n{'='*60}")
print("ALL CHAINS COMPLETE")
print(f"{'='*60}")
