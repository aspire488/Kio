import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from mini_kio.llm.freellm_provider import FreeLLMProvider
from mini_kio.llm.models import LLMRequest, LLMStatus


class TestFreeLLMProvider(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.provider = FreeLLMProvider(
            base_url="http://127.0.0.1:3001/v1/chat/completions",
            api_key="test-key",
            model="auto",
            timeout_s=5.0,
            max_tokens=100,
        )

    async def asyncTearDown(self):
        await self.provider.close()

    def _mock_response(self, status_code=200, json_data=None, text=""):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json = MagicMock(return_value=json_data)
        mock.text = text
        return mock

    async def test_successful_response(self):
        mock_resp = self._mock_response(json_data={
            "choices": [{"message": {"content": "Hello from FreeLLMAPI!"}}]
        })

        with patch.object(self.provider._client, "post", return_value=mock_resp):
            request = LLMRequest(prompt="Hi", provider="freellm")
            response = await self.provider.generate(request)

        self.assertTrue(response.success)
        self.assertEqual(response.status, LLMStatus.SUCCESS)
        self.assertEqual(response.content, "Hello from FreeLLMAPI!")
        self.assertEqual(response.provider, "freellm")

    async def test_timeout_handling(self):
        with patch.object(self.provider._client, "post", side_effect=asyncio.TimeoutError()):
            request = LLMRequest(prompt="Hi", provider="freellm", timeout_s=1.0)
            response = await self.provider.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.TIMEOUT)
        self.assertEqual(response.error_code, "FREELLM_TIMEOUT")

    async def test_unreachable_server(self):
        with patch.object(self.provider._client, "post", side_effect=httpx.ConnectError("Connection refused")):
            request = LLMRequest(prompt="Hi", provider="freellm")
            response = await self.provider.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.ERROR)
        self.assertEqual(response.error_code, "FREELLM_UNREACHABLE")

    async def test_malformed_json_response(self):
        mock_resp = self._mock_response()
        mock_resp.json = MagicMock(side_effect=ValueError("Expecting value"))

        with patch.object(self.provider._client, "post", return_value=mock_resp):
            request = LLMRequest(prompt="Hi", provider="freellm")
            response = await self.provider.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.MALFORMED)
        self.assertEqual(response.error_code, "FREELLM_EMPTY_RESPONSE")

    async def test_empty_response(self):
        mock_resp = self._mock_response(json_data={
            "choices": [{"message": {"content": ""}}]
        })

        with patch.object(self.provider._client, "post", return_value=mock_resp):
            request = LLMRequest(prompt="Hi", provider="freellm")
            response = await self.provider.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.MALFORMED)
        self.assertEqual(response.error_code, "FREELLM_EMPTY_RESPONSE")

    async def test_missing_choices(self):
        mock_resp = self._mock_response(json_data={"foo": "bar"})

        with patch.object(self.provider._client, "post", return_value=mock_resp):
            request = LLMRequest(prompt="Hi", provider="freellm")
            response = await self.provider.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.MALFORMED)
        self.assertEqual(response.error_code, "FREELLM_EMPTY_RESPONSE")

    async def test_http_non_200(self):
        mock_resp = self._mock_response(status_code=500, text="Internal Server Error")

        with patch.object(self.provider._client, "post", return_value=mock_resp):
            request = LLMRequest(prompt="Hi", provider="freellm")
            response = await self.provider.generate(request)

        self.assertFalse(response.success)
        self.assertEqual(response.status, LLMStatus.MALFORMED)
        self.assertEqual(response.error_code, "FREELLM_EMPTY_RESPONSE")

    def test_provider_name(self):
        self.assertEqual(self.provider.provider_name, "freellm")
