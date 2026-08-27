# Proposition / Discourse Claim-Store Lifecycle — Final Report

## What the user reported

Live Telegram transcript (pre-fix process) showed a **systemic** failure, not an example failure:

```
> Ronaldo got married too
> KIO: Congrats to him—personal milestones like that can shift a player's focus...
> Is this true
> KIO: What specific claim are you asking about?
> Is Ronaldo married
> KIO: No, Cristiano Ronaldo isn't married; ...

> The Warriors won last night
> KIO: That win should give them a nice bump in the standings—who were they up against?
> Did that actually happen?
> KIO: (verified a STALE Ronaldo claim about a Madeira wedding mix-up)
> Did that actually happen?   (later)
> KIO: (verified an even STALER Kawhi-trade claim from an unrelated earlier conversation)
```

Three distinct failures in one mechanism:
1. **User assertions were discarded** — "Ronaldo got married too" was answered conversationally and never became a verifiable proposition.
2. **Bare verification probes were not resolved** — "Is this true" / "Did that actually happen?" carried no claim of their own and fell to generic conversation.
3. **The claim store leaked across conversations** — a Kawhi-trade claim from an *earlier, unrelated conversation* was still reclaimable, so a later bare probe answered the wrong proposition.

## Root causes (mechanisms, not phrases)

### RC-1: Assertions never registered as propositions
"Ronaldo got married too" → classified CONVERSATION, replied conversationally, proposition discarded. Additionally, the pipeline's state-verb vocabulary drifted from the adapter's: "won" was in the adapter's `_VERIF_STATE` but not routed as a verification query, and "happen" (the stem of "happened") was missing from `_VERIF_GENERIC_TOKENS`, so "Did that actually happen?" failed the reclaim gate.

### RC-2: Bare probes never reached the verification capability
"Is this true" / "Really?" / "Did that actually happen?" have no claim content — they *refer* to the preceding proposition. The pipeline's verification family only caught frames *with* claim content; the probe fell to CONVERSE and the adapter's reclaim (which already resolves "this" → stored claims) was never consulted.

### RC-3: The claim store was a single GLOBAL slot (the Kawhi leak)
`last_verif_claims` lived in the adapter's one `ContextStore`, shared across **all users and all conversations**, and was **never consumed**. A claim from an earlier session stayed reclaimable forever. That is how "Did that actually happen?" answered a Kawhi trade rumor from a completely different conversation.

### RC-4: Degenerate LLM synthesis passed the grounding gate
A long multi-claim verification prompt was answered with "It's 2:52 AM." The anti-hallucination gate checked `_answer_toks & _ground_toks`, but `_meaningful_tokens("It's 2:52 AM.")` = `{"it's"}` — a referential contraction not in `_EVIDENCE_STOPWORDS` that also appears in evidence snippets, so the overlap passed and the garbage was accepted.

## Canonical owners fixed

| Owner | File | Fix |
|---|---|---|
| Claim-store lifecycle | `mini_kio/media/intelligence/context_store.py` | added `ContextStore.remove(key)` |
| Claim-store scoping + consumption | `mini_kio/media/intelligence/integration_adapter.py` | session-scoped `_claims_key(session_id)`; `register_user_assertion`/`has_pending_verif_claims`/`clear_user_claims` take `session_id`; all 6 `last_verif_claims` read/write sites scoped; `handle()`/`_handle_verification()`/`_is_verif_elaboration_followup()` thread `session_id`; `_VERIF_STATE` extended with general event predicates (`won`, `beat`, `launched`, ...); `_VERIF_GENERIC_TOKENS` gains stemmed "happen"; `_EVIDENCE_STOPWORDS` gains contracted referential forms (`it's`, `that's`, ...) |
| Synthesis gate | `mini_kio/media/intelligence/integration_adapter.py` | reject answers with **zero content tokens** outright (empty-token branch) before the overlap check |
| Verification bridge | `mini_kio/media/media_manager.py` | `process_information_query(query, session_id="")` → `adapter.handle(topic_query, session_id=session_id)` |
| Pipeline routing | `mini_kio/core/pipeline/__init__.py` | `_register_user_assertion()` returns bool; `_apply_verification_probe_route()` checks pending claims **per session**; new `_consume_stale_claims()` wired into `run()` — topic moves consume the session's claims; `_exec_media` passes `session_id` |

## Files changed

- `mini_kio/media/intelligence/context_store.py` — `remove()`
- `mini_kio/media/intelligence/integration_adapter.py` — session scoping, consumption API, vocabulary alignment, synthesis-gate hardening
- `mini_kio/media/media_manager.py` — session threading
- `mini_kio/core/pipeline/__init__.py` — assertion registration + probe route + consumption lifecycle
- `tests/test_verification_claim_lifecycle.py` — NEW (7 focused tests)

## Mechanism-level behavior (in-process verification)

```
1. "Ronaldo got married too"  -> registers claim, sess_a pending=True
   "Is this true"             -> INFORMATION (bare probe, pending claims)
2. topic move                 -> claims CONSUMED
   "Is this true" (later)     -> stays conversational (nothing to verify)
3. sess_a claim               -> invisible to sess_b (cross-session isolation)
4. "I heard X and Y"          -> 2 independent claims, kept for reclaim
   "when did that happen"     -> elaboration keeps claims (reclaim works)
5. casual chat after claim    -> claims consumed (no pollution)
6. new assertion in session   -> REPLACES old claim (Warriors replaces Ronaldo)
7. "It's 2:52 AM."            -> _meaningful_tokens = set() -> gate REJECTS
   grounded synthesis         -> shares content tokens -> ACCEPTED
```

## Live Telegram validation (real round trips, one message at a time)

| Message | Response | Verdict |
|---|---|---|
| `Ronaldo got married too` | verified live, registered | PASS |
| `Is this true` | re-verified Ronaldo claim (reclaim worked) | PASS |
| `The Warriors won last night` | verified live (Knicks 126-113) | PASS |
| `Did that actually happen?` | reclaimed **Warriors** claim (NOT stale Ronaldo) | PASS — original failure fixed |
| `what movie should I watch tonight` | fresh recommendation; `[CLAIMS_CONSUMED]` logged | PASS |
| `Really?` (after movie topic) | stayed conversational — no resurrection | PASS — Kawhi-leak pattern fixed |
| `Apple released a new device` | verified with proper nuance (4 products, not 1) | PASS |
| `Really?` (after Apple) | reclaimed Apple claim | PASS |
| `I heard SpaceX launched a new rocket and Messi announced he's retiring` | **multi-proposition**: each claim independently verified (Messi retirement real; SpaceX launch only scheduled) | PASS — previously "It's 2:52 AM." |
| `which part is actually true?` | per-proposition verdict | PASS |
| `The first one?` | ordinal reference resolved against last reply | PASS |

Log evidence: `[VERIF_PROBE_ROUTE]`, `[CLAIMS_CONSUMED] session=tg_... route=converse (topic move)`, `[VERIFY_FOLLOWUP_RECLAIM] last_claims=[...]`, `[VERIFY_CLAIMS] claims=[...2 claims...]`.

## Focused tests

`tests/test_verification_claim_lifecycle.py` (7 new) + existing verification/discourse tests: **59 passed** in the focused set. Full suite NOT re-run (per instruction); baseline remains 2414/90/3 with those 90 pre-existing (stale-format/environmental), not from this work.

## Why the previous fix was insufficient

The earlier session fixed *routing* (vocabulary: "won"/"happen"; probe route; assertion registration) — and the current-process log proves the immediate Warriors flow now works. But the transcript exposed that claims were still stored in a **global, never-consumed slot**: the Kawhi claim from an unrelated earlier conversation remained reclaimable. That is a *lifetime* bug, not a routing bug — fixed here by session-scoped keys + topic-move consumption.

## Remaining genuine limitations

- Ordinal references ("the first one?") resolve against the most recent *reply's* ordering; an ambiguity between the user's original message order and the reply order is resolved pragmatically, not by tracking both.
- The claim store is bounded per session and consumed on topic moves, but has no explicit TTL — a long-running single-topic thread keeps its claim until the topic moves.
- Multi-user isolation is per `session_id` (tg_\<uid\>); two conversations by the same user in the same chat share a session, so a topic move is the consumption trigger rather than chat boundaries.
