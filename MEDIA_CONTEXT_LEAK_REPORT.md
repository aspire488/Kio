# MEDIA_CONTEXT_LEAK_REPORT.md

## Symptom
`Play Interstellar trailer` → `Couldn't play Godha on YouTube` (stale entity leak).

## Root Cause (traced end-to-end)
1. `MediaManager.play()` lowers+strips the verb before calling
   `_intelligence_adapter.handle("interstellar trailer", execute=False)`.
2. `ContinuityEngine.is_followup()` matches `_SHOW_ARTIFACT` ("trailer") → calls
   `_has_different_entity("interstellar trailer")`.
3. In `_has_different_entity`, all-lowercase input → `content = {"interstellar"}`
   (trailer removed as artifact keyword), but the guard required `len(content) >= 2` →
   returned False → treated as followup → resolved to the previous entity "Godha".
4. Second, identical guard in `IntegrationAdapter._is_continuation_query` required
   `len(words) > 2`, so a 2-word query ("interstellar trailer") also fell through to
   `bool(ref_words & query_words)` → "trailer" is a ref_word → continuation.

Two independent guards enforced the same wrong threshold.

## Fix
- `continuity_engine.py:100`: `len(content) >= 2` → `content and not any(...)` — any explicit
  entity word that isn't part of the current subject breaks the followup.
- Expanded `_start_words` with function words (the, a, an, of, for, with, about, …) so content
  extraction is precise.
- `integration_adapter.py:287`: `len(words) > 2` → `>= 2`, plus `not (interrogatives & query_words)`
  so bare 2-word interrogatives ("what happened") still resolve as continuations.

## Verification
```
is_followup(interstellar trailer): False   → fresh search (leak fixed)
is_followup(play trailer):         True    → continuation preserved
is_followup(show trailer):         True    → continuation preserved
is_followup(show gameplay):        True    → continuation preserved
handle('interstellar trailer') → source=retrieval, subject='Interstellar Trailer'
```
- `tests/test_entity_persistence_fix.py::TestFixB_IsContinuationQuery`: 17/17 pass.
- Full suite: identical failure set vs baseline (no regression).

## ponytail: noted
The artifact/followup vocabulary is hardcoded in two places (`_artifact_kws` in
continuity_engine, `ref_words` in integration_adapter). If new artifact types are added,
both sets must be updated. Acceptable for now; a shared vocabulary module is the upgrade path.
