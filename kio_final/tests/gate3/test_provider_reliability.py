import unittest
import asyncio
import time
from mini_kio.llm.llm_gateway import LLMGateway
from mini_kio.llm.mock_provider import MockLLMProvider
from mini_kio.llm.models import LLMRequest, LLMStatus, ProviderHealthStatus


class TestProviderReliability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.gateway = LLMGateway()
        # Reduce thresholds for testing
        self.gateway._manager.FAILURE_THRESHOLD = 2
        self.gateway._manager.COOLDOWN_DURATION_S = 10

    async def test_circuit_breaker_activation(self):
        # 1. Register a provider that always fails
        fail_provider = MockLLMProvider(mode="fail")
        self.gateway.register_provider(fail_provider)
        
        request = LLMRequest(prompt="test", provider="mock")
        
        # 2. Trigger failures until circuit breaker trips
        # Gateway retries 3 times per call, so 1 call should trip it if threshold is 2
        response = await self.gateway.generate(request)
        self.assertEqual(response.status, LLMStatus.DEGRADED)
        
        # 3. Next call should be rejected immediately with NO_PROVIDER_AVAILABLE
        response2 = await self.gateway.generate(request)
        self.assertEqual(response2.error_code, "NO_PROVIDER_AVAILABLE")
        self.assertEqual(self.gateway._manager.get_health_status("mock"), ProviderHealthStatus.COOLDOWN)

    async def test_cooldown_enforcement_and_recovery(self):
        fail_provider = MockLLMProvider(mode="fail")
        self.gateway.register_provider(fail_provider)
        
        request = LLMRequest(prompt="test", provider="mock")
        await self.gateway.generate(request)
        
        # Cooldown active
        self.assertEqual(self.gateway._manager.get_health_status("mock"), ProviderHealthStatus.COOLDOWN)
        
        # Manually expire cooldown
        self.gateway._manager._metrics["mock"].cooldown_until = time.time() - 1
        
        # Should no longer be in cooldown
        self.assertNotEqual(self.gateway._manager.get_health_status("mock"), ProviderHealthStatus.COOLDOWN)

    async def test_retry_exhaustion_with_backoff(self):
        fail_provider = MockLLMProvider(mode="fail")
        # Set backoff to be very small for test speed
        self.gateway.INITIAL_BACKOFF_S = 0.01
        self.gateway.register_provider(fail_provider)
        
        start_time = time.monotonic()
        await self.gateway.generate(LLMRequest(prompt="test"))
        elapsed = time.monotonic() - start_time
        
        # 3 attempts (2 retries): 0.01 + 0.02 = 0.03s minimum sleep
        # range(3) is 0, 1, 2. Backoff called for 0 and 1.
        self.assertGreaterEqual(elapsed, 0.02)

    async def test_malformed_response_rejection(self):
        malformed_provider = MockLLMProvider(mode="malformed_json")
        self.gateway.register_provider(malformed_provider)
        
        request = LLMRequest(prompt="Give me JSON: {intent_type: 'executable'}")
        response = await self.gateway.generate(request)
        
        self.assertEqual(response.status, LLMStatus.DEGRADED)
        self.assertEqual(response.error_code, "MISSING_JSON_BRACES")

    async def test_failover_selection(self):
        # 1. Register one bad and one good provider
        bad_p = MockLLMProvider(mode="fail")
        # Change provider name to distinguish
        class GoodProvider(MockLLMProvider):
            @property
            def provider_name(self): return "good"
        
        good_p = GoodProvider(mode="success")
        
        self.gateway.register_provider(bad_p) # "mock"
        self.gateway.register_provider(good_p) # "good"
        
        # 2. Trip the "mock" provider
        await self.gateway.generate(LLMRequest(prompt="test", provider="mock"))
        self.assertEqual(self.gateway._manager.get_health_status("mock"), ProviderHealthStatus.COOLDOWN)
        
        # 3. Next request should failover to "good"
        response = await self.gateway.generate(LLMRequest(prompt="test", provider="mock"))
        self.assertTrue(response.success)
        self.assertEqual(response.provider, "good")

    async def test_timeout_containment(self):
        timeout_p = MockLLMProvider(mode="timeout_storm")
        self.gateway.register_provider(timeout_p)
        
        # Call with short timeout
        request = LLMRequest(prompt="test", timeout_s=0.1)
        response = await self.gateway.generate(request)
        
        self.assertEqual(response.status, LLMStatus.DEGRADED)


if __name__ == "__main__":
    unittest.main()
