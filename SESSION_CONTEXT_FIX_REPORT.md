# SESSION — Conversational Continuity Fix (Discourse Override Session Loss)

## Root Cause

Live failure (reproduced through real Telegram after the previous session's
fixes):

```
USER:  what movie should I watch tonight
KIO:   I'd go with The Martian — ...
USER:  why did you prefer that one
KIO:   "I chose that option because it offers a straightforward, verifiable
        solution with minimal complexity..."   ← GENERIC, no referent
```

The previous session had already fixed the **G5 pronoun splice** (context
manager) — the math turns no longer stored `entity=6`, so "that" was no
longer spliced into "6". Routing was also correct: `DISCOURSE_OVERRIDE` sent
the message to CONVERSATION. Yet the LLM still answered with no referent.

The remaining defect was in `Pipeline._apply_discourse_context_override`
(`mini_kio/core/pipeline/__init__.py`):

- `run()` calls `classify()` → **then** sets `decision.session_id/channel/
  user_id` → **then** applies the discourse override.
- The override builds a **brand-new `RoutingDecision`** that only copied
  `metadata` — `session_id` defaulted to `"local_0"`.
- The conversational generator (`_chat_converse`) reads context via
  `get_session_context(decision.session_id)` → gets the **empty `local_0`
  session** instead of the user's session.
- Result: the "Recent conversation" section was **missing from the prompt**
  (verified by capturing the actual prompt — only "Known facts" and the
  discourse block were present), so the LLM answered with no prior context.

This also explains the earlier "sixth option" reply (the splice had made it
worse) and why the two live failures shared the same conversational-continuity
mechanism.

## Fix (canonical owner: `mini_kio/core/pipeline/__init__.py`)

`_apply_discourse_context_override` now copies `session_id`, `channel`, and
`user_id` from the original decision onto the replacement decision:

```python
return RoutingDecision(
    _IT.CONVERSATION, "converse", raw_text, raw_text, lower,
    confidence=0.65,
    session_id=decision.session_id,   # ← preserved
    channel=decision.channel,         # ← preserved
    user_id=decision.user_id,         # ← preserved
    metadata=dict(decision.metadata, discourse_override=True),
)
```

No routing changes — currentness research, entity lookups, and commands are
untouched.

## Verification

1. **In-process probe (prompt capture)**: before the fix, the prompt had no
   "Recent conversation" section; after the fix, the seeded history (including
   the movie recommendation) appears verbatim.
2. **In-process full pipeline**: `p.run("why did you prefer that one")` after
   a seeded Arrival recommendation → "I liked Arrival because its sci-fi
   premise is grounded in a genuine mystery…" (anchored, 2.2s).
3. **Live Telegram round trips** (Telethon user harness → real Bot API):
   - `what movie should I watch tonight` → The Martian (fresh, dynamic)
   - `why did you prefer that one` → **anchors on The Martian** ("…its plot
     revolves around concrete engineering problems…")
   - `would you still pick it tonight?` → stays on The Martian
   - `actually give me something darker instead` → Prisoners (no stale Chrome
     hijack)
   - `what's 6*7` → 42 · `6!` → 720 · `what exactly are you` → canonical
     identity
4. **Log evidence** (kio_bot_restart3.log): `[DISCOURSE_OVERRIDE] 'why did
   you prefer that one' -> CONVERSATION` fires, `CONTEXT_UPDATE` shows
   `entity=None` for both calculate and converse (the splice fix holds), and
   no `409` conflicts (single consumer).

## Focused tests

- `tests/test_discourse_context_routing.py` — added two tests:
  - `test_override_preserves_session_identity`: asserts the overridden
    decision keeps `session_id/channel/user_id` (the exact regression).
  - `test_override_history_reaches_conversational_prompt`: monkeypatches the
    LLM call and asserts the "Recent conversation" section (with the
    recommendation) reaches the prompt.
  - 32 passed (30 pre-existing + 2 new) in 1.98s.
- `tests/test_pronoun_splice_discourse_guard.py` (from the previous fix,
  6 tests) still passes — the two fixes are complementary: splice guard stops
  "that"→"6"; session preservation stops the empty-history generic answer.

## State

- KIO restarted (PID 28824 → killed; new instance owns port 9877, Telegram
  polling active, extension + Discord connected).
- One authoritative Telegram consumer (no webhook, zero 409s).
- Full suite NOT re-run (per instructions; baseline: 2414 passed / 90 failed
  / 3 skipped — the failures are pre-existing stale-format/environmental
  tests, not regressions from this work).
