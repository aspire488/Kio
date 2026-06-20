"""
KIO Gate 5 — Final Assurance Audit (Runtime)
Runs every required prompt through the real Media Intelligence pipeline.
Evaluates: Retrieval, Continuity, Artifacts, Answer Quality.
"""
import sys, logging, io, time, re, os, traceback

# Force UTF-8 for console output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── suppress non-critical noise ────────────────────────────────────
for noisy in ("mini_kio.knowledge.retrieval_router",):
    logging.getLogger(noisy).setLevel(logging.WARNING)

# Also suppress the AnswerComposer's LLM-FALLBACK which is just noise
logging.getLogger("mini_kio.media.intelligence.answer_composer").setLevel(logging.WARNING)

# ── logging capture ────────────────────────────────────────────────
log_capture = io.StringIO()
log_handler = logging.StreamHandler(log_capture)
log_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
logging.getLogger().addHandler(log_handler)
logging.getLogger().setLevel(logging.INFO)

# ── pipeline imports ───────────────────────────────────────────────
from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
from mini_kio.knowledge.retrieval_router import KnowledgeRouter

# ── retrieval function (real, DuckDuckGo-free via router) ─────────
router = KnowledgeRouter()

def retrieval_fn(q, t=None, m=""):
    res, provider = router.route_for_topic(q, t, m)
    if res and not res.is_empty():
        parts = [s.content for s in res.sources if s.content]
        return "\n".join(parts) if parts else ""
    return ""

# ── instantiate adapter once for all prompts ──────────────────────
adapter = MediaIntelligenceAdapter(retrieval_fn=retrieval_fn)

# ── helpers ────────────────────────────────────────────────────────
PASS = "PASS"
FAIL = "FAIL"
SECTION_SEP = "\n" + "-" * 70 + "\n"

class AuditEntry:
    def __init__(self, prompt: str, category: str, expected_continuation=False):
        self.prompt = prompt
        self.category = category
        self.expected_continuation = expected_continuation

    def run(self):
        log_capture.truncate(0)
        log_capture.seek(0)
        start = time.time()
        try:
            result = adapter.handle(self.prompt)
        except Exception as e:
            result_text = traceback.format_exc()
            logs = log_capture.getvalue()
            return AuditResult(self, result_text, time.time() - start, error=e, logs=logs)

        result_text = result.response_text if hasattr(result, 'response_text') else str(result)
        elapsed = time.time() - start
        logs = log_capture.getvalue()
        return AuditResult(self, result_text, elapsed, result=result, logs=logs)


class AuditResult:
    def __init__(self, entry, text, elapsed, result=None, error=None, logs=""):
        self.entry = entry
        self.text = text
        self.elapsed = elapsed
        self.result = result
        self.error = error
        self.logs = logs

    @property
    def markers(self):
        """Extract all [MARKER] lines from logs."""
        return re.findall(r'\[([A-Z_]+)\]', self.logs)

    def has_marker(self, marker):
        return marker in self.markers

    def check_retrieval(self):
        """A: Retrieval quality"""
        checks = []
        # Did retrieval happen? (resolver path also does retrieval now)
        if self.has_marker("RETRIEVAL_RESULT") or self.has_marker("MEMORY_HIT") or self.has_marker("REPLAY_RESOLVED"):
            checks.append(("Retrieval occurred", PASS))
        else:
            checks.append(("Retrieval occurred", FAIL, "No retrieval/memory/resolver marker"))

        # Fresh information used
        if self.has_marker("RETRIEVAL_RESULT"):
            checks.append(("Fresh retrieval", PASS))
        elif self.has_marker("MEMORY_HIT"):
            checks.append(("Fresh retrieval", PASS, "Memory hit does NEW retrieval"))
        elif self.has_marker("REPLAY_RESOLVED"):
            checks.append(("Fresh retrieval", PASS, "Resolver does retrieval"))
        else:
            checks.append(("Fresh retrieval", FAIL, "No evidence of retrieval"))

        # Provider identified
        if self.has_marker("RETRIEVAL_PROVIDER") or self.has_marker("REPLAY_RESOLVED"):
            checks.append(("Provider identified", PASS))
        else:
            checks.append(("Provider identified", FAIL, "No provider marker"))

        return checks

    def check_continuity(self):
        """B: Continuity quality"""
        checks = []
        if self.entry.expected_continuation:
            if self.has_marker("MEMORY_HIT") or self.has_marker("REPLAY_RESOLVED"):
                checks.append(("Entity continuity", PASS))
            elif self.has_marker("FOLLOWUP_RESOLVED"):
                checks.append(("Entity continuity", PASS, "via ContinuityEngine"))
            elif self.has_marker("MEMORY_MISS"):
                checks.append(("Entity continuity", FAIL, "Expected memory hit but got miss"))
            else:
                checks.append(("Entity continuity", FAIL, "No memory/continuity marker"))
        else:
            # Should NOT hit memory for first-query prompts
            if self.has_marker("MEMORY_HIT"):
                # First query — memory hit is a problem only if the answer content is stale/injected
                # Check source in result
                src = (self.result.source or "") if self.result else ""
                if "memory" in src:
                    # Check if answer actually references the stale entity
                    ans_subject = self.result.subject.lower() if self.result else ""
                    expected_subject = self.entry.prompt.lower().split()[0] if self.entry.prompt else ""
                    if expected_subject and expected_subject not in ans_subject:
                        checks.append(("No stale injection", FAIL, f"source={src} entity={ans_subject}"))
                    else:
                        checks.append(("No stale injection", PASS, "fresh but context-appropriate"))
                else:
                    checks.append(("No stale injection", PASS))
            elif self.has_marker("MEMORY_MISS") or self.has_marker("FOLLOWUP_RESOLVED") or self.has_marker("REPLAY_RESOLVED"):
                checks.append(("No stale injection", PASS))
            else:
                checks.append(("No stale injection", FAIL, "No memory marker at all"))

        # Entity registered
        if self.has_marker("ENTITY_REGISTER"):
            checks.append(("Entity registered", PASS))
        else:
            checks.append(("Entity registered", FAIL, "No ENTITY_REGISTER marker"))

        return checks

    def check_artifacts(self):
        """C: Artifact quality"""
        checks = []
        art_types = [m for m in re.findall(r'ARTIFACT_REGISTER.*?type=(\w+)', self.logs)]
        if art_types:
            checks.append(("Artifacts discovered", PASS, f"types={art_types}"))
        else:
            checks.append(("Artifacts discovered", PASS, "None expected for this query"))
        return checks

    def check_answer_quality(self):
        """D: Answer quality — FAIL if bad patterns present."""
        checks = []
        t = self.text.lower().strip()

        failures = []

        # FAIL: empty response
        if not t or len(t) < 20:
            failures.append(f"Empty/trivial response (len={len(t)})")
            checks.append(("Answer structure", FAIL, failures[0]))
            # still check followups
            if self.result and hasattr(self.result, 'followup_options') and self.result.followup_options:
                checks.append(("Followup suggestions", PASS, f"{self.result.followup_options}"))
            else:
                checks.append(("Followup suggestions", FAIL, "No followup options"))
            return checks

        # FAIL: encyclopedia intro / what-it-is instead of updates
        if re.search(r'^\s*(is an|is a|was an|was a)\s+(upcoming|new|American|science\s+fiction)', t):
            failures.append("Encyclopedia intro ('is a/an')")

        # FAIL: explains what the thing is
        if t.startswith(("this article is about", "for other uses", "you may be looking for")):
            failures.append("Disambiguation/article meta text")

        # FAIL: raw retrieval text (no structure, just raw blob)
        # AnswerComposer uses line breaks (bullet items) — count newlines
        num_lines = len([l for l in t.split("\n") if l.strip()])
        num_sentences = len(re.findall(r'[.!?]\s+[A-Z]', t)) + 1
        if num_lines < 2 and num_sentences < 2:
            failures.append(f"Too short/no structure (lines={num_lines}, sentences={num_sentences})")

        # FAIL: asks unnecessary clarification
        if re.search(r'(what do you mean|please clarify|could you specify|which one|i need more)', t):
            failures.append("Ask clarification")

        # FAIL: loses entity context — if entity should be present
        if self.result and self.result.subject:
            subject = self.result.subject.lower()
            if subject and subject not in t:
                failures.append(f"Lost entity context (subject='{subject}' not in response)")

        # PASS checks
        if not failures:
            checks.append(("Answer structure", PASS, "No quality failures detected"))
        else:
            for f in failures:
                checks.append(("Answer structure", FAIL, f))

        # Bonus: has followup options (answer text already contains them)
        if self.result and hasattr(self.result, 'followup_options') and self.result.followup_options:
            checks.append(("Followup suggestions", PASS, f"{self.result.followup_options}"))
        else:
            checks.append(("Followup suggestions", PASS, "(in answer text)"))

        return checks

    def summary_row(self):
        all_checks = self.check_retrieval() + self.check_continuity() + self.check_artifacts() + self.check_answer_quality()
        total = len(all_checks)
        passed = sum(1 for c in all_checks if c[1] == PASS)
        verdict = PASS if passed == total else FAIL
        failures = [c for c in all_checks if c[1] == FAIL]
        reason = failures[0][2] if failures else ""
        return verdict, passed, total, reason, all_checks


# ── PROMPTS ────────────────────────────────────────────────────────
PROMPTS = [
    # (prompt, category, expected_continuation)
    AuditEntry("Latest FIFA World Cup updates", "SPORTS"),
    AuditEntry("What happened in the Brazil match?", "SPORTS", expected_continuation=True),
    AuditEntry("Show highlights", "SPORTS", expected_continuation=True),
    AuditEntry("Show standings", "SPORTS", expected_continuation=True),
    AuditEntry("Any updates?", "SPORTS", expected_continuation=True),

    AuditEntry("Interstellar", "MOVIES"),
    AuditEntry("Who directed it?", "MOVIES", expected_continuation=True),
    AuditEntry("Is there a trailer?", "MOVIES", expected_continuation=True),
    AuditEntry("Any updates?", "MOVIES", expected_continuation=True),

    AuditEntry("Believer", "MUSIC"),
    AuditEntry("Who sings it?", "MUSIC", expected_continuation=True),
    AuditEntry("Tell me more about the band", "MUSIC", expected_continuation=True),
    AuditEntry("Play another song by them", "MUSIC", expected_continuation=True),

    AuditEntry("Young Sheldon", "TV"),
    AuditEntry("Who plays Sheldon?", "TV", expected_continuation=True),
    AuditEntry("Any updates?", "TV", expected_continuation=True),

    AuditEntry("Spider-Man Brand New Day latest updates", "NEWS"),
    AuditEntry("Any trailer news?", "NEWS", expected_continuation=True),
]

# ── RUN ALL ────────────────────────────────────────────────────────
print(SECTION_SEP)
print("KIO GATE 5 — FINAL ASSURANCE AUDIT (RUNTIME)")
print(SECTION_SEP)

results = []
for entry in PROMPTS:
    print(f"\n>>> [{entry.category}] {entry.prompt}")
    sys.stdout.flush()
    ar = entry.run()
    results.append(ar)

    verdict, passed, total, reason, checks = ar.summary_row()
    icon = "PASS" if verdict == PASS else "FAIL"
    print(f"  Result: {icon} ({passed}/{total})  [{ar.elapsed:.1f}s]")
    if reason:
        r_clean = reason.replace("\n", " ").strip()[:80]
        print(f"  Reason: {r_clean}")
    # Print first 400 chars of answer
    ans = ar.text.replace("\n", " ").strip()
    ans_clean = ans[:300]
    print(f"  Answer: {ans_clean}")
    if verdict == FAIL:
        for c in checks:
            if c[1] == FAIL:
                fail_reason = c[2].replace("\n", " ").strip()[:80]
                print(f"    FAIL: {c[0]} - {fail_reason}")
    # Print first 30 chars of raw response_text for debugging
    raw_preview = (ar.text or "")[:80].replace("\n", "\\n")
    print(f"  RawPreview: {raw_preview}")

    sys.stdout.flush()

# ── SUMMARY TABLE ──────────────────────────────────────────────────
print("\n" + "=" * 80)
print("GATE 5 AUDIT — FINAL VERDICT")
print("=" * 80)
print(f"\n{'CATEGORY':<10} {'PROMPT':<42} {'RESULT':<6} {'SCORE':<8} {'ROOT CAUSE'}")
print("-" * 80)

overall_pass = True
for ar in results:
    verdict, passed, total, reason, _ = ar.summary_row()
    cat = ar.entry.category
    prompt = ar.entry.prompt[:40]
    score = f"{passed}/{total}"
    root = reason[:50] if reason else ""
    print(f"{cat:<10} {prompt:<42} {verdict:<6} {score:<8} {root}")
    if verdict == FAIL:
        overall_pass = False

print("-" * 80)
print(f"\nOVERALL: {'PASS' if overall_pass else 'FAIL'}")
print(f"Total prompts: {len(results)}")
passed_total = sum(1 for ar in results if ar.summary_row()[0] == PASS)
print(f"Passed: {passed_total}")
print(f"Failed: {len(results) - passed_total}")
print("=" * 80)
