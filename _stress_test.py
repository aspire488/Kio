import os, sys, time, psutil

for mod in list(sys.modules.keys()):
    if "mini_kio" in mod:
        del sys.modules[mod]

from mini_kio.core import config
for attr in ["GEMINI_ENABLED","GROQ_ENABLED","CEREBRAS_ENABLED","SAMBANOVA_ENABLED",
             "FIREWORKS_ENABLED","HUGGINGFACE_ENABLED","OPENROUTER_ENABLED",
             "TOGETHER_AI_ENABLED","FREELLMAPI_ENABLED"]:
    setattr(config, attr, False)
config.OLLAMA_ENABLED = True

import asyncio
from mini_kio.core.llm_router import _get_gateway, ask_llm

g = _get_gateway()
r = g.get_registry()
print("Chain:", r.get_providers())

py = psutil.Process()
m1 = py.memory_info()
oll = None
for p in psutil.process_iter(["pid","name","memory_info"]):
    try:
        if p.info["name"] and "ollama" in p.info["name"].lower():
            oll = p; break
    except:
        pass
o1 = oll.memory_info() if oll else None

queries = ["What is Python?","Explain gravity","Who wrote Hamlet?","What is AI?",
           "Capital of France","What is Docker?","Explain recursion",
           "What is blockchain?","Who is Einstein?","What is Linux?"] * 5

ok = fail = to = 0
lats = []
t0 = time.monotonic()

for i, q in enumerate(queries, 1):
    r.clear_diagnostics()
    s = time.monotonic()
    try:
        ans = asyncio.run(ask_llm(q + " One sentence.", timeout=30.0, max_tokens=64))
        lats.append((time.monotonic() - s) * 1000)
        if ans and len(ans) > 3:
            ok += 1
        else:
            fail += 1
    except asyncio.TimeoutError:
        to += 1; fail += 1
    except:
        fail += 1
    if i % 10 == 0:
        print(f"  {i}/50 ok={ok} fail={fail} to={to}")

tt = time.monotonic() - t0
m2 = py.memory_info()
o2 = oll.memory_info() if oll else None
cpu = py.cpu_percent(interval=0.5)

print()
print("STRESS TEST RESULTS")
print(f"  Successes:  {ok}")
print(f"  Failures:   {fail}")
print(f"  Timeouts:   {to}")
print(f"  Total time: {tt:.1f}s")
if lats:
    print(f"  Avg lat:    {sum(lats)/len(lats):.0f}ms")
    print(f"  Min lat:    {min(lats):.0f}ms")
    print(f"  Max lat:    {max(lats):.0f}ms")
rss_delta = abs(m2.rss - m1.rss) / 1024 / 1024
print(f"  Python RSS: {m1.rss/1024/1024:.1f} -> {m2.rss/1024/1024:.1f} MB (delta={rss_delta:.1f} MB)")
print(f"  Python VMS: {m1.vms/1024/1024:.1f} -> {m2.vms/1024/1024:.1f} MB")
if o1 and o2:
    print(f"  Ollama RSS: {o1.rss/1024/1024:.1f} -> {o2.rss/1024/1024:.1f} MB")
    print(f"  Ollama VMS: {o1.vms/1024/1024:.1f} -> {o2.vms/1024/1024:.1f} MB")
print(f"  Python CPU: {cpu:.1f}%")
print(f"  Chain:      {r.get_providers()}")
print(f"  State:      {r.get_state('ollama').value}")
print()
all_pass = (ok + fail == 50) and (tt < 600) and (rss_delta < 50) and (len(r.get_providers()) == 1)
print(f"PASS: no_crash={(ok+fail==50)} no_hang={tt<600} ram_stable={rss_delta<50} chain_ok={(len(r.get_providers())==1)}")
print(f"OVERALL: {'ALL PASS' if all_pass else 'FAIL'}")
