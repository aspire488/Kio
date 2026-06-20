"""
Step 6 - Media Intelligence Runtime Validation.

Bootstraps the runtime, disables cloud providers (Ollama-only),
then submits 10 media queries through route() and captures responses.
Output to file to avoid console encoding issues.
"""
import os, sys, time, re, logging as _logging

_logging.disable(_logging.CRITICAL)

_output_file = os.path.join(os.path.dirname(__file__) or ".", "_runtime_transcript.txt")
_f = open(_output_file, "w", encoding="utf-8")

def output(*args, **kw):
    line = " ".join(str(a) for a in args)
    _f.write(line + "\n")
    try:
        print(line, **kw)
    except UnicodeEncodeError:
        safe = line.encode("ascii", "replace").decode("ascii")
        print(safe, **kw)

# Clear cached modules
for mod in list(sys.modules.keys()):
    if "mini_kio" in mod:
        del sys.modules[mod]

from mini_kio.core import config
for attr in ["GEMINI_ENABLED","GROQ_ENABLED","CEREBRAS_ENABLED","SAMBANOVA_ENABLED",
             "FIREWORKS_ENABLED","HUGGINGFACE_ENABLED","OPENROUTER_ENABLED",
             "TOGETHER_AI_ENABLED","FREELLMAPI_ENABLED"]:
    setattr(config, attr, False)
config.OLLAMA_ENABLED = True

from mini_kio.core.runtime import bootstrap_runtime
runtime = bootstrap_runtime()
output("[RUNTIME] bootstrapped - state=%s" % runtime.state)
output()

from mini_kio.core.command_router import route

user_id = 888888

QUERIES = {
    "Interstellar": "Interstellar",
    "Atomic Habits": "Atomic Habits",
    "FIFA World Cup": "FIFA World Cup",
    "Believer": "Believer",
    "The Bear": "The Bear",
    "GTA VI": "GTA VI",
    "Vaazha II": "Vaazha II",
    "French Revolution": "French Revolution",
    "Quantum Tunneling": "quantum tunneling",
    "Kubernetes": "Kubernetes",
}

results = []

for label, query in QUERIES.items():
    output("=" * 60)
    output("QUERY: %s" % label)
    output("RAW:   %s" % query)
    output("-" * 60)

    start = time.monotonic()
    try:
        result = route(query, user_id)
        elapsed = (time.monotonic() - start) * 1000
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        result = "ERROR: %s" % e

    if isinstance(result, dict):
        text = result.get("message", str(result))
    elif isinstance(result, str):
        text = result
    else:
        text = str(result)

    output("TIME:  %.0fms" % elapsed)
    output("LEN:   %d chars" % len(text))
    output()

    # Validation
    issues = []

    wiki_links = re.findall(r"en\.wikipedia\.org|wikipedia\.org", text, re.IGNORECASE)
    if wiki_links:
        issues.append("WIKIPEDIA_URL")

    raw_urls = re.findall(r"https?://[^\s)]+", text)
    if raw_urls:
        issues.append("RAW_URL")

    if len(text) < 50:
        issues.append("TOO_SHORT")

    if text.startswith("{") or text.startswith("["):
        issues.append("SOURCE_DUMP")

    status = "OK" if not issues else "ISSUES:%s" % ",".join(issues)
    results.append((label, status, elapsed, len(text)))

    # Print full response (stripped of emoji/unicode for console)
    safe_text = text.encode("ascii", "replace").decode("ascii")
    output(safe_text)
    output()

output("=" * 60)
output("VALIDATION SUMMARY")
output("=" * 60)
output()
output("%-25s %-20s %-10s %-8s" % ("Query", "Status", "Latency", "Length"))
output("-" * 70)
for label, status, elapsed, length in results:
    output("%-25s %-20s %-10s %-8d" % (label[:25], status, "%.0fms" % elapsed, length))
output()

ok_count = sum(1 for r in results if r[1] == "OK")
issue_count = sum(1 for r in results if r[1] != "OK")
output()
output("Summary: %d OK, %d with issues" % (ok_count, issue_count))
output("Full transcript saved to: %s" % _output_file)
_f.close()
