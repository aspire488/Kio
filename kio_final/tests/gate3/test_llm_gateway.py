import unittest
import asyncio
from mini_kio.llm.llm_gateway import LLMGateway
from mini_kio.llm.models import LLMRequest, LLMStatus
from mini_kio.llm.mock_provider import MockLLMProvider


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

    async def test_timeout_handling_and_retry(self):
        provider = MockLLMProvider(mode="timeout")
        self.gateway.register_provider(provider)
        
        # Set short timeout for test efficiency
        request = LLMRequest(prompt="Test timeout", timeout_s=0.1)
        response = await self.gateway.generate(request)
        
        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)
        self.assertEqual(response.error_code, "TIMEOUT")
        # Ensure retries happened (1 initial + 2 retries = 3 total)
        self.assertEqual(provider._generate_count, 3)

    async def test_empty_response_rejection(self):
        provider = MockLLMProvider(mode="empty")
        self.gateway.register_provider(provider)
        
        request = LLMRequest(prompt="Test empty")
        response = await self.gateway.generate(request)
        
        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)
        self.assertEqual(response.error_code, "EMPTY_RESPONSE")

    async def test_provider_failure_handling(self):
        provider = MockLLMProvider(mode="fail")
        self.gateway.register_provider(provider)
        
        request = LLMRequest(prompt="Test failure")
        response = await self.gateway.generate(request)
        
        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.DEGRADED)
        self.assertIn("PROVIDER_ERROR", response.error_code)

    async def test_no_provider_available(self):
        request = LLMRequest(prompt="Test no provider")
        response = await self.gateway.generate(request)
        
        self.assertFalse(response.success)
        self.assertEqual(response.error_code, "NO_PROVIDER_AVAILABLE")

    async def test_token_limit_enforcement(self):
        # This test ensures we don't crash when tokens are requested
        # Note: Actual clamping is in logic but request object still holds original value 
        # unless we modify it in generate.
        provider = MockLLMProvider(mode="success")
        self.gateway.register_provider(provider)
        
        request = LLMRequest(prompt="Big prompt", max_tokens=10000)
        response = await self.gateway.generate(request)
        self.assertTrue(response.success)
        # Clamping logic is internal to generate(), 
        # in future we might verify it via provider capture.
