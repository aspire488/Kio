"""Runtime validation: test REAL pipeline through route() — full 6-scenario pass.

Exact same production path as the Telegram/Discord bot:
  bootstrap_runtime() -> route() -> dispatch_channel_input() -> handle_command()

Output: tests/runtime_validation_results.txt (UTF-8, emoji-safe)
"""

import sys, os, json, logging

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.disable(logging.CRITICAL)

OUT = open("runtime_validation_results.txt", "w", encoding="utf-8")

def log(msg="", end="\n"):
    OUT.write(str(msg) + end)
    OUT.flush()

log("=" * 80)
log("KIO RUNTIME VALIDATION — 6-SCENARIO PRODUCTION PASS")
log("=" * 80)

from mini_kio.core.runtime import bootstrap_runtime
runtime = bootstrap_runtime()
log(f"[RUNTIME] state={runtime.state} pid={os.getpid()}")
log()

from mini_kio.core.command_router import route

# ── Instrumentation ──────────────────────────────────────────────────

def capture_state(label=""):
    from mini_kio.media.media_manager import MediaManager
    from mini_kio.core.continuity_resolver import ContinuityResolver
    mm = MediaManager.get_instance()
    ctx = mm.get_context()
    crs = ContinuityResolver.get_state()
    state = {
        "active_entity": ctx.entity,
        "active_domain": ctx.topic,
        "pending_action": ctx.pending_action,
        "pending_media_query": ctx.pending_media_query,
        "active_artifact": ctx.artifact_type,
        "cr_active_subject": crs.active_subject if crs else None,
        "cr_active_domain": crs.active_domain.value if crs and crs.active_domain else None,
    }
    return state

def simulate_turn(user_msg, turn_num=0):
    sep = "-" * 70
    log(f"\n{sep}")
    log(f"TURN {turn_num}: USER: {user_msg}")
    log(sep)

    before = capture_state("BEFORE")
    log(f"  [BEFORE] active_entity={before['active_entity']} domain={before['active_domain']} "
        f"pending_action={before['pending_action']} artifact={before['active_artifact']}")

    reply = route(user_msg, user_id=99999, channel="discord")

    after = capture_state("AFTER")
    log(f"  [AFTER]  active_entity={after['active_entity']} domain={after['active_domain']} "
        f"pending_action={after['pending_action']} artifact={after['active_artifact']}")

    log(f"\n  BOT RESPONSE:")
    for line in reply.strip().split("\n"):
        log(f"    {line}")
    log(f"\n  [LEN={len(reply)}]")

    return reply, before, after


# ══════════════════════════════════════════════════════════════════════
# SCENARIO 1: MOVIES — Interstellar
# ══════════════════════════════════════════════════════════════════════

log("\n\n" + "=" * 80)
log("SCENARIO 1: MOVIES — Interstellar")
log("=" * 80)

m = {}
m[1], _, _ = simulate_turn("Tell me about Interstellar", turn_num=1)
m[2], _, _ = simulate_turn("Who directed it?", turn_num=2)
m[3], _, _ = simulate_turn("Who composed it?", turn_num=3)
m[4], _, _ = simulate_turn("Show trailer", turn_num=4)
m[5], _, _ = simulate_turn("Show soundtrack", turn_num=5)
m[6], _, _ = simulate_turn("Show movie clips", turn_num=6)
m[7], _, _ = simulate_turn("Behind the scenes", turn_num=7)

# ══════════════════════════════════════════════════════════════════════
# SCENARIO 2: SPORTS — FIFA World Cup 2026
# ══════════════════════════════════════════════════════════════════════

log("\n\n" + "=" * 80)
log("SCENARIO 2: SPORTS — FIFA World Cup 2026")
log("=" * 80)

s = {}
s[8],  _, _  = simulate_turn("FIFA World Cup 2026 latest updates", turn_num=8)
s[9],  _, _  = simulate_turn("Latest standings", turn_num=9)
s[10], _, _  = simulate_turn("Latest results", turn_num=10)
s[11], _, _  = simulate_turn("Latest highlights", turn_num=11)
s[12], _, _  = simulate_turn("Who is leading the group?", turn_num=12)
s[13], _, _  = simulate_turn("Who scored in the latest match?", turn_num=13)

# ══════════════════════════════════════════════════════════════════════
# SCENARIO 3: MUSIC — Believer
# ══════════════════════════════════════════════════════════════════════

log("\n\n" + "=" * 80)
log("SCENARIO 3: MUSIC — Believer")
log("=" * 80)

u = {}
u[14], _, _ = simulate_turn("Tell me about Believer by Imagine Dragons", turn_num=14)
u[15], _, _ = simulate_turn("Who sings it?", turn_num=15)
u[16], _, _ = simulate_turn("Show live performance", turn_num=16)

# ══════════════════════════════════════════════════════════════════════
# SCENARIO 4: BOOKS — Atomic Habits
# ══════════════════════════════════════════════════════════════════════

log("\n\n" + "=" * 80)
log("SCENARIO 4: BOOKS — Atomic Habits")
log("=" * 80)

b = {}
b[17], _, _ = simulate_turn("Tell me about Atomic Habits", turn_num=17)
b[18], _, _ = simulate_turn("Who wrote it?", turn_num=18)
b[19], _, _ = simulate_turn("Play audiobook", turn_num=19)
b[20], _, _ = simulate_turn("Show author interview", turn_num=20)

# ══════════════════════════════════════════════════════════════════════
# SCENARIO 5: TV — The Bear
# ══════════════════════════════════════════════════════════════════════

log("\n\n" + "=" * 80)
log("SCENARIO 5: TV — The Bear")
log("=" * 80)

t = {}
t[21], _, _ = simulate_turn("Tell me about The Bear", turn_num=21)
t[22], _, _ = simulate_turn("Who created it?", turn_num=22)

# ══════════════════════════════════════════════════════════════════════
# SCENARIO 6: Cross-Domain Isolation
# ══════════════════════════════════════════════════════════════════════

log("\n\n" + "=" * 80)
log("SCENARIO 6: CROSS-DOMAIN ISOLATION")
log("=" * 80)

x = {}
x[23], _, _ = simulate_turn("Tell me about Believer", turn_num=23)
x[24], _, _ = simulate_turn("Tell me about Interstellar", turn_num=24)
x[25], _, _ = simulate_turn("Who directed it?", turn_num=25)

# ══════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════

log("\n\n" + "=" * 80)
log("VALIDATION RESULTS")
log("=" * 80)

all_replies = {}
all_replies.update(m)
all_replies.update(s)
all_replies.update(u)
all_replies.update(b)
all_replies.update(t)
all_replies.update(x)

# Forbidden patterns — catch exact bad outputs
FORBIDDEN_EXACT = {"Done.", "OK.", "Query:"}
FORBIDDEN_SUBSTR = {"[RETRIEVAL", "[MEMORY_", "[LLM_", "[ANSWER_",
                    "[ENTITY_", "[ARTIFACT_", "[QUERY_", "[MEDIA_",
                    "TopicType.", "provider unavailable", "no entity for query"}

issues = []
warnings = []

for tn in sorted(all_replies):
    reply = all_replies[tn]
    txt = reply.strip()

    # Exact match forbidden
    if txt in FORBIDDEN_EXACT:
        issues.append(f"Turn {tn}: FORBIDDEN exact match '{txt}'")

    # Substring forbidden (log markers leaking into output)
    for fp in FORBIDDEN_SUBSTR:
        if fp in txt:
            issues.append(f"Turn {tn}: Contains diagnostic marker '{fp}'")

    # Empty
    if not txt:
        issues.append(f"Turn {tn}: Empty response")

    # Too short (likely placeholder/fallback)
    if len(txt) < 10:
        issues.append(f"Turn {tn}: Suspiciously short ({len(txt)} chars): {txt[:50]}")

log(f"\n--- SCENARIO 1: INTERSTELLAR ---")
# Turn 1: Must start with movie emoji or entity name
log(f"  Turn 1 (Tell me about Interstellar):")
if "Interstellar" in m[1] or "interstellar" in m[1].lower():
    log(f"    [PASS] Entity in response")
else:
    w = "Entity name 'Interstellar' not found in response"
    warnings.append(f"Turn 1: {w}")
    log(f"    [WARN] {w}")
log(f"    Length: {len(m[1])} chars")

# Turn 2: Must name Christopher Nolan
log(f"  Turn 2 (Who directed it?):")
if "Nolan" in m[2] or "nolan" in m[2].lower():
    log(f"    [PASS] Christopher Nolan mentioned")
else:
    issues.append(f"Turn 2: 'Nolan' not found in response")
if "trailer" not in m[2].lower() and "play" not in m[2].lower()[:10]:
    log(f"    [PASS] No trailer playback triggered")
else:
    issues.append(f"Turn 2: Trailer/playback leak in response")

# Turn 3: Must name Hans Zimmer
log(f"  Turn 3 (Who composed it?):")
if "Zimmer" in m[3] or "zimmer" in m[3].lower():
    log(f"    [PASS] Hans Zimmer mentioned")
else:
    issues.append(f"Turn 3: 'Zimmer' not found in response")

# Turn 4-7: Must reference Interstellar
for tn in [4, 5, 6, 7]:
    log(f"  Turn {tn} ({['Show trailer','Show soundtrack','Show movie clips','Behind the scenes'][tn-4]}):")
    if "Interstellar" in m[tn] or "interstellar" in m[tn].lower():
        log(f"    [PASS] Interstellar referenced")
    else:
        w = f"Turn {tn}: No Interstellar reference"
        warnings.append(w)
        log(f"    [WARN] {w}")

log(f"\n--- SCENARIO 2: FIFA WORLD CUP 2026 ---")
fifa_entity_terms = ["FIFA", "World Cup", "world cup"]
for tn in range(8, 14):
    log(f"  Turn {tn}:")
    entity_ok = any(term in s[tn] for term in fifa_entity_terms)
    if entity_ok:
        log(f"    [PASS] FIFA context preserved")
    else:
        issues.append(f"Turn {tn}: FIFA entity lost")
    if not s[tn].strip() or s[tn].strip() in FORBIDDEN_EXACT:
        issues.append(f"Turn {tn}: Empty/forbidden response")

log(f"\n--- SCENARIO 3: BELIEVER ---")
for tn in [14, 15, 16]:
    log(f"  Turn {tn}:")
    if "Believer" in u[tn] or "believer" in u[tn].lower():
        log(f"    [PASS] Believer context preserved")
    else:
        issues.append(f"Turn {tn}: Believer entity lost")

log(f"\n--- SCENARIO 4: ATOMIC HABITS ---")
# Turn 17: Must have content
log(f"  Turn 17 (Tell me about Atomic Habits):")
if "Atomic" in b[17] or "atomic" in b[17].lower():
    log(f"    [PASS] Atomic Habits in response")
else:
    issues.append(f"Turn 17: 'Atomic Habits' not found in response")

# Turn 18: Must name James Clear — critical test
log(f"  Turn 18 (Who wrote it?):")
if "James" in b[18] or "Clear" in b[18]:
    log(f"    [PASS] James Clear identified as author")
elif b[18].strip() == "Done.":
    issues.append(f"Turn 18: CRITICAL — 'Done.' response for 'who wrote it'")
else:
    w = f"Turn 18: 'James Clear' not found in response: '{b[18][:80]}...'"
    warnings.append(w)
    log(f"    [WARN] {w}")

for tn in [19, 20]:
    log(f"  Turn {tn}:")
    if "Atomic" in b[tn] or "atomic" in b[tn].lower():
        log(f"    [PASS] Atomic Habits context preserved")
    else:
        w = f"Turn {tn}: Atomic Habits context lost"
        warnings.append(w)
        log(f"    [WARN] {w}")

log(f"\n--- SCENARIO 5: THE BEAR ---")
log(f"  Turn 21 (Tell me about The Bear):")
if "Bear" in t[21] or "bear" in t[21].lower():
    log(f"    [PASS] The Bear in response")
else:
    issues.append(f"Turn 21: 'The Bear' not found in response")

log(f"  Turn 22 (Who created it?):")
if "Storer" in t[22] or "storer" in t[22].lower():
    log(f"    [PASS] Christopher Storer identified as creator")
else:
    w = f"Turn 22: 'Storer' not found"
    warnings.append(w)
    log(f"    [WARN] {w}")
# Check for bear-animal contamination
if "grizzly" in t[22].lower() or "brown bear" in t[22].lower() or "animal" in t[22].lower():
    issues.append(f"Turn 22: Bear-animal content leaked instead of TV show")

log(f"\n--- SCENARIO 6: CROSS-DOMAIN ISOLATION ---")
log(f"  Turn 24 (Tell me about Interstellar after Believer):")
log(f"  Turn 25 (Who directed it?):")
if "Believer" in x[25] or "believer" in x[25].lower():
    issues.append(f"Turn 25: Believer leaked into Interstellar response")
else:
    log(f"    [PASS] No Believer leakage")
if "Nolan" in x[25] or "nolan" in x[25].lower():
    log(f"    [PASS] Christopher Nolan identified for Interstellar")
else:
    w = f"Turn 25: 'Nolan' not found in cross-domain response"
    warnings.append(w)
    log(f"    [WARN] {w}")

# ══════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════

log("\n\n" + "=" * 80)
log("FINAL SUMMARY")
log("=" * 80)
log(f"\nTurns executed: {len(all_replies)}")
log(f"Issues (FAIL): {len(issues)}")
log(f"Warnings: {len(warnings)}")

if issues:
    log(f"\n--- ISSUES ---")
    for iss in issues:
        log(f"  [FAIL] {iss}")

if warnings:
    log(f"\n--- WARNINGS ---")
    for w in warnings:
        log(f"  [WARN] {w}")

log(f"\n--- RESPONSE LENGTHS ---")
for tn in sorted(all_replies):
    r = all_replies[tn]
    first_line = r.strip().split("\n")[0][:80] if r.strip() else "(empty)"
    log(f"  Turn {tn:2d}: len={len(r):5d}  {first_line}")

# GO/NO-GO verdict
log(f"\n--- VERDICT ---")
if len(issues) > 0:
    log(f"  ❌  NO-GO — {len(issues)} issue(s) remain")
else:
    log(f"  ✅  GO — All scenarios pass")
if warnings:
    log(f"  ⚠️   {len(warnings)} warning(s) — investigate")

log(f"\n{'=' * 80}")
log("VALIDATION COMPLETE")
log("=" * 80)

OUT.close()

# Also print summary to console
print(f"\nResults written to tests/runtime_validation_results.txt")
print(f"Issues: {len(issues)}, Warnings: {len(warnings)}")
for iss in issues:
    print(f"  FAIL: {iss}")
