"""
test_verification_entity_anchor.py

Focused tests for the verification-path subject anchor. The verification
handler registers the entity named in the user's message so a later
entity-less follow-up ("is that actually true?") anchors to THIS subject.
camelCase entities ("iPhone", "iPad", "macOS") start lowercase and were
missed by the capitalization-only detector, so the subject fell back to the
PREVIOUS query's entity (live: an iPhone question registered "Tom" from a
prior Tom Holland question).

These tests assert the extracted anchor only — never response wording.
"""

import pytest

from mini_kio.media.intelligence.integration_adapter import _message_entity_name


@pytest.mark.parametrize("text,expected", [
    # The live failure: camelCase entity must be found.
    ("is it true that the new iPhone got delayed", "iPhone"),
    ("did the new iPad come out", "iPad"),
    ("is macOS still supported", "macOS"),
    ("what happened to eBay", "eBay"),
    # Regular capitalized entities keep working.
    ("I heard Messi's father passed away and he said he can't play long anymore", "Messi"),
    ("did Tom Holland actually say he is taking a break from acting", "Tom"),
    # Sentence-initial capitals are NOT entity evidence.
    ("Is that actually true?", ""),
    ("Is it true that the fix works", ""),
    # First named entity wins — "Marvel" is the claim's subject here.
    ("Did Marvel confirm Spider-Man 4", "Marvel"),
])
def test_message_entity_name(text, expected):
    assert _message_entity_name(text) == expected


def test_camelcase_beats_memory_anchor():
    """The fix exists so a camelCase entity in the CURRENT message outranks
    the memory anchor from a previous query."""
    name = _message_entity_name("is it true that the new iPhone got delayed")
    assert name == "iPhone"
    assert name != "Tom"
