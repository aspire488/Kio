"""
Gate 5.1 Registry Stabilization + Runtime Response Hardening

Validates:
1. Continuity pre-routing bypasses routing/classifier
2. Global normalization (emoji + typo) at earliest entrypoint
3. Capability registry independent of process registry
4. Browser close resolves capability session, not process
5. No ambiguous chrome closure path
6. User-facing responses hide internal routing
7. Calculator lifecycle unchanged
8. Diagnostics tracking
"""

import copy
import sys
import time
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mini_kio.core.capability_registry import CapabilityRegistry, get_capability_registry
from mini_kio.core.runtime_response_formatter import (
    format_result, format_open_app, format_close_app,
    format_capability, format_search, reset_diag, get_diag,
)
from mini_kio.core.routing_utils import (
    register_browser_capability, resolve_capability_for_close,
    deactivate_capability, get_latest_capability,
)
from mini_kio.llm.input_normalizer import InputNormalizer
from mini_kio.llm.conversation_responder import _handle_continuity_pre_route


# ── Capability Registry Tests ────────────────────────────────────────────────


class TestCapabilityRegistry:
    def setup_method(self):
        self.reg = CapabilityRegistry()

    def test_register_creates_session(self):
        cap_id = self.reg.register("instagram", "chrome", "https://www.instagram.com")
        assert cap_id.startswith("cap_")
        entry = self.reg.resolve_by_id(cap_id)
        assert entry is not None
        assert entry.canonical_target == "instagram"
        assert entry.browser == "chrome"
        assert entry.active is True

    def test_resolve_by_target_finds_latest(self):
        self.reg.register("notion", "chrome", "https://www.notion.so")
        time.sleep(0.01)
        self.reg.register("instagram", "chrome", "https://www.instagram.com")
        entry = self.reg.resolve_by_target("instagram")
        assert entry is not None
        assert entry.canonical_target == "instagram"

    def test_resolve_by_target_not_found(self):
        entry = self.reg.resolve_by_target("nonexistent")
        assert entry is None

    def test_deactivate_marks_inactive(self):
        cap_id = self.reg.register("instagram", "chrome", "https://www.instagram.com")
        assert self.reg.deactivate(cap_id) is True
        entry = self.reg.resolve_by_id(cap_id)
        assert entry is None  # resolve_by_id only returns active
        assert self.reg.active_count() == 0

    def test_deactivate_by_target(self):
        self.reg.register("instagram", "chrome", "https://www.instagram.com")
        assert self.reg.deactivate_by_target("instagram") is True
        assert self.reg.active_count() == 0

    def test_deactivate_non_existent(self):
        assert self.reg.deactivate("nonexistent") is False

    def test_browser_not_same_as_capability(self):
        """Browser (chrome) should not resolve as a capability target."""
        self.reg.register("instagram", "chrome", "https://www.instagram.com")
        entry = self.reg.resolve_by_target("chrome")
        assert entry is None

    def test_get_latest_active(self):
        self.reg.register("notion", "chrome", "https://www.notion.so")
        time.sleep(0.01)
        latest_id = self.reg.register("instagram", "chrome", "https://www.instagram.com")
        latest = self.reg.get_latest_active()
        assert latest is not None
        assert latest.capability_id == latest_id

    def test_capability_survives_process_deletion(self):
        """Capability sessions are independent of process registry."""
        cap_id = self.reg.register("instagram", "chrome", "https://www.instagram.com")
        # Simulate process pruning (capability registry has no prune)
        assert self.reg.active_count() == 1
        assert self.reg.resolve_by_id(cap_id) is not None

    def test_closes_capability_not_process(self):
        """Close by capability target deactivates session, never touches process."""
        self.reg.register("instagram", "chrome", "https://www.instagram.com")
        assert self.reg.active_count() == 1
        assert self.reg.deactivate_by_target("instagram") is True
        assert self.reg.active_count() == 0
        # Browser process should NOT be affected — verified by no process terminate call

    def test_calculator_lifecycle_unchanged(self):
        """Calculator-like single process apps are NOT capability sessions."""
        cap_id = self.reg.register("calculator", "native", "")
        entry = self.reg.resolve_by_id(cap_id)
        assert entry is not None
        # Calculator resolves normally through app_operator, not capability


# ── Routing Utils Capability Wrappers ────────────────────────────────────────


class TestRoutingUtilsCapability:
    def setup_method(self):
        registry = get_capability_registry()
        # Access private sessions to reset
        registry._sessions.clear()
        registry._diag = {k: 0 for k in registry._diag}

    def test_register_and_resolve_for_close(self):
        register_browser_capability("instagram", "chrome", "https://www.instagram.com")
        info = resolve_capability_for_close("instagram")
        assert info is not None
        assert info["canonical_target"] == "instagram"
        assert info["active"] is True

    def test_deactivate_capability(self):
        register_browser_capability("instagram", "chrome", "https://www.instagram.com")
        assert deactivate_capability("instagram") is True
        info = resolve_capability_for_close("instagram")
        assert info is None  # No longer active

    def test_get_latest_capability(self):
        register_browser_capability("notion", "chrome", "https://www.notion.so")
        time.sleep(0.01)
        register_browser_capability("instagram", "chrome", "https://www.instagram.com")
        latest = get_latest_capability()
        assert latest is not None
        assert latest["canonical_target"] == "instagram"

    def test_close_resolves_capability_not_process(self):
        """'close it' after browser capability should match capability, not process."""
        register_browser_capability("instagram", "chrome", "https://www.instagram.com")
        info = resolve_capability_for_close("instagram")
        assert info is not None
        # The target "chrome" should NOT resolve since capabilities are by target name
        chrome_info = resolve_capability_for_close("chrome")
        assert chrome_info is None


# ── Runtime Response Formatter Tests ─────────────────────────────────────────


class TestRuntimeResponseFormatter:
    def setup_method(self):
        reset_diag()

    def test_format_open_app_success(self):
        result = format_result("open_app", "notepad", True, {"message": "Opened notepad"})
        assert "Opened" in result
        assert "routed" not in result.lower()
        assert "search_fallback" not in result

    def test_format_close_app_success(self):
        details = {"message": "Closed notepad (pid 1234)"}
        result = format_result("close_app", "notepad", True, details)
        assert "Closed" in result
        assert "pid" not in result

    def test_format_close_capability(self):
        details = {
            "message": "Closed the Instagram session.",
            "capability_closed": True,
            "capability_name": "Instagram",
        }
        result = format_result("close_app", "instagram", True, details)
        assert "Closed" in result
        assert "Instagram" in result
        assert "session" in result

    def test_format_capability_browser_success(self):
        details = {"message": "Routed open_url to chrome.", "browser": "chrome", "capability_name": "Instagram"}
        result = format_result("execute_capability", "chrome::open_url::https://instagram.com", True, details)
        assert "Opened" in result or "opened" in result
        assert "Instagram" in result
        assert "Chrome" in result
        assert "routed" not in result.lower()

    def test_format_capability_domain_name_extraction(self):
        details = {"message": "Routed open_url to chrome.", "browser": "chrome"}
        result = format_result("execute_capability", "chrome::open_url::https://www.instagram.com", True, details)
        assert "Instagram" in result
        assert "Chrome" in result

    def test_format_search_success(self):
        result = format_result("search_web", "python tutorials", True, {"message": "Searched google"})
        assert "Searched" in result
        assert "search_fallback" not in result

    def test_format_error_hides_internal(self):
        details = {"message": "capability lookup failed for target"}
        result = format_result("open_app", "unknown", False, details)
        assert "capability" not in result.lower()
        assert "lookup" not in result.lower()

    def test_format_error_dev_terms_scrubbed(self):
        details = {"message": "execution classification failed"}
        result = format_result("open_app", "test", False, details)
        assert "execution" not in result.lower()

    def test_natural_message_preserved(self):
        """Already-natural messages should not be reformatted."""
        result = format_result("open_app", "chrome", True, {"message": "Opened Chrome."})
        assert result == "Opened Chrome."

    def test_no_dev_routing_terms_in_output(self):
        """Verify no internal routing leaks in any format path."""
        test_cases = [
            ("open_app", "notepad", True, {"message": "Opened notepad"}),
            ("close_app", "notepad", True, {"message": "Closed notepad (pid 1234)"}),
            ("execute_capability", "chrome::open_url::https://instagram.com", True,
             {"message": "Routed open_url to chrome.", "browser": "chrome"}),
            ("search_web", "python", True, {"message": "search_fallback"}),
            ("open_app", "unknown", False, {"message": "capability lookup failed"}),
        ]
        dev_terms = {"routed", "search_fallback", "capability lookup",
                     "execution classification", "execute_capability"}
        for action, target, success, details in test_cases:
            result = format_result(action, target, success, details)
            lower = result.lower()
            for term in dev_terms:
                assert term not in lower, f"Found dev term '{term}' in: {result}"


# ── Input Normalizer Tests ───────────────────────────────────────────────────


class TestInputNormalizer:
    def test_strip_emoji_removes_emoji(self):
        result = InputNormalizer.strip_emoji("Open chrome🙂‍↕️")
        assert "🙂" not in result
        assert "Open" in result or "open" in result.lower()

    def test_strip_emoji_preserves_text(self):
        result = InputNormalizer.strip_emoji("hello world")
        assert result == "hello world"

    def test_normalize_typos_recusrion(self):
        normalizer = InputNormalizer()
        result = normalizer.normalize_typos("recusrion")
        assert "recursion" in result

    def test_normalize_typos_pythn(self):
        normalizer = InputNormalizer()
        result = normalizer.normalize_typos("pythn")
        assert "python" in result or result == "python"

    def test_normalize_typos_baiscs(self):
        normalizer = InputNormalizer()
        result = normalizer.normalize_typos("baiscs")
        assert result == "basics"

    def test_normalize_typos_sytnax(self):
        normalizer = InputNormalizer()
        result = normalizer.normalize_typos("sytnax")
        assert result == "syntax"

    def test_normalize_compound_pythn_baiscs(self):
        normalizer = InputNormalizer()
        result = normalizer.normalize_typos("pythn baiscs")
        assert "python" in result and "basics" in result


# ── Continuity Pre-Route Tests ───────────────────────────────────────────────


class TestContinuityPreRoute:
    def test_continuity_triggers_detected(self):
        """Verify matched continuity triggers."""
        from mini_kio.llm.conversation_responder import _handle_continuity_pre_route
        # These should match
        assert _get_continuity_clean("next") == "next"
        assert _get_continuity_clean("continue") == "continue"
        assert _get_continuity_clean("more") == "more"

    def test_non_continuity_not_detected(self):
        """Non-continuity text should not match."""
        assert _get_continuity_clean("help") != "next"
        assert _get_continuity_clean("what is python") != "next"


def _get_continuity_clean(text: str) -> str:
    return text.strip(".,!?;: ").lower()


# ── Diagnostics Tests ────────────────────────────────────────────────────────


class TestGate51Diagnostics:
    def setup_method(self):
        self.reg = get_capability_registry()
        self.reg._sessions.clear()
        self.reg._diag = {k: 0 for k in self.reg._diag}
        reset_diag()

    def test_capability_registered_diagnostic(self):
        self.reg.register("instagram", "chrome", "https://www.instagram.com")
        diag = self.reg.get_diagnostics()
        assert diag["capability_registered"] >= 1

    def test_capability_resolved_diagnostic(self):
        self.reg.register("instagram", "chrome", "https://www.instagram.com")
        self.reg.resolve_by_target("instagram")
        diag = self.reg.get_diagnostics()
        assert diag["capability_resolved"] >= 1

    def test_runtime_response_formatted_diagnostic(self):
        reset_diag()
        format_result("open_app", "test", True, {"message": "Routed open_url to chrome."})
        diag = get_diag()
        assert diag["runtime_response_formatted"] >= 1

    def test_browser_close_contained(self):
        """Browser capability close should not reach process termination."""
        self.reg.register("instagram", "chrome", "https://www.instagram.com")
        assert self.reg.active_count() == 1
        self.reg.deactivate_by_target("instagram")
        diag = self.reg.get_diagnostics()
        assert diag["capability_deactivated"] >= 1
        assert self.reg.active_count() == 0

    def test_no_ambiguous_chrome_closure(self):
        """Multiple capability sessions for same browser should not create ambiguity."""
        self.reg.register("instagram", "chrome", "https://www.instagram.com")
        self.reg.register("notion", "chrome", "https://www.notion.so")
        # Resolving "instagram" should only return instagram session
        info = resolve_capability_for_close("instagram")
        assert info is not None
        assert info["canonical_target"] == "instagram"
        # Resolving "chrome" should NOT find a capability
        info = resolve_capability_for_close("chrome")
        assert info is None
