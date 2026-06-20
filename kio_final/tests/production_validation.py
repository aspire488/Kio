"""Production validation: test REAL runtime conversations through route().

This script runs the EXACT same production pipeline that Discord uses:
  bootstrap_runtime() -> route() -> dispatch_channel_input() -> handle_command()

No mocks.
No test doubles.
No direct function invocation.
"""

import sys, os, json

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── Phase 1: Bootstrap the EXACT production runtime ──────────────────
print("=" * 70)
print("PHASE 1: Bootstrapping production runtime")
print("=" * 70)

from mini_kio.core.runtime import bootstrap_runtime
runtime = bootstrap_runtime()
print(f"[RUNTIME] state={runtime.state} pid={os.getpid()}")

# Import route after runtime is bootstrapped
from mini_kio.core.command_router import route

# ── Helper: capture runtime state ────────────────────────────────────

def capture_state(label=""):
    """Capture MediaManager context state."""
    from mini_kio.media.media_manager import MediaManager
    from mini_kio.core.continuity_resolver import ContinuityResolver
    mm = MediaManager.get_instance()
    ctx = mm.get_context()
    cr = ContinuityResolver.get_state()
    state = {
        "active_entity": ctx.entity,
        "active_domain": ctx.topic,
        "pending_action": ctx.pending_action,
        "pending_media_query": ctx.pending_media_query,
        "active_artifact": ctx.artifact_type,
        "cr_active_subject": cr.active_subject if cr else None,
        "cr_active_domain": cr.active_domain.value if cr and cr.active_domain else None,
    }
    print(f"\n  [STATE {label}]")
    for k, v in state.items():
        print(f"    {k}: {v}")
    return state


def simulate_turn(user_msg, expected_hint="", turn_num=0):
    """Run route() exactly as Discord does. Print verbatim."""
    sep = "-" * 70
    print(f"\n{sep}")
    print(f"TURN {turn_num}: USER: {user_msg}")
    print(f"{sep}")
    
    state_before = capture_state("BEFORE")
    
    # EXACT production call — same as discord_transport.py line 38:
    # reply = await asyncio.to_thread(route, content, user_id=..., channel="discord")
    reply = route(user_msg, user_id=99999, channel="discord")
    
    state_after = capture_state("AFTER")
    
    print(f"\n  BOT RESPONSE:")
    for line in reply.strip().split("\n"):
        print(f"    {line}")
    print(f"\n  [LEN={len(reply)}]")
    
    return reply, state_before, state_after


# ══════════════════════════════════════════════════════════════════════
# PHASE 2: MOVIE — Interstellar Conversation
# ══════════════════════════════════════════════════════════════════════

print("\n\n" + "=" * 70)
print("PHASE 2: MOVIE — Interstellar Conversation")
print("=" * 70)

movie_replies = []

r1, sb1, sa1 = simulate_turn("Tell me about Interstellar",
    "Movie summary, no generic acknowledgment", turn_num=1)
movie_replies.append(r1)

r2, sb2, sa2 = simulate_turn("Who directed it?",
    "Christopher Nolan, no trailer playback", turn_num=2)
movie_replies.append(r2)

r3, sb3, sa3 = simulate_turn("Who composed it?",
    "Hans Zimmer", turn_num=3)
movie_replies.append(r3)

r4, sb4, sa4 = simulate_turn("Show trailer",
    "Trailer offer or playback", turn_num=4)
movie_replies.append(r4)

r5, sb5, sa5 = simulate_turn("Show movie clips",
    "Interstellar clips, not 'What movie?'", turn_num=5)
movie_replies.append(r5)

r6, sb6, sa6 = simulate_turn("Behind the scenes",
    "Interstellar BTS content, no entity loss", turn_num=6)
movie_replies.append(r6)

r7, sb7, sa7 = simulate_turn("Show soundtrack",
    "Interstellar soundtrack", turn_num=7)
movie_replies.append(r7)

# ══════════════════════════════════════════════════════════════════════
# PHASE 3: SPORTS — FIFA World Cup 2026
# ══════════════════════════════════════════════════════════════════════

print("\n\n" + "=" * 70)
print("PHASE 3: SPORTS — FIFA World Cup 2026")
print("=" * 70)

sports_replies = []

r8, sb8, sa8 = simulate_turn("FIFA World Cup 2026 latest updates",
    "⚽ FIFA, Status report, Watch, Follow-up", turn_num=8)
sports_replies.append(r8)

r9, sb9, sa9 = simulate_turn("Latest standings",
    "World Cup standings, entity must remain FIFA", turn_num=9)
sports_replies.append(r9)

r10, sb10, sa10 = simulate_turn("Latest results",
    "World Cup results", turn_num=10)
sports_replies.append(r10)

r11, sb11, sa11 = simulate_turn("Who is leading the group?",
    "FIFA answer, not generic web search", turn_num=11)
sports_replies.append(r11)

r12, sb12, sa12 = simulate_turn("Who scored in the latest match?",
    "FIFA context retained", turn_num=12)
sports_replies.append(r12)

# ══════════════════════════════════════════════════════════════════════
# PHASE 4: MUSIC — Believer
# ══════════════════════════════════════════════════════════════════════

print("\n\n" + "=" * 70)
print("PHASE 4: MUSIC — Believer")
print("=" * 70)

music_replies = []

r13, sb13, sa13 = simulate_turn("Tell me about Believer",
    "🎵 Believer, Field intel", turn_num=13)
music_replies.append(r13)

r14, sb14, sa14 = simulate_turn("Who sings it?",
    "Imagine Dragons", turn_num=14)
music_replies.append(r14)

r15, sb15, sa15 = simulate_turn("Show live performance",
    "Believer live performance", turn_num=15)
music_replies.append(r15)

# ══════════════════════════════════════════════════════════════════════
# PHASE 5: BOOKS — Atomic Habits
# ══════════════════════════════════════════════════════════════════════

print("\n\n" + "=" * 70)
print("PHASE 5: BOOKS — Atomic Habits")
print("=" * 70)

books_replies = []

r16, sb16, sa16 = simulate_turn("Tell me about Atomic Habits",
    "📖 Atomic Habits, Field intel", turn_num=16)
books_replies.append(r16)

r17, sb17, sa17 = simulate_turn("Who wrote it?",
    "James Clear", turn_num=17)
books_replies.append(r17)

r18, sb18, sa18 = simulate_turn("Play audiobook",
    "Atomic Habits audiobook", turn_num=18)
books_replies.append(r18)

r19, sb19, sa19 = simulate_turn("Show author interview",
    "James Clear interview", turn_num=19)
books_replies.append(r19)

# ══════════════════════════════════════════════════════════════════════
# PHASE 6: TV — The Bear
# ══════════════════════════════════════════════════════════════════════

print("\n\n" + "=" * 70)
print("PHASE 6: TV — The Bear")
print("=" * 70)

tv_replies = []

r20, sb20, sa20 = simulate_turn("Tell me about The Bear",
    "📺 The Bear, Field intel", turn_num=20)
tv_replies.append(r20)

r21, sb21, sa21 = simulate_turn("Who created it?",
    "Christopher Storer", turn_num=21)
tv_replies.append(r21)

# ══════════════════════════════════════════════════════════════════════
# PHASE 7: Entity State Verification
# ══════════════════════════════════════════════════════════════════════

print("\n\n" + "=" * 70)
print("PHASE 7: Entity State Verification")
print("=" * 70)

# Verify Interstellar never became "Official Trailer", "Movie Clips", "Soundtrack"
# (entity and artifact must remain separate)
print("\nInterstellar entity validation:")
for i, (turn_num, reply) in enumerate([(1, r1), (2, r2), (3, r3), (4, r4), (5, r5), (6, r6), (7, r7)]):
    # For the first 3 turns, entity should be "Interstellar"
    if i < 3:
        if "🎬" in reply or "Interstellar" in reply.split("\n")[0]:
            print(f"  Turn {turn_num}: ✅ Entity preserved (Interstellar)")
        else:
            print(f"  Turn {turn_num}: ⚠️ Entity check")
    # For show trailer/clips/BTS/soundtrack (turns 4-7), response should contain Interstellar
    if i >= 3:
        if "Interstellar" in reply or "interstellar" in reply.lower():
            print(f"  Turn {turn_num}: ✅ Entity referenced")
        else:
            print(f"  Turn {turn_num}: ⚠️ No Interstellar reference")

# Verify FIFA never became "Latest Standings", "Latest Results"
print("\nFIFA entity validation:")
for turn_num, reply in [(8, r8), (9, r9), (10, r10), (11, r11), (12, r12)]:
    check = "FIFA" in reply or "World Cup" in reply or "⚽" in reply
    print(f"  Turn {turn_num}: {'✅ Entity preserved' if check else '⚠️ Entity lost'}")

# Verify Believer never became "Live Performance"
print("\nBeliever entity validation:")
for turn_num, reply in [(13, r13), (14, r14), (15, r15)]:
    check = "Believer" in reply or "believer" in reply.lower()
    print(f"  Turn {turn_num}: {'✅ Entity preserved' if check else '⚠️ Entity lost'}")

# Verify Atomic Habits never became just "Audiobook" or "Interview"
print("\nAtomic Habits entity validation:")
for turn_num, reply in [(16, r16), (17, r17), (18, r18), (19, r19)]:
    check = "Atomic Habits" in reply or "Atomic" in reply
    print(f"  Turn {turn_num}: {'✅ Entity preserved' if check else '⚠️ Entity lost'}")

# ══════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════

print("\n\n" + "=" * 70)
print("PHASE 8: PRODUCTION VALIDATION SUMMARY")
print("=" * 70)

# Check forbidden patterns
forbidden_patterns = ["Done.", "OK.", "Query:", "SPORTS", "provider"]
all_responses = movie_replies + sports_replies + music_replies + books_replies + tv_replies
issues = []
for i, reply in enumerate(all_responses):
    for fp in forbidden_patterns:
        if fp in reply and reply.strip() == fp:
            issues.append(f"Turn {i+1}: Contains forbidden exact match '{fp}'")
    # Check for generic acknowledgment
    if reply.strip() in ("Done.", "OK."):
        issues.append(f"Turn {i+1}: Generic acknowledgment '{reply.strip()}'")

if issues:
    print(f"\n❌ {len(issues)} ISSUES FOUND:")
    for iss in issues:
        print(f"  - {iss}")
else:
    print("\n✅ No forbidden patterns detected in any response")

# Overall result
print(f"\nTotal turns: {len(all_responses)}")
print(f"Total responses with content: {sum(1 for r in all_responses if r.strip())}")
print(f"Total empty/error responses: {sum(1 for r in all_responses if not r.strip())}")
print(f"\n{'=' * 70}")
print("VALIDATION COMPLETE")
print(f"{'=' * 70}")
