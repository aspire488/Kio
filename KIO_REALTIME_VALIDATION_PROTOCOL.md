# KIO Realtime Validation Protocol (CANONICAL)

**Status:** Project-wide canonical protocol — mandatory for all runtime-facing work.

> **REAL KIO RUNTIME IS THE PRIMARY ACCEPTANCE AUTHORITY.**
> **PYTEST IS SUPPORTING EVIDENCE, NOT RUNTIME ACCEPTANCE.**

---

## 1. Core Principles

1. **REAL KIO RUNTIME IS THE PRIMARY ACCEPTANCE AUTHORITY.**
   A capability is "working" only when the real KIO process, running on the
   real machine, demonstrably performs it. Passing tests do not prove runtime
   behavior.

2. **PYTEST IS SUPPORTING EVIDENCE, NOT RUNTIME ACCEPTANCE.**
   Pytest proves code behavior in isolation. It never proves KIO behavior.
   Never report "feature works because N tests passed" as completion proof.

3. **FULL PYTEST MUST NOT BE USED AS THE DEFAULT DEVELOPMENT LOOP.**
   The forbidden loop is: edit → full pytest → count failures → stash →
   full pytest → compare → repeat. Counting 84 vs 85 vs 83 baseline failures
   is not engineering. Full-suite baseline drift is not today's target.

4. **RUNTIME-FACING FEATURES REQUIRE REAL-MACHINE VALIDATION.**
   Telegram, browser, desktop, applications, windows, files, media, CUA,
   system state, CPU/RAM/GPU, battery, storage, lock/unlock, credentials,
   authentication, providers, MCP, execution, contextual commands and
   natural-language routing must each be exercised against the real machine
   — one message/action at a time.

5. **LIVE FAILURE TAKES PRIORITY OVER GREEN MOCKS.**
   If pytest = PASS and runtime = FAIL, the runtime failure is the bug.
   Trace the real execution path, find the canonical owner, fix the owner,
   re-run the real runtime. Never weaken the live requirement to satisfy a
   mock. Conversely, pytest = FAIL while runtime = PASS is investigated as
   a stale expectation — never "fixed" by breaking working runtime behavior.

6. **TARGETED TESTS ARE PREFERRED DURING DEVELOPMENT.**
   A targeted test suite for the code you actually changed is sufficient to
   catch a local regression. Semantic extraction → semantic-routing tests;
   desktop observation → desktop-observation tests; application resolution →
   application-resolution tests; health/status → health tests; credentials →
   credential tests; target identity → target-identity tests. Do not
   automatically escalate into the entire repository suite.

7. **FULL REGRESSION IS A MILESTONE CHECK, NOT A DEVELOPMENT LOOP.**
   A full regression may be run ONCE at an appropriate milestone boundary if
   genuinely necessary. Existing documented baseline failures are not the
   milestone's engineering target.

---

## 2. Real-World-First Test Order

    REAL KIO RUNTIME
        → REAL WINDOWS STATE
        → LIVE TELEGRAM (one message at a time)
        → TARGETED TESTS
        → ADJACENT REGRESSION
        → ONE FINAL FULL REGRESSION (milestone boundary only)

## 3. Real-Machine Test Matrix

Use actual KIO runtime interactions, one message at a time. Use entities
that were NOT mentioned in the milestone prompts — the objective is whether
KIO understands ARBITRARY requests, not whether it recognizes example
phrases.

Example classes (never just the literal examples):

- natural greeting
- KIO self-reference ("how's KIO?", "KIO status")
- battery query ("what's my battery?", "is it charging")
- system health / "what's wrong"
- application inventory ("what apps do I have?")
- desktop observation ("what's open?")
- native application open ("open <unseen application>")
- web open
- explicit web modality ("open X in Chrome", "on the web")
- explicit native modality ("open the X app", "launch X")
- native/web conversational correction ("Actually open the app")
- duplicate open prevention ("open X" twice → no duplicate)
- explicit second target ("open another X tab")
- external application control
- contextual close ("close it", "close both")
- multi-target close ("close X and Y")
- focus/switch
- lock state / unlock / authentication boundary
- KIO uptime / system uptime
- credential status
- knowledge query vs action query vs state query boundaries

## 4. When Live Behavior Fails

Do NOT immediately add another regex / alias / application name / response
template / pytest fixture. Trace the canonical chain:

    input → semantic extraction → intent → entity → context → capability
    → provider → execution → observation → verification → response

Find the canonical owner responsible for the failure, fix that owner, then
perform the SAME class of operation against a DIFFERENT live entity.

## 5. Reporting Format

Report live verification as:

    LIVE RUNTIME:       PASS/FAIL
    REAL SYSTEM STATE:  PASS/FAIL
    REAL TELEGRAM:      PASS/FAIL
    REAL BROWSER:       PASS/FAIL
    REAL DESKTOP:       PASS/FAIL
    REAL APPLICATION EXECUTION: PASS/FAIL
    TARGETED REGRESSION: PASS/FAIL

Pytest numbers appear as supporting evidence only, after the live result.
If live validation could not be performed, state `LIVE VALIDATION NOT
PERFORMED` explicitly — do not claim the capability is fully verified.

## 6. Live Validation Log

For significant milestones, keep a concise markdown record
(`reports/LIVE_VALIDATION_<milestone>.md`): date, commit, runtime PID,
interface tested, environment, capability, input, actual response, observed
state, verification method, result, known limitations. NEVER write
passwords, API keys, OAuth tokens, session cookies or private credentials
into the record.

## 7. References

This protocol is the single canonical source for runtime-validation policy.
Engineering/planning documents reference it instead of duplicating the
policy.
