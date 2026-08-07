"""
R5a regression tests: KIO's own error replies and mojibake must be excluded
from the conversation window fed to the LLM, so stale failure text can't
pollute follow-up replies.
"""
from mini_kio.core.pipeline import _bad_kio_reply
from mini_kio.core.context_manager import SessionContext


def test_bad_reply_detects_error_prefixes():
    assert _bad_kio_reply("Error: Couldn't play interstellar trailer on YouTube")
    assert _bad_kio_reply("Couldn't play messi on YouTube")
    assert _bad_kio_reply("I couldn't pick out a fact to remember from that")
    assert _bad_kio_reply("")


def test_bad_reply_detects_mojibake():
    assert _bad_kio_reply("Lionel Messi \ufffdrenowned Argentine footballer")
    assert _bad_kio_reply("interstellar trailer Ã©Ã§")


def test_good_replies_kept():
    assert not _bad_kio_reply("Searched: Interstellar")
    assert not _bad_kio_reply("Played believer on YouTube")
    assert not _bad_kio_reply("Lionel Messi is a renowned Argentine footballer")
    assert not _bad_kio_reply("Done.")


def test_history_window_filters_bad_replies():
    ctx = SessionContext(session_id="r5a_test")
    ctx.append_exchange("play messi", "Error: Couldn't play messi on YouTube")
    ctx.append_exchange("who is messi", "Lionel Messi is a renowned Argentine footballer.")
    ctx.append_exchange("search again", "Searched: Interstellar")

    history = ctx.get_history_window(6)
    filtered = [(u, r) for u, r in history if not _bad_kio_reply(r)]

    assert len(filtered) == 2
    assert all("Couldn't" not in r and "Error:" not in r for _, r in filtered)
    # Order preserved (oldest first), error exchange dropped but good ones kept.
    assert filtered[0][0] == "who is messi"
    assert filtered[1][0] == "search again"
