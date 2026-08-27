# MEMORY_UX_FIX_REPORT.md

## Symptoms
- `Remember I like Formula 1` → ack leaked the raw key: `Remembered: preference_formula 1 = like.`
  (schema is inverted — key holds the subject, value holds the sentiment).
- `What do I like about Formula 1?` dumped **all** saved facts instead of the Formula 1 one.

## Root Cause
`_exec_memory` (`pipeline/__init__.py:920-928`) acknowledged facts verbatim as `{key} = {value}`,
and the recall branch (`:940-961`) only had coarse "favorite/like/love/enjoy/prefer" matching with
no topic scoping for "about X" / "for X" queries.

## Fix
1. **Friendly ack:** store path now renders human-readable sentences:
   - `preference_X` → "You {value} {X}."
   - `favorite_X` → "Your favorite {X} is {value}."
   - `user_name` → "Your name is {value}."
   - else → "{key}: {value}."
   Ack prefix: "Got it — …"
2. **Topic-scoped recall:** before the broad favorite dump, a new branch matches
   `(?:about|for) <topic>` and returns only facts whose key overlaps the topic terms.
   Falls through to existing category/general behavior when no scope matches.

## Verification
```
store  → "Got it — You like formula 1."
recall "What do I like about Formula 1?" → "You like formula 1."      (scoped, not a full dump)
recall "What do I like?"                → "You like formula 1."      (general, still works)
```
Full suite: no regression.

## ponytail: noted
The `preference_{subject} → like` schema is preserved (recall logic depends on it). A migration
to `{subject} → like` (sane orientation) is possible but touches `memory_store.py`,
`fact_repository.py`, and all recall branches — deferred as not required to fix the UX bugs.
