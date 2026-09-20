# Post-Repair Live Validation Plan — Final Gate Before Pipecat

**Date**: 2026-09-12
**Branch**: `kio-restoration-safety-20260823`
**Purpose**: the ONE final real-Telegram pass. Nothing here is executed until
every offline gate below is green and KIO has been restarted on the repaired
code.

---

## 0. Preconditions (must all hold before the first Telegram message)

| # | Precondition | How it is proven |
|---|--------------|------------------|
| 0.1 | No unwanted console window | `python tools/verify_no_console_window.py` → `total_windows_created: 0` |
| 0.2 | No unflagged spawn sites | `python tools/audit_spawn_flags.py` → exit 0, `uncovered: 0` |
| 0.3 | Exactly one KIO runtime | process table shows one `python -u kio_bot.py`; a second launch exits with `[LIFECYCLE] startup refused` |
| 0.4 | Artifacts produce real files | `python tools/verify_artifacts.py` → 8/8 |
| 0.5 | Dependencies | `KIO_REQUIRED_DEPENDENCIES.md` — 12/12 installed, 0 installs pending |
| 0.6 | Regression baseline | `pytest tests/test_execution_fabric.py tests/test_gap_closure_v3.py` → same failure set as the pre-session baseline (13 known) |
| 0.7 | Clean restart on repaired code | PID of the new runtime differs from the PIDs in flight before the restart |

---

## 1. Execution rules for the live pass

1. **One message at a time.** Send, wait for KIO's reply, verify the side
   effect on the machine, then send the next message.
2. **Never accept KIO's prose as proof.** Verify the OS/filesystem/browser
   state independently (Explorer, tab list, clipboard viewer, the file on
   disk, `sha`/`size`, Telegram receipt).
3. **No combined commands.** "open github and list my tabs" is not a test.
4. **Record latency** per message (send → reply received).
5. **Do not re-run a failed case repeatedly.** One retry maximum, then record
   FAIL with the observed evidence.

---

## 2. Case list (one real message each)

| # | Message | Independent verification |
|---|---------|--------------------------|
| 1 | Open github.com | Chrome has a github.com tab |
| 2 | Open github.com in a new tab | tab count increases, new tab is github.com |
| 3 | List my tabs | reported tabs match the actual Chrome window |
| 4 | Navigate the current tab to https://example.com | tab URL is example.com |
| 5 | List the files on my Desktop | matches Explorer's Desktop listing |
| 6 | Create a file called kio_live_test.txt containing KIO LIVE TEST | file exists on Desktop with exact bytes |
| 7 | Read kio_live_test.txt | content equals what was written |
| 8 | Copy KIO_CLIPBOARD_LIVE_TEST_1234 to my clipboard | OS clipboard reads that exact string |
| 9 | What is in my clipboard? | matches OS clipboard |
| 10 | Write a Python function that checks whether a number is prime | code text in chat; **no** VS Code window, **no** project folder created |
| 11 | Create a Python project called kio_prime_test with tests and open it in VS Code | `kio_prime_test/{src,tests,README.md,.gitignore,requirements.txt}` on disk **and** a VS Code window showing it |
| 12 | Create a Word report explaining KIO | `.docx` in Documents, opens, has headings + a table |
| 13 | Create a PDF version of the report | `.pdf` in Documents, `%PDF-` header, page count > 0 |
| 14 | Create an Excel spreadsheet containing KIO capabilities | `.xlsx`, sheet with the capability rows (not `Item/Quantity/Cost`) |
| 15 | Create a five-slide PowerPoint explaining KIO | `.pptx`; **record the actual slide count** (known deviation: currently 9) |
| 16 | Create a CSV containing KIO validation cases | `.csv` parses with the `csv` module into ≥2 columns |
| 17 | Create a Markdown architecture summary | `.md` contains `#` headings |
| 18 | Create an HTML architecture page | `.html` with doctype/title, opens in the browser |
| 19 | Play some lofi hip hop | **visible** browser/YouTube playback — not hidden audio |
| 20 | Pause | playback state actually paused |
| 21 | Resume | playback state actually resumed |
| 22 | Seek forward 30 seconds | player position actually advanced ~30s |
| 23 | Increase the volume | volume actually increased |
| 24 | Decrease the volume | volume actually decreased |
| 25 | Play the previous track | different track actually playing |
| 26 | Send a Telegram message saying KIO live communication test | message received in the chat |
| 27 | Remember that my temporary test value is KIO_MEMORY_TEST_9281 | stored |
| 28 | What is my temporary test value? | returns KIO_MEMORY_TEST_9281 |
| 29 | Forget my temporary test value | delete acknowledged |
| 30 | What is my temporary test value? | **no** value returned (not "I forgot" — the value must be gone) |

Security (no side effects): confirm that a destructive request is refused
(e.g. "run the command shutdown /s /t 0" → blocked, machine stays up).

---

## 3. Scoring rule

- **PASS** = KIO claimed the action *and* the independent check confirmed it.
- **FAIL** = KIO claimed success but the side effect did not occur, or KIO's
  reply was a non-answer for a supported capability.
- **BLOCKED** = a genuine external prerequisite is missing after reasonable
  setup (e.g. a provider needs credentials). A code bug is never BLOCKED.

Score is `PASS / (PASS + FAIL)` with BLOCKED items listed separately. Do not
inflate: a single unverified claim invalidates that case.

---

## 4. Report to write afterwards

`FINAL_LIVE_VALIDATION_REPORT.md` — and only after the run — containing: exact
Git SHA, environment, installed dependencies, provider matrix, every case with
the exact message sent + KIO's reply + the independent verification, latency,
resource usage (KIO tree RSS/CPU, 650 MB ceiling), failures, blocked items and
the strict score.

**This file does not exist yet, on purpose: no live validation has been run in
this session.** Writing it before the run would be a fabricated PASS.
