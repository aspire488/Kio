"""
test_provider_failover_chain.py — Gate 5D Multi-Provider Failover Chain Tests

Coverage:
- Provider states (HEALTHY, DEGRADED, COOLDOWN, DEAD)
- Priority ordering
- Groq 429 → Gemini fallback (simulated via mock modes)
- Cooldown skipping
- Chain exhaustion → deterministic offline fallback
- Provider recovery after cooldown
- Bounded retry counts (exactly 1 per provider)
- Timeout handling
- Provider-specific error classification
- Diagnostics tracking
- No execution regression
- RAM budget verification (no persistent threads/workers)
"""

import asyncio
import time
import unittest
from mini_kio.llm.provider_registry import (
    ProviderFailoverRegistry, ProviderState, DiagnosticRecord,
    DIAG_PROVIDER_SELECTED, DIAG_PROVIDER_FAILED, DIAG_PROVIDER_SKIPPED,
    DIAG_COOLDOWN_STARTED, DIAG_CHAIN_EXHAUSTED, DIAG_PROVIDER_RECOVERED,
    DIAG_PROVIDER_DEAD, ProviderPriority,
)
from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus
from mini_kio.llm.mock_provider import MockLLMProvider
from mini_kio.llm.direct_providers import DirectHTTPProvider


# ══════════════════════════════════════════════════════════════════════
# Part 1: Provider Failover Registry (unit tests)
# ══════════════════════════════════════════════════════════════════════


class TestProviderFailoverRegistry(unittest.TestCase):
    """ProviderFailoverRegistry unit tests — states, cooldown, diagnostics."""

    def setUp(self):
        self.registry = ProviderFailoverRegistry()

    def test_register_adds_provider(self):
        self.registry.register("alpha", 0)
        self.assertIn("alpha", self.registry.get_providers())
        self.assertEqual(self.registry.get_state("alpha"), ProviderState.HEALTHY)

    def test_register_priority_ordering(self):
        self.registry.register("low", 5)
        self.registry.register("high", 0)
        self.registry.register("mid", 2)
        # Should be: high (priority 0), mid (priority 2), low (priority 5)
        chain = self.registry.get_chain()
        self.assertEqual(chain[0], "high")
        self.assertEqual(chain[1], "mid")
        self.assertEqual(chain[2], "low")

    def test_register_duplicate_skipped(self):
        self.registry.register("alpha", 0)
        self.registry.register("alpha", 1)  # Should be skipped
        providers = self.registry.get_providers()
        self.assertEqual(len(providers), 1)

    def test_state_healthy_initially(self):
        self.registry.register("p", 0)
        self.assertEqual(self.registry.get_state("p"), ProviderState.HEALTHY)

    def test_failure_transitions_to_degraded(self):
        self.registry.register("p", 0)
        self.registry.record_failure("p", "TIMEOUT")
        state = self.registry.get_state("p")
        self.assertEqual(state, ProviderState.DEGRADED)
        self.assertEqual(self.registry.get_failure_count("p"), 1)

    def test_three_failures_transitions_to_cooldown(self):
        self.registry.register("p", 0)
        for _ in range(3):
            self.registry.record_failure("p", "TIMEOUT")
        state = self.registry.get_state("p")
        self.assertEqual(state, ProviderState.COOLDOWN)
        self.assertEqual(self.registry.get_failure_count("p"), 3)

    def test_auth_error_transitions_to_dead(self):
        self.registry.register("p", 0)
        self.registry.record_failure("p", "INVALID_API_KEY")
        state = self.registry.get_state("p")
        self.assertEqual(state, ProviderState.DEAD)

    def test_success_after_failure_resets(self):
        self.registry.register("p", 0)
        self.registry.record_failure("p", "TIMEOUT")
        self.registry.record_success("p")
        state = self.registry.get_state("p")
        self.assertEqual(state, ProviderState.HEALTHY)
        self.assertEqual(self.registry.get_failure_count("p"), 0)

    def test_cooldown_skipped_in_chain(self):
        self.registry.register("p", 0)
        for _ in range(3):
            self.registry.record_failure("p", "TIMEOUT")
        chain = self.registry.get_chain()
        self.assertNotIn("p", chain)

    def test_cooldown_expiry_recovers(self):
        self.registry.register("p", 0)
        for _ in range(3):
            self.registry.record_failure("p", "TIMEOUT")
        # Simulate cooldown expiry
        self.registry._cooldown_until["p"] = time.time() - 1
        chain = self.registry.get_chain()
        self.assertIn("p", chain)
        state = self.registry.get_state("p")
        self.assertEqual(state, ProviderState.HEALTHY)

    def test_dead_provider_excluded_from_chain(self):
        self.registry.register("p", 0)
        self.registry.record_failure("p", "INVALID_API_KEY")
        chain = self.registry.get_chain()
        self.assertNotIn("p", chain)

    def test_chain_order_preserved(self):
        self.registry.register("a", 3)
        self.registry.register("b", 1)
        self.registry.register("c", 0)
        self.registry.register("d", 2)
        chain = self.registry.get_chain()
        self.assertEqual(chain, ["c", "b", "d", "a"])

    def test_dead_others_still_tried(self):
        self.registry.register("dead_p", 0)
        self.registry.register("good_p", 1)
        self.registry.record_failure("dead_p", "INVALID_API_KEY")
        chain = self.registry.get_chain()
        self.assertNotIn("dead_p", chain)
        self.assertIn("good_p", chain)

    def test_diagnostics_selected_event(self):
        self.registry.register("p", 0)
        self.registry.record_success("p")
        diag = self.registry.get_diagnostics()
        self.assertEqual(diag[0].event, DIAG_PROVIDER_SELECTED)

    def test_diagnostics_failed_event(self):
        self.registry.register("p", 0)
        self.registry.record_failure("p", "TIMEOUT")
        diag = self.registry.get_diagnostics()
        self.assertEqual(diag[0].event, DIAG_PROVIDER_FAILED)

    def test_diagnostics_cooldown_event(self):
        self.registry.register("p", 0)
        for _ in range(3):
            self.registry.record_failure("p", "TIMEOUT")
        diag = self.registry.get_diagnostics()
        events = [d.event for d in diag]
        self.assertIn(DIAG_COOLDOWN_STARTED, events)

    def test_diagnostics_skipped_event(self):
        self.registry.register("p", 0)
        for _ in range(3):
            self.registry.record_failure("p", "TIMEOUT")
        self.registry.get_chain()  # triggers skip diagnostic
        diag = self.registry.get_diagnostics()
        events = [d.event for d in diag]
        self.assertIn(DIAG_PROVIDER_SKIPPED, events)

    def test_diagnostics_dead_event(self):
        self.registry.register("p", 0)
        self.registry.record_failure("p", "INVALID_API_KEY")
        diag = self.registry.get_diagnostics()
        events = [d.event for d in diag]
        self.assertIn(DIAG_PROVIDER_DEAD, events)

    def test_diagnostics_recovered_event(self):
        self.registry.register("p", 0)
        for _ in range(3):
            self.registry.record_failure("p", "TIMEOUT")
        self.registry._cooldown_until["p"] = time.time() - 1
        self.registry.get_chain()  # triggers recovery
        diag = self.registry.get_diagnostics()
        events = [d.event for d in diag]
        self.assertIn(DIAG_PROVIDER_RECOVERED, events)

    def test_clear_diagnostics(self):
        self.registry.register("p", 0)
        self.registry.record_success("p")
        self.registry.clear_diagnostics()
        self.assertEqual(len(self.registry.get_diagnostics()), 0)

    def test_unknown_provider_returns_dead(self):
        state = self.registry.get_state("nonexistent")
        self.assertEqual(state, ProviderState.DEAD)

    def test_reset_clears_all(self):
        self.registry.register("p", 0)
        self.registry.record_success("p")
        self.registry.reset()
        self.assertEqual(len(self.registry.get_providers()), 0)
        self.assertEqual(len(self.registry.get_diagnostics()), 0)


# ══════════════════════════════════════════════════════════════════════
# Part 2: Provider-Specific Error Classification
# ══════════════════════════════════════════════════════════════════════


class TestProviderErrorClassification(unittest.TestCase):
    """Error patterns classified correctly per provider."""

    def _test_error_classification(self, error_code: str, expected_state: ProviderState):
        registry = ProviderFailoverRegistry()
        registry.register("p", 0)
        registry.record_failure("p", error_code)
        return registry.get_state("p")

    def test_invalid_api_key_dead(self):
        state = self._test_error_classification("INVALID_API_KEY", ProviderState.DEAD)
        self.assertEqual(state, ProviderState.DEAD)

    def test_auth_failed_dead(self):
        state = self._test_error_classification("AUTH_FAILED", ProviderState.DEAD)
        self.assertEqual(state, ProviderState.DEAD)

    def test_permission_denied_dead(self):
        state = self._test_error_classification("PERMISSION_DENIED", ProviderState.DEAD)
        self.assertEqual(state, ProviderState.DEAD)

    def test_gemini_auth_error_dead(self):
        state = self._test_error_classification("GEMINI_AUTH_ERROR", ProviderState.DEAD)
        self.assertEqual(state, ProviderState.DEAD)

    def test_gemini_not_configured_dead(self):
        state = self._test_error_classification("GEMINI_NOT_CONFIGURED", ProviderState.DEAD)
        self.assertEqual(state, ProviderState.DEAD)

    def test_quota_exceeded_degraded(self):
        state = self._test_error_classification("FREELLM_RATE_LIMITED", ProviderState.DEGRADED)
        self.assertEqual(state, ProviderState.DEGRADED)

    def test_timeout_degraded(self):
        state = self._test_error_classification("TIMEOUT", ProviderState.DEGRADED)
        self.assertEqual(state, ProviderState.DEGRADED)

    def test_unreachable_degraded(self):
        state = self._test_error_classification("FREELLM_UNREACHABLE", ProviderState.DEGRADED)
        self.assertEqual(state, ProviderState.DEGRADED)

    def test_server_error_degraded(self):
        state = self._test_error_classification("TOGETHER_AI_SERVER_ERROR", ProviderState.DEGRADED)
        self.assertEqual(state, ProviderState.DEGRADED)

    def test_cerebras_overloaded_degraded(self):
        state = self._test_error_classification("CEREBRAS_RATE_LIMITED", ProviderState.DEGRADED)
        self.assertEqual(state, ProviderState.DEGRADED)

    def test_openrouter_upstream_failure_degraded(self):
        state = self._test_error_classification("OPENROUTER_UNAVAILABLE", ProviderState.DEGRADED)
        self.assertEqual(state, ProviderState.DEGRADED)


# ══════════════════════════════════════════════════════════════════════
# Part 3: Multi-Provider Failover Chain Integration
# ══════════════════════════════════════════════════════════════════════


class _FailMock(LLMProvider):
    """A mock that always fails with a specific error."""

    def __init__(self, name: str, error_code: str = "MOCK_FAIL"):
        self._name = name
        self._error_code = error_code
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        if "429" in self._error_code or "RATE_LIMIT" in self._error_code:
            return LLMResponse(False, LLMStatus.DEGRADED, "", error_code=self._error_code, provider=self._name)
        if "QUOTA" in self._error_code:
            return LLMResponse(False, LLMStatus.DEGRADED, "", error_code=self._error_code, provider=self._name)
        if "TIMEOUT" in self._error_code:
            raise asyncio.TimeoutError()
        if "AUTH" in self._error_code or "INVALID_KEY" in self._error_code:
            return LLMResponse(False, LLMStatus.ERROR, "", error_code=self._error_code, provider=self._name)
        return LLMResponse(False, LLMStatus.ERROR, "", error_code=self._error_code, provider=self._name)

    async def health_check(self) -> bool:
        return True


class _SuccessMock(LLMProvider):
    """A mock that always succeeds."""

    def __init__(self, name: str = "success"):
        self._name = name
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(True, LLMStatus.SUCCESS, f"Response from {self._name}", provider=self._name)

    async def health_check(self) -> bool:
        return True


class TestMultiProviderFailoverChain(unittest.IsolatedAsyncioTestCase):
    """Integration tests for the failover chain via LLMGateway."""

    async def asyncSetUp(self):
        from mini_kio.llm.llm_gateway import LLMGateway
        self.gateway = LLMGateway()

    async def test_groq_429_fallsback_to_gemini(self):
        groq = _FailMock("groq", "FREELLM_RATE_LIMITED")
        gemini = _SuccessMock("gemini")
        self.gateway.register_provider(groq, priority=0)
        self.gateway.register_provider(gemini, priority=1)

        request = LLMRequest(prompt="hello")
        response = await self.gateway.generate(request)

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "gemini")
        self.assertEqual(groq.call_count, 1)
        self.assertEqual(gemini.call_count, 1)

    async def test_gemini_failure_fallsback_to_together(self):
        gemini = _FailMock("gemini", "GEMINI_QUOTA_EXCEEDED")
        together = _SuccessMock("together_ai")
        self.gateway.register_provider(gemini, priority=0)
        self.gateway.register_provider(together, priority=1)

        request = LLMRequest(prompt="hello")
        response = await self.gateway.generate(request)

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "together_ai")

    async def test_all_providers_fail_returns_deterministic_fallback(self):
        p1 = _FailMock("p1", "TIMEOUT")
        p2 = _FailMock("p2", "FREELLM_RATE_LIMITED")
        p3 = _FailMock("p3", "CEREBRAS_SERVER_ERROR")
        self.gateway.register_provider(p1, priority=0)
        self.gateway.register_provider(p2, priority=1)
        self.gateway.register_provider(p3, priority=2)

        request = LLMRequest(prompt="hello", timeout_s=2.0)
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        self.assertIn("unable to connect", response.content.lower())
        self.assertEqual(p1.call_count, 1)
        self.assertEqual(p2.call_count, 1)
        self.assertEqual(p3.call_count, 1)

    async def test_cooldown_provider_skipped(self):
        p = _FailMock("p", "MOCK_FAIL")
        self.gateway.register_provider(p, priority=0)
        request = LLMRequest(prompt="hello")

        # Trip cooldown (3 failures)
        for _ in range(3):
            await self.gateway.generate(request)

        state = self.gateway.get_registry().get_state("p")
        self.assertEqual(state, ProviderState.COOLDOWN)

        # Next call: provider should be skipped
        response = await self.gateway.generate(request)
        self.assertFalse(response.success)

        # call_count should NOT increase (skipped)
        diag = self.gateway.get_diagnostics()
        skip_events = [d for d in diag if d.event == DIAG_PROVIDER_SKIPPED]
        self.assertTrue(len(skip_events) >= 1)

    async def test_bounded_exactly_one_attempt_per_provider(self):
        """No per-provider retries. Each provider tried exactly once."""
        p = _FailMock("p", "TIMEOUT")
        self.gateway.register_provider(p, priority=0)

        request = LLMRequest(prompt="hello", timeout_s=1.0)
        await self.gateway.generate(request)

        self.assertEqual(p.call_count, 1)

    async def test_total_chain_timeout_bounded(self):
        """Chain does not hang — total timeout enforced."""
        t1 = _FailMock("t1", "TIMEOUT")
        t2 = _FailMock("t2", "TIMEOUT")
        self.gateway.register_provider(t1, priority=0)
        self.gateway.register_provider(t2, priority=1)

        start = time.monotonic()
        request = LLMRequest(prompt="hello", timeout_s=0.5)
        await self.gateway.generate(request)
        elapsed = time.monotonic() - start

        # Should complete quickly (not hang)
        self.assertLess(elapsed, 5.0)

    async def test_dead_provider_excluded(self):
        """DEAD provider is never tried across multiple calls."""
        p = _FailMock("p", "INVALID_API_KEY")
        self.gateway.register_provider(p, priority=0)

        request = LLMRequest(prompt="hello")
        await self.gateway.generate(request)

        state = self.gateway.get_registry().get_state("p")
        self.assertEqual(state, ProviderState.DEAD)

        # Second call — provider should be skipped (DEAD)
        count_before = p.call_count
        response = await self.gateway.generate(request)
        self.assertEqual(p.call_count, count_before)

    async def test_priority_higher_first(self):
        """Higher priority (lower number) provider is tried first."""
        low = _SuccessMock("low_priority")
        high = _SuccessMock("high_priority")
        self.gateway.register_provider(low, priority=10)
        self.gateway.register_provider(high, priority=0)

        request = LLMRequest(prompt="hello")
        response = await self.gateway.generate(request)

        # high_priority should be tried first and succeed
        self.assertEqual(response.provider, "high_priority")
        self.assertEqual(high.call_count, 1)
        self.assertEqual(low.call_count, 0)

    async def test_diagnostics_track_chain_exhausted(self):
        """Chain exhaustion is recorded in diagnostics."""
        p = _FailMock("p", "MOCK_FAIL")
        self.gateway.register_provider(p, priority=0)

        request = LLMRequest(prompt="hello")
        await self.gateway.generate(request)

        diag = self.gateway.get_diagnostics()
        events = [d.event for d in diag]
        self.assertIn(DIAG_CHAIN_EXHAUSTED, events)

    async def test_diagnostics_all_providers_tracked(self):
        """Each provider attempt is recorded in diagnostics."""
        p1 = _FailMock("p1", "MOCK_FAIL")
        p2 = _FailMock("p2", "MOCK_FAIL")
        self.gateway.register_provider(p1, priority=0)
        self.gateway.register_provider(p2, priority=1)

        request = LLMRequest(prompt="hello")
        await self.gateway.generate(request)

        diag = self.gateway.get_diagnostics()
        failed_events = [d for d in diag if d.event == DIAG_PROVIDER_FAILED]
        self.assertEqual(len(failed_events), 2)  # Both providers failed

    async def test_provider_recovery_after_cooldown(self):
        """Provider recovers to HEALTHY after cooldown expires."""
        p = _FailMock("p", "MOCK_FAIL")
        self.gateway.register_provider(p, priority=0)

        request = LLMRequest(prompt="hello")
        for _ in range(3):
            await self.gateway.generate(request)

        state = self.gateway.get_registry().get_state("p")
        self.assertEqual(state, ProviderState.COOLDOWN)

        # Manually expire cooldown
        self.gateway.get_registry()._cooldown_until["p"] = time.time() - 1

        # Next call should try the provider again
        response = await self.gateway.generate(request)
        self.assertFalse(response.success)

        diag = self.gateway.get_diagnostics()
        recovery_events = [d for d in diag if d.event == DIAG_PROVIDER_RECOVERED]
        self.assertTrue(len(recovery_events) >= 1)


# ══════════════════════════════════════════════════════════════════════
# Part 4: Direct HTTP Provider Tests
# ══════════════════════════════════════════════════════════════════════


class TestDirectHTTPProvider(unittest.TestCase):
    """Unit tests for DirectHTTPProvider error classification."""

    def setUp(self):
        self.provider = DirectHTTPProvider(
            name="test_provider",
            base_url="http://localhost:9999",
            api_key="test-key",
            model="test-model",
            timeout_s=1.0,
        )

    def test_provider_name(self):
        self.assertEqual(self.provider.provider_name, "test_provider")

    def test_health_check_no_key(self):
        provider = DirectHTTPProvider("x", "http://x.com", "", timeout_s=1)
        self.assertFalse(asyncio.run(provider.health_check()))

    def test_health_check_with_key(self):
        self.assertTrue(asyncio.run(self.provider.health_check()))

    def test_classify_429(self):
        code = self.provider._classify_http_error(429, "")
        self.assertEqual(code, "TEST_PROVIDER_RATE_LIMITED")

    def test_classify_401(self):
        code = self.provider._classify_http_error(401, "")
        self.assertEqual(code, "TEST_PROVIDER_AUTH_ERROR")

    def test_classify_403(self):
        code = self.provider._classify_http_error(403, "")
        self.assertEqual(code, "TEST_PROVIDER_AUTH_ERROR")

    def test_classify_503(self):
        code = self.provider._classify_http_error(503, "")
        self.assertEqual(code, "TEST_PROVIDER_UNAVAILABLE")

    def test_classify_502(self):
        code = self.provider._classify_http_error(502, "")
        self.assertEqual(code, "TEST_PROVIDER_UNAVAILABLE")

    def test_classify_500(self):
        code = self.provider._classify_http_error(500, "")
        self.assertEqual(code, "TEST_PROVIDER_SERVER_ERROR")

    def test_classify_404(self):
        code = self.provider._classify_http_error(404, "")
        self.assertEqual(code, "TEST_PROVIDER_HTTP_404")


# ══════════════════════════════════════════════════════════════════════
# Part 5: Provider Isolation Verification
# ══════════════════════════════════════════════════════════════════════


class TestProviderIsolation(unittest.TestCase):
    """Verify providers are text-only, no state mutation, no execution."""

    def test_direct_provider_has_no_execution_methods(self):
        methods = [m for m in dir(DirectHTTPProvider) if not m.startswith('_')]
        banned = ['execute', 'run', 'dispatch', 'tool', 'action', 'stream']
        for m in methods:
            for b in banned:
                self.assertNotIn(b, m.lower(),
                    f"Provider has banned method: {m}")

    def test_provider_registry_has_no_execution_methods(self):
        methods = [m for m in dir(ProviderFailoverRegistry) if not m.startswith('_')]
        banned = ['execute', 'run', 'dispatch', 'tool', 'action', 'stream']
        for m in methods:
            for b in banned:
                self.assertNotIn(b, m.lower(),
                    f"Registry has banned method: {m}")


# ══════════════════════════════════════════════════════════════════════
# Part 6: Execution Non-Regression
# ══════════════════════════════════════════════════════════════════════


class TestExecutionNonRegression(unittest.TestCase):
    """Gate 5D changes must not affect execution paths."""

    def test_ask_llm_still_returns_optional_string(self):
        """Interface compatibility: ask_llm returns Optional[str]."""
        from mini_kio.core.llm_router import ask_llm

        # Verify the function signature hasn't changed
        import inspect
        sig = inspect.signature(ask_llm)
        params = list(sig.parameters.keys())
        self.assertIn("query", params)
        self.assertIn("timeout", params)
        self.assertIn("max_tokens", params)

    def test_llm_gateway_still_returns_llm_response(self):
        """Interface compatibility: generate returns LLMResponse."""
        from mini_kio.llm.llm_gateway import LLMGateway
        from mini_kio.llm.models import LLMResponse

        gw = LLMGateway()
        import asyncio
        response = asyncio.run(gw.generate(LLMRequest(prompt="test")))
        self.assertIsInstance(response, LLMResponse)


# ══════════════════════════════════════════════════════════════════════
# Part 7: RAM Budget Verification
# ══════════════════════════════════════════════════════════════════════


class TestRAMBudget(unittest.TestCase):
    """No persistent threads, no background workers, no long-lived state."""

    def test_no_threading_import_in_provider_registry(self):
        import mini_kio.llm.provider_registry as pr
        import inspect
        source = inspect.getsource(pr)
        self.assertNotIn("threading", source)
        self.assertNotIn("Thread", source)
        self.assertNotIn("Process", source)

    def test_no_threading_import_in_direct_providers(self):
        import mini_kio.llm.direct_providers as dp
        import inspect
        source = inspect.getsource(dp)
        self.assertNotIn("threading", source)
        self.assertNotIn("Thread", source)
        self.assertNotIn("Process", source)

    def test_no_persistent_workers(self):
        import mini_kio.llm.provider_registry as pr
        import mini_kio.llm.direct_providers as dp
        for mod in [pr, dp]:
            import inspect
            source = inspect.getsource(mod)
            self.assertNotIn("while True", source)
            self.assertNotIn("background", source.lower())


if __name__ == "__main__":
    unittest.main()
