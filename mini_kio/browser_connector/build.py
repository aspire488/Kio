"""
build.py — Single source of truth for the KIO Chrome extension build fingerprint.

Both the connector (registration gate) and the state-verification pipeline
(stale-build diagnostic) previously hardcoded the same value ("0.2.0") in two
separate places. If they ever drift, a freshly-built extension can be rejected
by one layer while the other reports a stale build. Every Python consumer must
import this constant instead of declaring its own literal.

The JavaScript side (background.js BUILD_VERSION + the INLINED build literal in
get_build_info, and manifest.json "version") cannot import Python at runtime,
so it is kept in sync manually — the regression test
tests/test_fix_batch_20260809b.py parses those files and asserts they equal
this constant. Bump here FIRST, then bump the JS/manifest to match.
"""

EXTENSION_BUILD = "0.3.6"
