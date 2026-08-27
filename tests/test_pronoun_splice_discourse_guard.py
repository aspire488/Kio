"""Regression tests: the context manager's G5 pronoun splice (resolved_text)
must NEVER splice a stale command entity into conversational discourse
(live failure: after "6!" left active_entity="6", "why did you prefer that
one" became "why did you prefer 6 one" and the LLM answered "I chose the
sixth option"). Command referents must still splice."""
import sys

sys.path.insert(0, ".")
from mini_kio.core.context_manager import SessionContext


def _ctx_with(entity):
    ctx = SessionContext(session_id="splice_test")
    ctx.active_entity = entity
    ctx.last_target = entity
    return ctx


DISCOURSE_CASES = [
    "why did you prefer that one",
    "would you pick it",
    "what about the other one",
    "do you still like this",
    "what about watching it instead",
    "would you still choose it now",
    "why that one",
    "which one would you pick",
    "what about it",
    "you said the first one was better",
]


def test_discourse_never_spliced_with_stale_entity():
    """Even with a stale math referent ("6") in context, conversational
    discourse must reach the generator untouched."""
    ctx = _ctx_with("6")
    for q in DISCOURSE_CASES:
        assert ctx.resolved_text(q) == q, f"{q!r} was spliced -> {ctx.resolved_text(q)!r}"


def test_discourse_never_spliced_with_real_entity():
    """Same with a plausible command entity — the referent must not be
    injected into a conversation question."""
    ctx = _ctx_with("notepad")
    for q in DISCOURSE_CASES:
        assert ctx.resolved_text(q) == q, f"{q!r} was spliced -> {ctx.resolved_text(q)!r}"


def test_command_referents_still_splice():
    """Genuine command continuations must still resolve the pronoun."""
    ctx = _ctx_with("notepad")
    for q in ["open it", "close that", "show it", "focus that", "run it", "search it"]:
        out = ctx.resolved_text(q)
        assert "notepad" in out, f"{q!r} -> {out!r}"


def test_media_modifiers_never_spliced():
    """"turn it up" / "make it louder" — "it" is the media object."""
    ctx = _ctx_with("notepad")
    for q in ["turn it up", "make it louder", "turn it down"]:
        assert ctx.resolved_text(q) == q, f"{q!r} -> {ctx.resolved_text(q)!r}"


def test_no_referent_leaves_commands_untouched():
    ctx = SessionContext(session_id="fresh")
    for q in ["open it", "why did you prefer that one"]:
        assert ctx.resolved_text(q) == q


def test_calculate_not_a_referent():
    """Deterministic utility results must never become the active entity."""
    from mini_kio.core.context_manager import _NON_REFERENT_ACTIONS
    for action in ("calculate", "convert", "time", "date", "weather", "utility"):
        assert action in _NON_REFERENT_ACTIONS, action


if __name__ == "__main__":
    test_discourse_never_spliced_with_stale_entity()
    print("ok: stale-entity discourse never spliced")
    test_discourse_never_spliced_with_real_entity()
    print("ok: real-entity discourse never spliced")
    test_command_referents_still_splice()
    print("ok: command referents splice")
    test_media_modifiers_never_spliced()
    print("ok: media modifiers never spliced")
    test_no_referent_leaves_commands_untouched()
    print("ok: no-referent untouched")
    test_calculate_not_a_referent()
    print("ok: calculate not a referent")
