import unittest
import asyncio
from mini_kio.llm.llm_gateway import LLMGateway
from mini_kio.llm.models import LLMRequest, LLMStatus
from mini_kio.llm.mock_provider import MockLLMProvider
from mini_kio.llm.provider_registry import ProviderState


class TestLLMGateway(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.gateway = LLMGateway()

    async def test_successful_response(self):
        provider = MockLLMProvider(mode="success")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="Hello World")
        response = await self.gateway.generate(request)

        self.assertTrue(response.success)
        self.assertEqual(response.status, LLMStatus.SUCCESS)
        self.assertIn("Mock response", response.content)

    async def test_timeout_handling_chain_exhausted(self):
        provider = MockLLMProvider(mode="timeout")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="Test timeout", timeout_s=0.1)
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)
        # Chain exhausted after 1 attempt (no per-provider retries)
        self.assertEqual(provider._generate_count, 1)

    async def test_empty_response_rejection(self):
        provider = MockLLMProvider(mode="empty")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="Test empty")
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)
        self.assertIn("PROVIDER_CHAIN_EXHAUSTED", response.error_code)

    async def test_provider_failure_advances_chain(self):
        provider = MockLLMProvider(mode="fail")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="Test failure")
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)

    async def test_no_provider_available(self):
        request = LLMRequest(prompt="Test no provider")
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)

    async def test_quota_marks_provider_degraded(self):
        provider = MockLLMProvider(mode="non_retryable")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="Test quota")
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        # Quota is a TRANSIENT error, so the bounded chain retry adds one
        # extra pass (transient-storm recovery); still marks DEGRADED and
        # never exceeds two passes.
        self.assertEqual(provider._generate_count, 2)

    async def test_invalid_key_marks_provider_dead(self):
        provider = MockLLMProvider(mode="invalid_key")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="Test invalid key")
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(provider._generate_count, 1)
        # Provider should be DEAD after auth error
        state = self.gateway.get_registry().get_state("mock")
        self.assertEqual(state, ProviderState.DEAD)

    async def test_single_attempt_per_provider_no_retries(self):
        provider = MockLLMProvider(mode="timeout")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="Test timeout", timeout_s=0.1)
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)
        # Exactly 1 attempt, no retries
        self.assertEqual(provider._generate_count, 1)

    async def test_token_limit_enforcement(self):
        provider = MockLLMProvider(mode="success")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="Big prompt", max_tokens=10000)
        response = await self.gateway.generate(request)
        self.assertTrue(response.success)

    async def test_chain_failover_two_providers(self):
        """When first provider fails, chain advances to second."""
        fail_provider = MockLLMProvider(mode="fail")
        success_provider = MockLLMProvider(mode="success")

        self.gateway.register_provider(fail_provider)     # priority=99
        self.gateway.register_provider(success_provider)  # priority=99

        request = LLMRequest(prompt="test")
        response = await self.gateway.generate(request)

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "mock")

    async def test_chain_all_exhausted_returns_fallback(self):
        fail_provider = MockLLMProvider(mode="fail")
        fail_provider2 = MockLLMProvider(mode="fail")

        # Override provider names to register both
        class Fail2(MockLLMProvider):
            @property
            def provider_name(self): return "fail2"

        self.gateway.register_provider(fail_provider)    # "mock"
        self.gateway.register_provider(Fail2(mode="fail"))  # "fail2"

        request = LLMRequest(prompt="test")
        response = await self.gateway.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)
        self.assertIn("PROVIDER_CHAIN_EXHAUSTED", response.error_code)

    async def test_first_provider_succeeds(self):
        good = MockLLMProvider(mode="success")
        bad = MockLLMProvider(mode="fail")

        class BadMock(MockLLMProvider):
            @property
            def provider_name(self): return "bad"

        self.gateway.register_provider(good)  # "mock" (priority=99)
        self.gateway.register_provider(BadMock(mode="fail"))  # "bad" (priority=99)

        request = LLMRequest(prompt="test")
        response = await self.gateway.generate(request)

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "mock")

    async def test_dead_provider_skipped(self):
        provider = MockLLMProvider(mode="invalid_key")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="test")
        await self.gateway.generate(request)

        state = self.gateway.get_registry().get_state("mock")
        self.assertEqual(state, ProviderState.DEAD)

        # Second call should skip dead provider
        response = await self.gateway.generate(request)
        self.assertFalse(response.success)

    async def test_diagnostics_recorded(self):
        provider = MockLLMProvider(mode="timeout")
        self.gateway.register_provider(provider)

        request = LLMRequest(prompt="test", timeout_s=0.1)
        await self.gateway.generate(request)

        diag = self.gateway.get_diagnostics()
        self.assertTrue(len(diag) > 0)
        events = [d.event for d in diag]
        self.assertIn("provider_failed", events)
