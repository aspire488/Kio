# CURRENT TASK: Gate 4D Entrypoint — Context Intelligence

Target:   mini_kio/context/context_manager.py
Contract: Refine keyword/relevance matching for imported memory retrieval.
          Deterministic only — no probabilistic ranking, no embeddings, no AI.
          No runtime changes. No conversational changes.

## Scope (exact)

- Keyword matching refinement — multiple keyword search, fuzzy substring matching
  (contiguous subsequence, not semantic)
- Relevance scoring — normalized score based on occurrence density, position
- Retrieval with scoring — return scored results without affecting deterministic
  prioritization
- Budget-aware retrieval — scored results respect max_total_chars and limit

## NOT in Scope

- Any core/ runtime file
- Any conversational changes
- Probabilistic or embedding-based relevance
- Profile or identity changes
- Persistence format changes

## Entry Criteria

- [ ] Branch: gate4_foundation
- [ ] Working tree clean
- [ ] 341/341 Gate 3 + Gate 4A + Gate 4C tests passing
- [ ] No pending changes in core/ or runtime/

## Exit Criteria

- [ ] All existing tests still pass
- [ ] No new lint or type errors
- [ ] Multiple keyword search returns intersection of matches
- [ ] Relevance scoring is deterministic and bounded
- [ ] Scored retrieval respects budget limits
- [ ] gitnexus_detect_changes() confirms scope
