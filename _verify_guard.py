"""Verify document creation guard invariants."""
import sys, os
sys.path.insert(0, '.')
os.chdir(r'C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final')

from mini_kio.core.pipeline import Pipeline
p = Pipeline()
c = p._classifier

# System-level invariant: informational/voice/research requests must NOT produce document creation routing
test_cases = [
    'give me a voice reply on Teachers Day',
    'tell me about climate change',
    'what is the capital of France',
    'explain how photosynthesis works',
    'say that out loud',
    'give me your thoughts on quantum computing',
    'research the latest AI trends',
    'who is the CEO of Tesla',
    'how does the stock market work',
    'what are the best restaurants nearby',
]

print('=== DOCUMENT CREATION GUARD TEST (should all be BLOCKED) ===')
failures = 0
for tc in test_cases:
    lower = tc.lower()
    result = c._detect_document_creation(lower, tc)
    if result is None:
        status = 'OK (no doc)'
    else:
        status = 'FAIL: routed to {} artifact={}'.format(result.action, result.metadata.get('artifact', '?'))
        failures += 1
    print('  {:55s} -> {}'.format(repr(tc), status))

# Positive cases: these SHOULD produce document creation
positive_cases = [
    'create a report about climate change',
    'make a spreadsheet of monthly expenses',
    'draft an email to my professor about the deadline',
    'write a comparison of Python vs Rust',
    'generate a presentation about AI',
]

print()
print('=== POSITIVE DOCUMENT CREATION (should all route) ===')
for tc in positive_cases:
    lower = tc.lower()
    result = c._detect_document_creation(lower, tc)
    if result:
        status = 'OK: {} artifact={}'.format(result.action, result.metadata.get('artifact', '?'))
    else:
        status = 'FAIL: should have routed to document creation'
        failures += 1
    print('  {:55s} -> {}'.format(repr(tc), status))

print()
if failures == 0:
    print('ALL INVARIANTS HOLD')
else:
    print('FAILURES: {}'.format(failures))
