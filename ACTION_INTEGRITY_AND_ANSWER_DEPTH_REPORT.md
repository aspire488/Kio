# Action Integrity + Answer Depth + Proactive Orchestration — Final Report

## Live failures reproduced (from real Telegram transcripts)

| Message | Before | Root cause |
|---|---|---|
| `show me the trailer` (after Marvel/Dune media answer) | `https://www.youtube.com/watch?v=example-trailer-id` — **fabricated URL** | routed to CONVERSATION; the LLM hallucinated a resource during synthesis |
| `what's the capital of Japan` | tourism paragraph about Kyoto/Osaka/cherry blossoms — **never named Tokyo** | composer summarized "about {subject}" instead of answering the actual question |
| `who wrote the book Dune` | `I don't have information on book Dune yet` | `_is_relevant` role-stem bypass had "writ" but not the inflected "wrote" → correctly retrieved author page REJECTED → stub fallback |
| `yeah show me the trailer` | fabricated URL | confirmation + noun phrase fell to conversation; accept_offer only matched bare "show it"/"watch it" |
| media queries (Marvel/Dune) | no proactive offer possible | `offer_media()` was **dead code** — the whole opportunity loop (detect → surface → accept → play) was never wired |

## Canonical owners fixed (mechanisms, not examples)

| Owner | File | Fix |
|---|---|---|
| Action-intent routing | `mini_kio/core/pipeline/__init__.py` | "show/display/open + concrete media noun" (`trailer`, `highlights`, `interview`, `clip`, ...) → **accept_offer** action path, never conversation. Both accept_offer exec paths (media + conversation) now fall back to **genuinely search+play** a real provider resource when no pending offer exists, composing `<offer topic> <user noun>` as the query |
| Fabrication guard | `mini_kio/core/pipeline/__init__.py` | converse prompt now forbids inventing URLs/IDs/paths/resources: "NEVER invent URLs... A fake link is worse than saying you'll pull it up — never fabricate one." |
| Answer-first contract | `mini_kio/media/intelligence/answer_composer.py` | composer prompt now includes `The user's question was: {query!r}` and requires answering THAT question DIRECTLY first, then optional color — no more tourism padding around a simple fact |
| Role-stem relevance | `mini_kio/media/intelligence/integration_adapter.py` | `_is_relevant` role-stem bypass extended to inflected forms (`wrote`, `written`, `author`, `director`, `composer`, `producer`, `directed`, ...) so role questions accept the person's page |
| Proactive loop (was dead code) | `mini_kio/media/media_discovery.py`, `mini_kio/core/pipeline/__init__.py`, `mini_kio/media/media_manager.py` | `offer_media()` wired after topic answers (bounded: never after verification/claims, cooldown per topic); opportunity keywords tightened to media-SEEKING intent (bare "what is"/"explain" removed — no video offer after general questions); templates reworded to natural KIO voice |
| "Bottom line:" template | `mini_kio/media/intelligence/integration_adapter.py` | verification synthesis prompt no longer instructs "Start with the bottom line" — verdict must be natural, never a fixed label |

## Live Telegram validation (new unseen conversations, real round trips)

**Session A — simple facts**
- `what's the capital of Japan` → **"Tokyo."** first, one sentence of context — no tourism paragraph
- `who wrote the book Dune` → **"written by Frank Herbert"** first — no more stub
- `what's 17*8` → **136** (deterministic, no web)

**Session B — recommendation continuity**
- `recommend me a sci-fi book` → Three-Body Problem (POV + rationale)
- `give me something darker` → Blindsight (dynamic refinement)
- `would you still pick that one` → stays on Blindsight (callback)
- `what exactly are you` → canonical identity ("KIO — Kernel for Intelligent Orchestration...")

**Session C/D — media + action integrity (the critical test)**
- `what's the latest on the new Dune movie` → current synthesis + **restrained offer**: "There's an official trailer if you want to see what it actually looks like — want me to pull it up?"
- `show me the trailer` → **real execution**: `[PROACTIVE_OFFER]` → `accept_offer` → `MEDIA_CONTEXT_RESOLVE artifact=trailer` → YouTube provider `FINAL_RETURN playback_state=playing success=True` → "Playing Dune Official Trailer." — **no fabricated URL**

**Session E — rapid topic switching** — book → math → identity, each correctly routed with no contamination.

## Log evidence (runtime, not assertion)

```
[PROACTIVE_OFFER] topic=what's the latest on the new Dune movie media_type=movie_trailer
[MEDIA_CONTEXT_RESOLVE] artifact=trailer query=Dune official trailer trigger=show me the trailer
[ROOT_YT] FINAL_RETURN playback_state=playing success=True message=Playing Dune Official Trailer.
[CLAIMS_CONSUMED] session=tg_2146008061 route=accept_offer (topic move)
```

## Focused tests

`tests/test_action_intent_and_answer_depth.py` (7 new) + proactive/verification/discourse suites: **66 passed** in the focused set. Full suite NOT re-run (per instruction); baseline 2414/90/3 unchanged, those 90 pre-existing.

## Why the previous fix was insufficient

Earlier sessions fixed the *proposition lifecycle* (session-scoped claims, consumption) — routing and evidence now work. But the transcript exposed two orthogonal systemic failures: (1) **action requests fell to the LLM** which fabricated resources instead of executing the real capability, and (2) **answer depth was uncontrolled** — simple facts produced essays/stubs. Both were owners in the routing/synthesis layer, now fixed at the classifier and composer.

## Remaining genuine limitations

- The media accept path depends on provider search quality; if the provider returns nothing relevant, the fallback reports the honest no-pending-offer state rather than a fabricated result.
- Answer depth is prompt-contract driven (LLM-following); a fully deterministic depth classifier per question class is a possible future hardening but risks re-introducing template rules.
- Proactive offers fire on media/current-topic queries with opportunity keywords; cross-domain (Python learning, travel) proactivity uses the same generic opportunity model but is not yet live-validated in this session.
