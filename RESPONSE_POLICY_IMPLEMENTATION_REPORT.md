# RESPONSE_POLICY_IMPLEMENTATION_REPORT.md

## Goal
Unified short-first response policy across all KIO output channels.

## Audit Findings
- No short-first mechanism existed. The final answer composer was `_ResponseComposer.compose`
  (`pipeline/__init__.py`), which passed through whatever the resolver/coordinator produced.
- `AnswerComposer` (`answer_composer.py:30-68`) used a "concise, 2-4 sentences" LLM prompt but
  produced ~3-sentence blobs, no follow-up offer, no expand-on-demand hook.
- `runtime_response_formatter.py` only passed natural text through (`:177-179`) and truncated at
  4000 chars in `format_channel_reply`.

## Implementation (two layers)
1. **Prompt-level (source of blobs):** `_chat_converse` system prompt now explicitly says
   short-first: reply in 1-2 sentences, then offer to go deeper ("Want more detail?"); only
   expand unprompted when the user asked for depth.
2. **Hard enforcement (central chokepoint):** `_ResponseComposer._short_first` truncates any
   successful natural reply > 220 chars to its first sentence + "Want more?" (hard cap 190 chars
   for a single over-long sentence). Structured content is preserved:
   - multi-line results (`\n`, bullet lists, "Open tabs:", "Here's what I remember:") pass through.
   - This makes the policy channel-agnostic — Telegram, terminal, and MCP all inherit it from
     `compose()`.

## Verification
```
_short_first("Good morning! How are you today? Lovely weather.") → unchanged (67 chars)
_short_first(327-char blob) → "…Zimmer which is widely regarded as one of his best…Want more?" (197)
_short_first("Open tabs:\n  YouTube\n  Gmail") → unchanged (structured)
```
Full suite: no regression.

## Design Notes
- Threshold is a heuristic (220 chars ≈ 1-2 short sentences). A follow-up question ("Want more?")
  invites expansion, implementing the expand-on-demand contract without a new command.
- Action results (open/close/play) already route through `runtime_response_formatter` and are
  naturally short; the composer only guards against LLM bloat.

## Remaining
- Expand-on-demand ("yes" after "Want more?") currently re-enters the normal classifier as a
  followup; a dedicated "expand" path that re-asks the LLM without the short-first cap would
  complete the loop. Not required for this slice.
