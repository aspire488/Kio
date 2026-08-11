# LIVE VALIDATION — Knowledge Response Quality + Semantic Routing

**Date:** 2026-08-11
**Interface:** Real KIO Telegram bot (`@KIO_Runtime_bot`), real Windows machine
**Validation authority:** KIO_REALTIME_VALIDATION_PROTOCOL.md (real runtime > pytest)

---

## Runtime

| Item | Value |
|------|-------|
| Final validated PID | 25964 (post-review-fix restart) |
| Channel | Telegram |
| Method | One message at a time, actual delivery observed via `live_msg.py` + Telethon read-back |

---

## Capability Matrix

| Capability | Input | Actual reply | Result |
|-----------|-------|-------------|--------|
| Knowledge composition | "What is Notepad?" | "Windows Notepad (commonly known simply as Notepad) is a simple text editor for Windows; it creates and edits plain text documents." | PASS |
| Knowledge composition | "What is Paint?" | Natural LLM answer incl. AI tools / Image Creator / image editing | PASS |
| Knowledge composition (expanded) | "Tell me more about Notepad" | Expanded natural answer (history, spellcheck, rewrite tools) | PASS |
| Knowledge composition (unseen entity) | "What is VLC media player?" | "VLC is a free and open source cross-platform multimedia player and framework that plays most multimedia files, and various streaming protocols." | PASS |
| Knowledge composition (unseen entity) | "What does Audacity do?" | Natural answer: free open-source audio editor, VST3/Nyquist, AI features | PASS |
| Lock-state routing | "what's the lock state" | "Your computer isn't locked." (deterministic) | PASS |
| Lock-state variants | "am I locked out" / "is my computer locked" / "can I use the computer" | Same truthful deterministic answer | PASS |
| Battery family | "is my laptop charging?" | "Yes — the battery's at 31% and charging." | PASS |
| Battery family | "what's my battery?" | "Battery is at 60% and charging." | PASS |
| KIO uptime | "how long have you been running?" | "KIO has been running for 1 minute." (resets with restart) | PASS |
| System uptime | "how long has the system been up?" | Truthful: session 4d 3h + Fast Startup caveat | PASS |
| Desktop observation | "what's open?" | Real visible desktop: Chrome tabs (ChatGPT/Wikipedia/Spotify/Telegram), Windows Terminal, Spotify, Settings, File Explorer | PASS |
| Credential census | "what credentials are configured?" | "You don't have any connected accounts yet." (deterministic vault) | PASS |
| Credential variants | "which integrations are connected?" | Routes to credential list (in-process) | PASS |
| Self-preference | "what's your favorite movie?" | "As an AI, I don't have personal preferences or favorite movies in the way a human does..." (complete, no truncation) | PASS |
| Day-status (anti-fabrication) | "how's your day been?" | "All good on my end and ready to help. What's on your mind?" (truthful, no invented human experience) | PASS |
| Native modality | "open the Paint app" | "Opened paint" (native) | PASS |
| Normal conversation | "tell me a fun fact" | Correct fun fact | PASS |
| Knowledge boundary | "what is notepad" → information; "open notepad" → action; "is notepad open" → state; "what's open" → tabs | Correct in-process + live | PASS |

---

## Issues Found & Fixed During Live Validation

1. **Lock-state routing gap** — "what's the lock state" fell through to web knowledge. Extended the canonical lock-state semantic family; fixed a politeness-prefix strip that was eating "can" from "can I use the computer" (subject-pronoun guard in `_NormalizationService.run` and `_strip_polite_prefix`).

2. **Raw knowledge dumps** — Notepad/Paint replies leaked source chrome (markdown tables, trace ids, `| title | -` fragments, "Available:" tails, language dropdowns). Rewrote `AnswerComposer._extract_key_sentences`: per-line chrome filtering, standalone-title-line strip, language/list row filter, doubled-title collapse. Removed the "Available: Tell me more" robotic tail; offers remain internal for contextual follow-up.

3. **Query-as-subject** — Exa returns the raw query as `result.entity`, so "What is Notepad?" became the displayed subject. Plumbed the extracted `subject` through `_compose_answer`/`_retrieve_and_summarize`.

4. **Truncated LLM replies** — provider stream cuts produced broken half-replies ("As an AI, I don't have personal"). Added completeness guards: knowledge composer rejects non-terminating short answers → deterministic fallback; `_chat_converse` retries once (min-length 20 to protect short replies). MediaManager summarizer budget 10s/200tok → 15s/300tok.

5. **"your favorite X" misrouted to knowledge** — self-preference questions ("what's your favorite movie?") now route to conversation (opinion family), not web search.

6. **Credential census gap** — "what credentials are configured?" went to web knowledge. Extended the credential list family with configured/set-up/connected/active variants.

7. **Fabricated human experience** — "how's your day been?" produced invented bakery/coffee/sunshine narrative. Extended the day-status greeting family so these route to the deterministic truthful greeting.

8. **UnicodeEncodeError (cp1252)** — `setup_startup_logging` stream handler crashed on emoji-containing log lines when console-attached. Reconfigured stdout/stderr to UTF-8 with `errors="replace"` (semantic content preserved in the UTF-8 file handler).

---

## Code Review

Reviewer feedback applied:
- Removed redundant `favourite` regex (subsumed by `(?:favourite|favorite)`)
- `included in` / `now comes with` no longer filtered (real content loss)
- Doubled-title collapse now requires a multi-word fragment ("The The" band preserved)
- Converse truncation retry gated on `len >= 20` (short replies don't pay for a retry)
- `_last_subject` now stored by composer; string-result guard added in `compose()`

---

## Targeted Regression

- 25 routing checks (lock/battery/knowledge-boundary/self-preference/credential/day-status/politeness): **0 failures**
- Composer assertions (plain prose, depth, chrome filter, subject preference, The The guard, dup collapse): **PASS**
- `tests/test_operational_health.py`: **22 passed**

## Final Runtime State

Single clean instance (validated PID 25964), zero Telegram getUpdates conflicts after clean launch, responsive to every matrix query.

## Known Limitations

- LIVE VALIDATION for actual lock/unlock transitions and media transport was not exercised during this pass (machine stayed unlocked; no media session active). Those were verified in prior milestones; the state-machine truthfulness invariants are unchanged.
- LLM-composed knowledge answers depend on provider availability; the deterministic extractor remains the guaranteed fallback.
