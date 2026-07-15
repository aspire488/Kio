import unittest
from unittest.mock import MagicMock, patch
import asyncio
from mini_kio.core.llm_router import ask_llm, _get_gateway
import mini_kio.core.llm_router

class TestLLMRouterWiring(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Reset singleton
        mini_kio.core.llm_router._GATEWAY = None

    @patch('mini_kio.core.config.GEMINI_API_KEY', 'test-key')
    @patch('mini_kio.core.config.GEMINI_MODEL', 'test-model-2.0')
    async def test_ask_llm_uses_configured_model(self):
        """Verify that ask_llm initializes the primary provider with the correct model."""
        with patch('mini_kio.core.llm_router.GeminiProvider') as MockProvider:
            mock_instance = MagicMock()
            mock_instance.provider_name = "gemini"
            MockProvider.return_value = mock_instance
            await ask_llm("test query")
            
            MockProvider.assert_called_once()
            args, kwargs = MockProvider.call_args
            self.assertEqual(kwargs.get('model_name'), 'test-model-2.0')

    @patch('mini_kio.core.config.GEMINI_API_KEY', 'test-key')
    async def test_ask_llm_routes_through_gateway(self):
        """Verify that ask_llm calls gateway.generate."""
        gateway = _get_gateway()
        with patch.object(gateway, 'generate') as mock_generate:
            mock_generate.return_value = MagicMock(success=True, content="Test response")
            
            result = await ask_llm("hello")
            
            self.assertEqual(result, "Test response")
            mock_generate.assert_called_once()
            request = mock_generate.call_args[0][0]
            self.assertEqual(request.prompt, "hello")
