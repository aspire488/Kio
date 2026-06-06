"""
test_failure_tracking_verification.py — Gate 5.8 Provider Failure Tracking Verification

Forced failures against Gemini, OpenRouter, and Cerebras through the gateway.
Verifies: failure count, last_error, cooldown state, health transitions, recovery.
"""
import asyncio
import time
import unittest
from mini_kio.llm.provider_registry import (
    ProviderFailoverRegistry, ProviderState,
    DIAG_PROVIDER_FAILED, DIAG_PROVIDER_SKIPPED,
    DIAG_COOLDOWN_STARTED, DIAG_PROVIDER_HEALTH_TRANSITION,
    DIAG_PROVIDER_DEAD, DIAG_PROVIDER_RECOVERED,
    DIAG_PROVIDER_SELECTED,
)
from mini_kio.llm.provider_base import LLMProvider
from mini_kio.llm.models import LLMRequest, LLMResponse, LLMStatus
from mini_kio.llm.llm_gateway import LLMGateway


class _ControlledFailMock(LLMProvider):
    """Mock that fails N times then succeeds."""

    def __init__(self, name: str, error_code: str = "MOCK_FAIL",
                 fail_times: int = 999):
        self._name = name
        self._error_code = error_code
        self._fail_times = fail_times
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        if self.call_count <= self._fail_times:
            return LLMResponse(
                False, LLMStatus.ERROR, "",
                error_code=self._error_code, provider=self._name,
            )
        return LLMResponse(
            True, LLMStatus.SUCCESS,
            f"Response from {self._name}", provider=self._name,
        )

    async def health_check(self) -> bool:
        return True


class _SuccessMock(LLMProvider):
    def __init__(self, name: str = "success"):
        self._name = name
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            True, LLMStatus.SUCCESS,
            f"Response from {self._name}", provider=self._name,
        )

    async def health_check(self) -> bool:
        return True


class _FailOncePerCall(LLMProvider):
    """Fails once per generate() call. Always returns failure."""
    def __init__(self, name: str, error_code: str = "MOCK_FAIL"):
        self._name = name
        self._error_code = error_code
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            False, LLMStatus.ERROR, "",
            error_code=self._error_code, provider=self._name,
        )

    async def health_check(self) -> bool:
        return True


class TestFailureTrackingRegistryUnit(unittest.TestCase):
    """Unit tests on ProviderFailoverRegistry directly."""

    def setUp(self):
        self.registry = ProviderFailoverRegistry()

    # ── Gemini-style: quota exceeded → DEGRADED → COOLDOWN ──────────

    def test_gemini_quota_tracking(self):
        self.registry.register("gemini", 0)

        # Failure #1
        s = self.registry.record_failure("gemini", "GEMINI_QUOTA_EXCEEDED")
        self.assertEqual(s, ProviderState.DEGRADED)
        self.assertEqual(self.registry.get_failure_count("gemini"), 1)
        self.assertEqual(self.registry.get_last_error("gemini"), "GEMINI_QUOTA_EXCEEDED")
        self.assertGreater(self.registry.get_last_error_time("gemini"), 0)

        # Failure #2
        s = self.registry.record_failure("gemini", "GEMINI_QUOTA_EXCEEDED")
        self.assertEqual(s, ProviderState.DEGRADED)
        self.assertEqual(self.registry.get_failure_count("gemini"), 2)

        # Failure #3 → COOLDOWN (1800s for quota)
        s = self.registry.record_failure("gemini", "GEMINI_QUOTA_EXCEEDED")
        self.assertEqual(s, ProviderState.COOLDOWN)
        self.assertEqual(self.registry.get_failure_count("gemini"), 3)
        cd_until = self.registry._cooldown_until.get("gemini", 0)
        self.assertGreater(cd_until, time.time() + 1700)  # ~1800s cooldown

        # Verify diagnostics
        diag = self.registry.get_diagnostics()
        events = [d.event for d in diag]
        self.assertEqual(events.count(DIAG_PROVIDER_FAILED), 3)
        self.assertIn(DIAG_PROVIDER_HEALTH_TRANSITION, events)
        self.assertIn(DIAG_COOLDOWN_STARTED, events)
        # 2 transitions: fail #1 (HEALTHY→DEGRADED), fail #2 (already DEGRADED, still logged)
        # fail #3 skips transition because it enters COOLDOWN instead
        self.assertEqual(events.count(DIAG_PROVIDER_HEALTH_TRANSITION), 2)

    # ── OpenRouter-style: HTTP 402 → DEGRADED (not permanent) ──────

    def test_openrouter_402_tracking(self):
        self.registry.register("openrouter", 2)

        s = self.registry.record_failure("openrouter", "OPENROUTER_HTTP_402")
        self.assertEqual(s, ProviderState.DEGRADED)
        self.assertEqual(self.registry.get_failure_count("openrouter"), 1)
        self.assertEqual(self.registry.get_last_error("openrouter"), "OPENROUTER_HTTP_402")

        # Not permanent — the pattern "402" is not in PERMANENT_ERROR_PATTERNS
        self.assertNotEqual(self.registry.get_state("openrouter"), ProviderState.DEAD)

    # ── Cerebras-style: HTTP 404 → DEAD (permanent) ────────────────

    def test_cerebras_404_tracking(self):
        self.registry.register("cerebras", 4)

        s = self.registry.record_failure("cerebras", "CEREBRAS_HTTP_404")
        self.assertEqual(s, ProviderState.DEAD)
        self.assertEqual(self.registry.get_failure_count("cerebras"), 1)
        self.assertEqual(self.registry.get_last_error("cerebras"), "CEREBRAS_HTTP_404")
        self.assertTrue(self.registry.get_last_error_time("cerebras") > 0)

        # DEAD provider should be skipped
        chain = self.registry.get_chain()
        self.assertNotIn("cerebras", chain)

        # Verify skip diagnostic
        diag = self.registry.get_diagnostics()
        skip_events = [d for d in diag if d.event == DIAG_PROVIDER_SKIPPED]
        self.assertTrue(len(skip_events) >= 1)

    # ── last_error cleared on success ──────────────────────────────

    def test_last_error_cleared_on_success(self):
        self.registry.register("p", 0)
        self.registry.record_failure("p", "TIMEOUT")
        self.assertEqual(self.registry.get_last_error("p"), "TIMEOUT")

        self.registry.record_success("p")
        self.assertEqual(self.registry.get_last_error("p"), "")
        self.assertEqual(self.registry.get_last_error_time("p"), 0.0)
        self.assertEqual(self.registry.get_failure_count("p"), 0)
        self.assertEqual(self.registry.get_state("p"), ProviderState.HEALTHY)

    # ── snapshot includes last_error ───────────────────────────────

    def test_snapshot_includes_last_error(self):
        self.registry.register("gemini", 0)
        self.registry.record_failure("gemini", "GEMINI_QUOTA_EXCEEDED")

        snap = self.registry.snapshot()
        self.assertIn("last_error", snap)
        self.assertIn("last_error_time", snap)
        self.assertEqual(snap["last_error"]["gemini"], "GEMINI_QUOTA_EXCEEDED")
        self.assertGreater(snap["last_error_time"]["gemini"], 0)

    # ── reset clears last_error ────────────────────────────────────

    def test_reset_clears_last_error(self):
        self.registry.register("p", 0)
        self.registry.record_failure("p", "TIMEOUT")
        self.registry.reset()
        self.assertEqual(len(self.registry._last_error), 0)
        self.assertEqual(len(self.registry._last_error_time), 0)


class TestFailureTrackingGatewayIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests through LLMGateway.generate()."""

    async def asyncSetUp(self):
        self.gateway = LLMGateway()

    # ── Gemini: 3 quota failures → COOLDOWN tracked ────────────────

    async def test_gemini_quota_accumulates_failures(self):
        gemini = _FailOncePerCall("gemini", "GEMINI_QUOTA_EXCEEDED")
        groq = _SuccessMock("groq")
        self.gateway.register_provider(gemini, priority=0)
        self.gateway.register_provider(groq, priority=1)

        request = LLMRequest(prompt="hello")

        for i in range(3):
            resp = await self.gateway.generate(request)
            self.assertTrue(resp.success)  # groq handles it
            self.assertEqual(resp.provider, "groq")

        reg = self.gateway.get_registry()
        self.assertEqual(reg.get_failure_count("gemini"), 3)
        self.assertEqual(reg.get_last_error("gemini"), "GEMINI_QUOTA_EXCEEDED")
        self.assertEqual(reg.get_state("gemini"), ProviderState.COOLDOWN)

        # Query 4: gemini skipped (cooldown)
        resp = await self.gateway.generate(request)
        self.assertEqual(resp.provider, "groq")
        diag = self.gateway.get_diagnostics()
        skip_events = [d for d in diag if d.event == DIAG_PROVIDER_SKIPPED
                       and d.provider == "gemini"]
        self.assertTrue(len(skip_events) >= 1)

    # ── OpenRouter: 402 accumulates as non-permanent ────────────────

    async def test_openrouter_402_not_permanent(self):
        gemini = _FailOncePerCall("gemini", "MOCK_FAIL")
        openrouter = _FailOncePerCall("openrouter", "OPENROUTER_HTTP_402")
        groq = _SuccessMock("groq")
        self.gateway.register_provider(gemini, priority=0)
        self.gateway.register_provider(openrouter, priority=1)
        self.gateway.register_provider(groq, priority=2)

        request = LLMRequest(prompt="hello")

        for i in range(2):
            resp = await self.gateway.generate(request)
            self.assertTrue(resp.success, f"Query {i+1} should succeed via groq")
            self.assertEqual(resp.provider, "groq")

        reg = self.gateway.get_registry()

        # Both gemini and openrouter should have failures
        self.assertGreater(reg.get_failure_count("gemini"), 0)
        self.assertGreater(reg.get_failure_count("openrouter"), 0)

        # openrouter should NOT be DEAD (402 is not permanent)
        self.assertNotEqual(reg.get_state("openrouter"), ProviderState.DEAD)
        self.assertEqual(reg.get_last_error("openrouter"), "OPENROUTER_HTTP_402")

    # ── Cerebras: 404 → DEAD, skipped ──────────────────────────────

    async def test_cerebras_404_dead_and_skipped(self):
        gemini = _FailOncePerCall("gemini", "MOCK_FAIL")
        cerebras = _FailOncePerCall("cerebras", "CEREBRAS_HTTP_404")
        groq = _SuccessMock("groq")
        self.gateway.register_provider(gemini, priority=0)
        self.gateway.register_provider(cerebras, priority=1)
        self.gateway.register_provider(groq, priority=2)

        request = LLMRequest(prompt="hello")
        resp = await self.gateway.generate(request)
        self.assertTrue(resp.success)
        self.assertEqual(resp.provider, "groq")

        reg = self.gateway.get_registry()
        self.assertEqual(reg.get_state("cerebras"), ProviderState.DEAD)
        self.assertEqual(reg.get_last_error("cerebras"), "CEREBRAS_HTTP_404")
        self.assertEqual(reg.get_failure_count("cerebras"), 1)

    # ── Recovery: cooldown expiry → HEALTHY, no residual last_error ──

    async def test_recovery_clears_health_and_error_state(self):
        p = _FailOncePerCall("p", "TIMEOUT")
        self.gateway.register_provider(p, priority=0)

        request = LLMRequest(prompt="hello")

        # Trip cooldown (3 failures, but there's no other provider so chain exhausts)
        for _ in range(3):
            await self.gateway.generate(request)

        reg = self.gateway.get_registry()
        self.assertEqual(reg.get_state("p"), ProviderState.COOLDOWN)
        self.assertEqual(reg.get_last_error("p"), "TIMEOUT")

        # Manually expire cooldown to test recovery
        reg._cooldown_until["p"] = time.time() - 1

        # get_chain should trigger recovery
        chain = reg.get_chain()
        self.assertIn("p", chain)
        self.assertEqual(reg.get_state("p"), ProviderState.HEALTHY)
        self.assertEqual(reg.get_failure_count("p"), 0)
        self.assertEqual(reg.get_last_error("p"), "")
        self.assertEqual(reg.get_last_error_time("p"), 0.0)

    # ── Combined: all three, full state check ──────────────────────

    async def test_full_provider_state_accuracy(self):
        """All 4 providers registered, all fail except groq.
        Verify complete state snapshot accuracy."""
        gemini = _FailOncePerCall("gemini", "GEMINI_QUOTA_EXCEEDED")
        groq = _SuccessMock("groq")
        openrouter = _FailOncePerCall("openrouter", "OPENROUTER_HTTP_402")
        cerebras = _FailOncePerCall("cerebras", "CEREBRAS_HTTP_404")
        self.gateway.register_provider(gemini, priority=0)
        self.gateway.register_provider(groq, priority=1)
        self.gateway.register_provider(openrouter, priority=2)
        self.gateway.register_provider(cerebras, priority=3)

        request = LLMRequest(prompt="hello")

        # 3 queries to accumulate
        for _ in range(3):
            resp = await self.gateway.generate(request)
            self.assertTrue(resp.success)
            self.assertEqual(resp.provider, "groq")

        snap = self.gateway.get_registry().snapshot()
        self.assertIn("last_error", snap)
        self.assertIn("last_error_time", snap)

        # gemini: tried 3 times, all failed with quota
        self.assertEqual(snap["failures"].get("gemini"), 3)
        self.assertEqual(snap["last_error"].get("gemini"), "GEMINI_QUOTA_EXCEEDED")
        self.assertEqual(snap["states"].get("gemini"), ProviderState.COOLDOWN)

        # groq: always succeeded, no failures
        self.assertEqual(snap["failures"].get("groq"), 0)
        self.assertEqual(snap["last_error"].get("groq"), "")
        self.assertEqual(snap["states"].get("groq"), ProviderState.HEALTHY)

        # openrouter: never tried (gemini fails, groq succeeds, chain stops)
        self.assertEqual(snap["failures"].get("openrouter"), 0)
        self.assertEqual(snap["last_error"].get("openrouter"), "")

        # cerebras: never tried (same reason)
        self.assertEqual(snap["failures"].get("cerebras"), 0)
        self.assertEqual(snap["last_error"].get("cerebras"), "")


if __name__ == "__main__":
    unittest.main()
