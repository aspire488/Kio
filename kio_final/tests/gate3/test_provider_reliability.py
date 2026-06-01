import unittest
import asyncio
import time
from mini_kio.llm.llm_gateway import LLMGateway
from mini_kio.llm.mock_provider import MockLLMProvider
from mini_kio.llm.models import LLMRequest, LLMStatus
from mini_kio.llm.provider_registry import ProviderState


class TestProviderReliability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.gateway = LLMGateway()

    async def test_circuit_breaker_activation(self):
        """Multiple failures on same provider trigger cooldown."""
        fail_provider = MockLLMProvider(mode="fail")
        self.gateway.register_provider(fail_provider)

        request = LLMRequest(prompt="test")

        # First call: 1 failure → DEGRADED
        await self.gateway.generate(request)
        state = self.gateway.get_registry().get_state("mock")
        self.assertEqual(state, ProviderState.DEGRADED)

        # Second call: 2nd failure → still DEGRADED (threshold is 3 for cooldown)
        await self.gateway.generate(request)
        state = self.gateway.get_registry().get_state("mock")
        self.assertEqual(state, ProviderState.DEGRADED)

    async def test_cooldown_after_multiple_failures(self):
        """Failures accumulate to trigger 60s cooldown on 3rd failure."""
        fail_provider = MockLLMProvider(mode="fail")
        self.gateway.register_provider(fail_provider)

        request = LLMRequest(prompt="test")

        # Three failures to trigger cooldown (COOLDOWN_THRESHOLD = 3)
        for _ in range(3):
            await self.gateway.generate(request)

        state = self.gateway.get_registry().get_state("mock")
        self.assertEqual(state, ProviderState.COOLDOWN)

    async def test_cooldown_provider_skipped(self):
        """Provider in cooldown is skipped in chain."""
        fail_provider = MockLLMProvider(mode="fail")
        self.gateway.register_provider(fail_provider)

        request = LLMRequest(prompt="test")

        # Trip cooldown (3 failures with COOLDOWN_THRESHOLD=3)
        for _ in range(3):
            await self.gateway.generate(request)

        state = self.gateway.get_registry().get_state("mock")
        self.assertEqual(state, ProviderState.COOLDOWN)

        # Next call: provider should be skipped
        response = await self.gateway.generate(request)
        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)

        # Verify cooldown-skip diagnostic
        diag = self.gateway.get_diagnostics()
        skip_events = [d for d in diag if d.event == "provider_skipped_cooldown"]
        self.assertTrue(len(skip_events) >= 1)

    async def test_auto_recovery_after_cooldown(self):
        """Provider auto-recovers to HEALTHY after cooldown expires."""
        fail_provider = MockLLMProvider(mode="fail")
        self.gateway.register_provider(fail_provider)

        request = LLMRequest(prompt="test")

        # Trigger cooldown
        for _ in range(3):
            await self.gateway.generate(request)

        state = self.gateway.get_registry().get_state("mock")
        self.assertEqual(state, ProviderState.COOLDOWN)

        # Manually expire cooldown
        self.gateway.get_registry()._cooldown_until["mock"] = time.time() - 1

        # Next call should recover and try the provider
        # But provider still fails, so chain exhausts
        response = await self.gateway.generate(request)
        self.assertFalse(response.success)

        # Recovery diagnostic
        diag = self.gateway.get_diagnostics()
        recovery_events = [d for d in diag if d.event == "provider_recovered"]
        self.assertTrue(len(recovery_events) >= 1)

    async def test_dead_provider_never_tried(self):
        """Provider with auth error goes DEAD and is never tried again."""
        provider = MockLLMProvider(mode="invalid_key")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="test")
        await self.gateway.generate(request)

        state = self.gateway.get_registry().get_state("mock")
        self.assertEqual(state, ProviderState.DEAD)

        # Second call — provider should be skipped (DEAD)
        start_count = provider._generate_count
        await self.gateway.generate(request)
        self.assertEqual(provider._generate_count, start_count)

    async def test_chain_failover_multiple_providers(self):
        """Failover chain advances through multiple providers."""
        class Fail1(MockLLMProvider):
            @property
            def provider_name(self): return "fail1"

        class Fail2(MockLLMProvider):
            @property
            def provider_name(self): return "fail2"

        class Success3(MockLLMProvider):
            @property
            def provider_name(self): return "success3"

        self.gateway.register_provider(Fail1(mode="fail"))
        self.gateway.register_provider(Fail2(mode="fail"))
        self.gateway.register_provider(Success3(mode="success"))

        request = LLMRequest(prompt="test")
        response = await self.gateway.generate(request)

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "success3")

    async def test_chain_exhaustion_fallback(self):
        """All providers fail → deterministic fallback response."""
        class AlwaysFail(MockLLMProvider):
            @property
            def provider_name(self): return "always_fail"

        self.gateway.register_provider(AlwaysFail(mode="fail"))
        self.gateway.register_provider(AlwaysFail(mode="fail"))

        request = LLMRequest(prompt="test")
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        self.assertIn("unable to connect", response.content.lower())

    async def test_malformed_response_rejection(self):
        """Malformed JSON response is rejected and chain advances."""
        malformed_provider = MockLLMProvider(mode="malformed_json")
        self.gateway.register_provider(malformed_provider)

        request = LLMRequest(prompt="Give me JSON")
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)

    async def test_diagnostics_provider_selected(self):
        """Diagnostics track provider_selected events on success."""
        provider = MockLLMProvider(mode="success")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="test")
        await self.gateway.generate(request)

        diag = self.gateway.get_diagnostics()
        events = [d.event for d in diag]
        self.assertIn("provider_selected", events)

    async def test_diagnostics_chain_exhausted(self):
        """Diagnostics track provider_chain_exhausted when all fail."""
        fail_provider = MockLLMProvider(mode="fail")
        self.gateway.register_provider(fail_provider)

        request = LLMRequest(prompt="test")
        await self.gateway.generate(request)

        diag = self.gateway.get_diagnostics()
        events = [d.event for d in diag]
        self.assertIn("provider_chain_exhausted", events)


if __name__ == "__main__":
    unittest.main()
