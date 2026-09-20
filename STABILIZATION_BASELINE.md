# Restoration Baseline — Captured Before Stabilization Fixes

## Git State
- **SHA**: f46e21c (chore: consolidate full KIO system restoration)
- **Working tree**: 5 modified files from prior stabilization investigation (D002/D003 shell.py, D004/D015 eval, D007/D008 test fixes)

## Test Baseline (gate3 subset, 126.9s)
- **131 passed, 10 failed** (all pre-existing)
- 28 subtests passed
- 2 warnings (hypothesis, google.generativeai deprecation)

### Pre-existing failures (NOT caused by our changes)
1. `test_social_thanks_variants` — "thank you kio" routes to LLM (provider unavailable) instead of deterministic response
2. `test_responder_called_in_orchestration_flow` — ImportError: `_route_via_orchestration` doesn't exist
3. `test_confirmation_prompt_unchanged_across_calls` — LLM provider unavailable on 3rd call
4. `test_degraded_fallback_unchanged` — Topic suffix mismatch (pre-existing)
5. `TestMultiStepNarration` (6 tests) — Tests expect old format ("done - opened chrome") but code produces new format ("Opened Chrome.")

## Runtime Metrics
- Pipeline init: 110ms
- Process RSS: 17.6 MB (idle Python process)
- CPU: 0.0% (idle)

## Pending Fixes (from prior investigation)
- D002/D003: shell=True → shlex.split (already applied)
- D004/D015: eval → AST evaluator (already applied)
- D007: test_degraded_fallback topic suffix (already applied)
- D008: test_unknown_command conversational fallback (already applied)
