import unittest

from mini_kio.llm.llm_gateway import LLMGateway


class TestLLMGateway(unittest.TestCase):

    def test_gateway_exists(self):
        gateway = LLMGateway()
        self.assertIsNotNone(gateway)