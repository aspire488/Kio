"""
Stale-discard regression tests for kio_bot.py _is_failure_response.

Invariant: when a newer request exists for the same session, an older reply
is discarded UNLESS it is a failure the user needs to see. Informational
content ("Nothing is playing right now.") is NOT a failure — it is eligible
for stale-discard.
"""
import unittest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIsFailureResponse(unittest.TestCase):
    """Test the _is_failure_response classifier in isolation."""

    def _classify(self, reply: str) -> bool:
        from kio_bot import _is_failure_response
        return _is_failure_response(reply)

    # ── Informational responses (NOT failures → eligible for stale-discard) ──

    def test_nothing_is_playing_not_failure(self):
        """'Nothing is playing right now.' is informational, not a failure."""
        self.assertFalse(self._classify("Nothing is playing right now."))

    def test_nothing_found_not_failure(self):
        """'Nothing found.' is informational."""
        self.assertFalse(self._classify("Nothing found."))

    def test_done_not_failure(self):
        """'Done.' is a success, not a failure."""
        self.assertFalse(self._classify("Done."))

    def test_success_message_not_failure(self):
        """Typical success responses are not failures."""
        self.assertFalse(self._classify("Opened Chrome."))

    def test_informational_status_not_failure(self):
        """Status responses are not failures."""
        self.assertFalse(self._classify("KIO is online and ready."))

    # ── Failure responses (NOT eligible for stale-discard) ──

    def test_i_couldnt_find_is_failure(self):
        """'I couldn't find anything.' is a user-critical failure."""
        self.assertTrue(self._classify("I couldn't find anything."))

    def test_i_couldnt_start_is_failure(self):
        """'I couldn't start Notepad.' is a failure."""
        self.assertTrue(self._classify("I couldn't start Notepad."))

    def test_i_dont_know_is_failure(self):
        """'I don't know how to do that.' is a failure."""
        self.assertTrue(self._classify("I don't know how to do that."))

    def test_failed_in_response_is_failure(self):
        """Response containing 'failed' is a failure."""
        self.assertTrue(self._classify("The operation failed."))

    def test_error_in_response_is_failure(self):
        """Response containing 'error' is a failure."""
        self.assertTrue(self._classify("An error occurred."))

    def test_lowercase_failed_is_failure(self):
        """Case-insensitive 'failed' detection."""
        self.assertTrue(self._classify("FAILED to open."))

    def test_lowercase_error_is_failure(self):
        """Case-insensitive 'error' detection."""
        self.assertTrue(self._classify("error: connection refused."))

    # ── Edge cases ──

    def test_empty_string_not_failure(self):
        """Empty reply is not a failure."""
        self.assertFalse(self._classify(""))

    def test_none_not_failure(self):
        """None reply is not a failure (handler guards with `reply and ...`)."""
        self.assertFalse(self._classify(None))  # type: ignore[arg-type]

    def test_nothing_with_error_is_failure(self):
        """'Nothing happened because of an error' — error marker wins."""
        self.assertTrue(self._classify("Nothing happened because of an error."))

    def test_i_couldnt_with_nothing_is_failure(self):
        """'I couldn't find anything' — 'I couldn't' marker wins."""
        self.assertTrue(self._classify("I couldn't find anything."))


class TestStaleDiscardIntegration(unittest.TestCase):
    """Test the stale-discard logic end-to-end using the helper function.

    These tests verify the LOGIC that the Telegram handler uses, without
    needing a live Telegram connection.
    """

    def _should_discard(self, my_seq: int, cur_seq: int, done_seq: int, reply: str) -> bool:
        """Simulate the stale-discard decision from kio_bot.py."""
        from kio_bot import _is_failure_response
        if my_seq < cur_seq and done_seq < cur_seq and not _is_failure_response(reply):
            return True
        return False

    def test_informational_response_is_discarded_when_stale(self):
        """'Nothing is playing right now.' IS discarded when a newer request exists."""
        # Session state: request 2 is current, request 1 is old, request 1 hasn't completed yet
        self.assertTrue(self._should_discard(
            my_seq=1, cur_seq=2, done_seq=1,
            reply="Nothing is playing right now."
        ))

    def test_failure_response_is_preserved_when_stale(self):
        """'I couldn't find anything.' is NOT discarded even when newer request exists."""
        self.assertFalse(self._should_discard(
            my_seq=1, cur_seq=2, done_seq=1,
            reply="I couldn't find anything."
        ))

    def test_success_response_is_discarded_when_stale(self):
        """Normal success response IS discarded when stale."""
        self.assertTrue(self._should_discard(
            my_seq=1, cur_seq=2, done_seq=1,
            reply="Opened Chrome."
        ))

    def test_failure_with_error_is_preserved_when_stale(self):
        """Response containing 'error' is NOT discarded."""
        self.assertFalse(self._should_discard(
            my_seq=1, cur_seq=2, done_seq=1,
            reply="An error occurred while opening Chrome."
        ))

    def test_not_stale_never_discarded(self):
        """When request is NOT stale (my_seq == cur_seq), never discard."""
        self.assertFalse(self._should_discard(
            my_seq=2, cur_seq=2, done_seq=1,
            reply="Nothing is playing right now."
        ))

    def test_already_completed_not_discarded(self):
        """When request is already completed (done >= cur), never discard."""
        self.assertFalse(self._should_discard(
            my_seq=1, cur_seq=2, done_seq=2,
            reply="Nothing is playing right now."
        ))


class TestSessionCounterLogic(unittest.TestCase):
    """Test the sequence counter increment/discard lifecycle."""

    def test_counter_increments_monotonically(self):
        """Counter increments for each new request."""
        counter = {}
        completed = {}
        user_id = 42

        # Simulate 3 requests
        for i in range(3):
            counter[user_id] = counter.get(user_id, 0) + 1

        self.assertEqual(counter[user_id], 3)

    def test_completed_tracks_max(self):
        """Completed counter tracks the maximum processed sequence."""
        completed = {}
        user_id = 42

        # Simulate completing requests 1 and 3 (out of order)
        completed[user_id] = max(completed.get(user_id, 0), 1)
        completed[user_id] = max(completed.get(user_id, 0), 3)

        self.assertEqual(completed[user_id], 3)

    def test_stale_detection_with_counter(self):
        """Full stale-discard scenario with counter lifecycle.

        Real handler behavior (kio_bot.py lines 269-283):
        1. Request arrives → increment counter → record my_seq
        2. route() executes (may take time)
        3. After route() returns → check stale → send or discard

        Stale check: my_seq < cur AND done < cur AND not _is_failure_response(reply)

        NOTE: The done < cur guard means that if a NEWER request completes
        BEFORE an older one, the older one's stale check sees done >= cur
        and is NOT discarded. This is a known limitation — the guard was
        added to prevent newer requests from being incorrectly discarded
        but has the side effect of preserving stale older replies when
        newer requests complete first. This test documents the ACTUAL behavior.
        """
        from kio_bot import _is_failure_response

        counter = {}
        completed = {}

        def dispatch():
            """Simulate request dispatch (increments counter)."""
            counter["u"] = counter.get("u", 0) + 1
            return counter["u"]

        def stale_check(my_seq, reply):
            """Simulate the stale check after route() returns."""
            cur = counter.get("u", 0)
            done = completed.get("u", 0)
            is_stale = my_seq < cur and done < cur and not _is_failure_response(reply)
            if not is_stale:
                completed["u"] = max(done, my_seq)
            return is_stale

        # ── Scenario 1: Informational response discarded when stale ──
        # Request 1 dispatched (slow), Request 2 dispatched and completes first
        seq1 = dispatch()  # seq=1
        seq2 = dispatch()  # seq=2

        # Request 2 completes (not stale: my_seq == cur)
        self.assertFalse(stale_check(seq2, "Done."))
        # done is now 2

        # Request 1 completes (my_seq=1 < cur=2, but done=2 >= cur=2)
        # Due to done < cur guard: NOT stale in this scenario
        # This is the ACTUAL behavior — documented, not changed
        self.assertFalse(stale_check(seq1, "Nothing is playing right now."))

        # ── Scenario 2: Stale detection works when requests complete IN ORDER ──
        counter = {}
        completed = {}

        seq1 = dispatch()  # seq=1
        seq2 = dispatch()  # seq=2

        # Request 1 completes FIRST (stale: my_seq=1 < cur=2, done=0 < cur=2)
        self.assertTrue(stale_check(seq1, "Nothing is playing right now."))

        # Request 2 completes (not stale: my_seq == cur)
        self.assertFalse(stale_check(seq2, "Done."))

        # ── Scenario 3: Failure response survives staleness ──
        counter = {}
        completed = {}

        seq1 = dispatch()
        seq2 = dispatch()

        # Request 1 fails (stale check says stale, but _is_failure_response saves it)
        self.assertFalse(stale_check(seq1, "I couldn't find anything."))

        # ── Scenario 4: Error response survives staleness ──
        counter = {}
        completed = {}

        seq1 = dispatch()
        seq2 = dispatch()

        self.assertFalse(stale_check(seq1, "An error occurred."))


if __name__ == "__main__":
    unittest.main()
