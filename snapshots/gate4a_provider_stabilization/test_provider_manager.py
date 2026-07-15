import unittest
import time
from mini_kio.llm.provider_manager import ProviderManager
from mini_kio.llm.models import ProviderHealthStatus, LLMStatus


class TestProviderManagerRegistration(unittest.TestCase):
    def setUp(self):
        self.mgr = ProviderManager()

    def test_duplicate_registration_rejected(self):
        self.mgr.register_provider("alpha")
        with self.assertRaises(ValueError):
            self.mgr.register_provider("alpha")

    def test_duplicate_registration_replace_allowed(self):
        self.mgr.register_provider("alpha")
        self.mgr.register_provider("alpha", replace=True)

    def test_duplicate_replace_resets_metrics(self):
        self.mgr.register_provider("alpha")
        self.mgr.record_failure("alpha", LLMStatus.ERROR)
        self.mgr.register_provider("alpha", replace=True)
        status = self.mgr.get_health_status("alpha")
        self.assertEqual(status, ProviderHealthStatus.HEALTHY)

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            self.mgr.register_provider("")

    def test_whitespace_name_rejected(self):
        with self.assertRaises(ValueError):
            self.mgr.register_provider("   ")

    def test_none_name_rejected(self):
        with self.assertRaises(ValueError):
            self.mgr.register_provider(None)

    def test_name_stripped_on_register(self):
        self.mgr.register_provider("  beta  ")
        status = self.mgr.get_health_status("beta")
        self.assertEqual(status, ProviderHealthStatus.HEALTHY)

    def test_multiple_unique_providers(self):
        self.mgr.register_provider("a")
        self.mgr.register_provider("b")
        self.mgr.register_provider("c")
        self.assertEqual(len(self.mgr._providers), 3)


class TestProviderManagerHealthTransitions(unittest.TestCase):
    def setUp(self):
        self.mgr = ProviderManager()
        self.mgr.register_provider("p1")
        self.mgr.FAILURE_THRESHOLD = 2

    def test_initial_health_is_healthy(self):
        status = self.mgr.get_health_status("p1")
        self.assertEqual(status, ProviderHealthStatus.HEALTHY)

    def test_single_failure_returns_unstable(self):
        self.mgr.record_failure("p1", LLMStatus.ERROR)
        status = self.mgr.get_health_status("p1")
        self.assertEqual(status, ProviderHealthStatus.UNSTABLE)

    def test_success_clears_unstable(self):
        self.mgr.record_failure("p1", LLMStatus.ERROR)
        self.mgr.record_success("p1")
        status = self.mgr.get_health_status("p1")
        self.assertEqual(status, ProviderHealthStatus.HEALTHY)

    def test_threshold_failures_triggers_cooldown(self):
        self.mgr.record_failure("p1", LLMStatus.ERROR)
        self.mgr.record_failure("p1", LLMStatus.ERROR)
        status = self.mgr.get_health_status("p1")
        self.assertEqual(status, ProviderHealthStatus.COOLDOWN)

    def test_cooldown_expiry_returns_healthy(self):
        self.mgr.record_failure("p1", LLMStatus.ERROR)
        self.mgr.record_failure("p1", LLMStatus.ERROR)
        self.assertEqual(self.mgr.get_health_status("p1"), ProviderHealthStatus.COOLDOWN)
        self.mgr.expire_cooldown("p1")
        status = self.mgr.get_health_status("p1")
        self.assertEqual(status, ProviderHealthStatus.HEALTHY)

    def test_post_cooldown_is_selectable(self):
        self.mgr.record_failure("p1", LLMStatus.ERROR)
        self.mgr.record_failure("p1", LLMStatus.ERROR)
        self.mgr.expire_cooldown("p1")
        selected = self.mgr.select_provider("p1")
        self.assertEqual(selected, "p1")

    def test_repeated_failure_cooldown_cycle(self):
        for _ in range(4):
            for _ in range(2):
                self.mgr.record_failure("p1", LLMStatus.ERROR)
            self.assertEqual(self.mgr.get_health_status("p1"), ProviderHealthStatus.COOLDOWN)
            self.mgr.expire_cooldown("p1")
            self.assertEqual(self.mgr.get_health_status("p1"), ProviderHealthStatus.HEALTHY)

    def test_timeout_threshold_triggers_cooldown(self):
        self.mgr.TIMEOUT_THRESHOLD = 2
        self.mgr.record_failure("p1", LLMStatus.TIMEOUT)
        self.assertEqual(self.mgr.get_health_status("p1"), ProviderHealthStatus.UNSTABLE)
        self.mgr.record_failure("p1", LLMStatus.TIMEOUT)
        self.assertEqual(self.mgr.get_health_status("p1"), ProviderHealthStatus.COOLDOWN)

    def test_malformed_threshold_triggers_cooldown(self):
        self.mgr.MALFORMED_THRESHOLD = 2
        self.mgr.record_failure("p1", LLMStatus.MALFORMED)
        self.assertEqual(self.mgr.get_health_status("p1"), ProviderHealthStatus.UNSTABLE)
        self.mgr.record_failure("p1", LLMStatus.MALFORMED)
        self.assertEqual(self.mgr.get_health_status("p1"), ProviderHealthStatus.COOLDOWN)


class TestProviderManagerSelection(unittest.TestCase):
    def setUp(self):
        self.mgr = ProviderManager()

    def test_empty_registry_returns_none(self):
        result = self.mgr.select_provider()
        self.assertIsNone(result)

    def test_select_requested_when_healthy(self):
        self.mgr.register_provider("a")
        self.mgr.register_provider("b")
        result = self.mgr.select_provider("a")
        self.assertEqual(result, "a")

    def test_select_fallback_on_unhealthy(self):
        self.mgr.register_provider("a")
        self.mgr.register_provider("b")
        self.mgr.FAILURE_THRESHOLD = 1
        self.mgr.record_failure("a", LLMStatus.ERROR)
        result = self.mgr.select_provider("a")
        self.assertEqual(result, "b")

    def test_ordering_stable_across_calls(self):
        self.mgr.register_provider("x")
        self.mgr.register_provider("y")
        self.mgr.register_provider("z")
        first = self.mgr.select_provider()
        second = self.mgr.select_provider()
        self.assertEqual(first, second)

    def test_ordering_is_registration_order(self):
        self.mgr.register_provider("first")
        self.mgr.register_provider("second")
        result = self.mgr.select_provider()
        self.assertEqual(result, "first")

    def test_degraded_provider_skipped(self):
        self.mgr.register_provider("a")
        self.mgr.register_provider("b")
        self.mgr.FAILURE_THRESHOLD = 1
        self.mgr.record_failure("a", LLMStatus.ERROR)
        self.mgr.record_failure("a", LLMStatus.ERROR)
        result = self.mgr.select_provider()
        self.assertEqual(result, "b")

    def test_all_degraded_returns_none(self):
        self.mgr.register_provider("a")
        self.mgr.register_provider("b")
        self.mgr.FAILURE_THRESHOLD = 1
        self.mgr.record_failure("a", LLMStatus.ERROR)
        self.mgr.record_failure("a", LLMStatus.ERROR)
        self.mgr.record_failure("b", LLMStatus.ERROR)
        self.mgr.record_failure("b", LLMStatus.ERROR)
        result = self.mgr.select_provider()
        self.assertIsNone(result)


class TestProviderManagerEdgeCases(unittest.TestCase):
    def setUp(self):
        self.mgr = ProviderManager()

    def test_record_success_unknown_is_noop(self):
        self.mgr.record_success("nonexistent")

    def test_record_failure_unknown_is_noop(self):
        self.mgr.record_failure("nonexistent", LLMStatus.ERROR)

    def test_invalid_name_in_record_success(self):
        with self.assertRaises(ValueError):
            self.mgr.record_success("")

    def test_invalid_name_in_record_failure(self):
        with self.assertRaises(ValueError):
            self.mgr.record_failure("", LLMStatus.ERROR)

    def test_invalid_name_in_get_health_status(self):
        with self.assertRaises(ValueError):
            self.mgr.get_health_status("")

    def test_invalid_name_in_expire_cooldown(self):
        with self.assertRaises(ValueError):
            self.mgr.expire_cooldown("")

    def test_expire_cooldown_unregistered_raises(self):
        with self.assertRaises(ValueError):
            self.mgr.expire_cooldown("ghost")

    def test_unregistered_returns_down(self):
        status = self.mgr.get_health_status("unknown")
        self.assertEqual(status, ProviderHealthStatus.DOWN)

    def test_select_provider_unknown_requested_no_fallback(self):
        self.mgr.register_provider("a")
        result = self.mgr.select_provider("unknown")
        self.assertEqual(result, "a")

    def test_register_case_sensitive_is_distinct(self):
        self.mgr.register_provider("Provider")
        self.mgr.register_provider("provider")
        self.assertIn("Provider", self.mgr._providers)
        self.assertIn("provider", self.mgr._providers)


if __name__ == "__main__":
    unittest.main()
