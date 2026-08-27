"""
test_deterministic_calculator.py

Focused tests for the deterministic calculator owner (Rule 10: arithmetic
must be deterministic — the numerical answer NEVER comes from the LLM or web
retrieval) and the date-sensitive routing owner (Rule 12: date-sensitive
current questions must be temporally grounded and research-routed).

Tests assert ROUTE and deterministic RESULT, never response wording.
"""

import pytest

from mini_kio.core.context_manager import clear_session_context, get_session_context
from mini_kio.core.pipeline import Pipeline
from mini_kio.core.pipeline.types import IntentType
from mini_kio.core.utilities import calculate_answer, looks_like_arithmetic


@pytest.fixture(autouse=True)
def _fresh():
    clear_session_context("calc_test")
    yield
    clear_session_context("calc_test")


def _classify(p: Pipeline, msg: str):
    ctx = get_session_context("calc_test")
    norm = p._normalizer.run(msg, ctx)
    d = p._classifier.classify(norm, msg)
    return p._apply_discourse_context_override(d, msg, ctx)


# ── deterministic calculator results ────────────────────────────────────────

@pytest.mark.parametrize("expr,expected", [
    ("6*7", "42"),
    ("2+8", "10"),
    ("2 + 8", "10"),
    ("4*68", "272"),
    ("6!", "720"),
    ("10/2", "5"),
    ("144/12", "12"),
    ("2**10", "1024"),
    ("(4+6)*3", "30"),
    ("1+2*3", "7"),
    ("7 % 3", "1"),
    ("15% of 200", "30"),
    ("9 factorial", "362880"),
    ("5 squared", "25"),
    ("square root of 144", "12"),
    ("2 to the power of 10", "1024"),
    ("what is 20 percent of 150", "30"),
])
def test_calculator_deterministic_results(expr, expected):
    r = calculate_answer(expr)
    assert r["success"] is True
    assert r["message"] == expected


def test_division_by_zero_is_deterministic_error():
    r = calculate_answer("6/0")
    assert r["success"] is False
    assert "division by zero" in r["message"].lower()


def test_invalid_expression_is_not_arithmetic():
    # Stray chat / version strings must never route to the calculator.
    assert looks_like_arithmetic("2-D2") is False
    assert looks_like_arithmetic("version 2.0") is False
    assert looks_like_arithmetic("haha lol") is False
    assert looks_like_arithmetic("R2-D2") is False


# ── arithmetic routing (never LLM, never web) ───────────────────────────────

@pytest.mark.parametrize("msg", [
    "what is 6*7", "What's 6*7", "2+8", "what is 2 + 8", "6!", "4*68",
    "6/0", "what is 9 factorial?", "what's 17 times 8?", "calculate 144 / 12",
    "2**10", "(4+6)*3", "what is 15% of 200",
])
def test_arithmetic_routes_to_utility_calculate(msg):
    d = _classify(Pipeline(), msg)
    assert d.intent_type == IntentType.UTILITY
    assert d.action == "calculate"


# ── date-sensitive routing (temporally grounded research) ──────────────────

@pytest.mark.parametrize("msg", [
    "Which country is celebrating independence day today?",
    "what happened today?",
    "What events are happening today?",
    "what is the holiday today",
    "which country celebrates independence day today",
])
def test_date_sensitive_queries_route_to_research(msg):
    d = _classify(Pipeline(), msg)
    assert d.intent_type == IntentType.INFORMATION
    assert d.action == "information_query"


def test_date_sensitive_query_is_temporally_anchored():
    import datetime
    d = _classify(Pipeline(), "Which country is celebrating independence day today?")
    month = datetime.datetime.now().strftime("%B")
    assert month in d.target
    assert "today" not in d.target.lower()


def test_greeting_with_date_phrase_is_not_hijacked():
    d = _classify(Pipeline(), "happy independence day kio")
    assert d.intent_type in (IntentType.SOCIAL, IntentType.GREETING)
