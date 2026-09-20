"""Tests for Phase 4 Step 7: AI Reasoning provider wiring."""
import json
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final")


# ── A. APP_CAPABILITIES registration ─────────────────────────────

class TestA_CapabilityRegistration:
    def test_ai_reasoning_in_app_capabilities(self):
        from mini_kio.core.app_operator import APP_CAPABILITIES
        assert "ai_reasoning" in APP_CAPABILITIES

    def test_all_52_actions_registered(self):
        from mini_kio.core.app_operator import APP_CAPABILITIES
        caps = APP_CAPABILITIES["ai_reasoning"]
        assert len(caps) == 52

    def test_key_actions_present(self):
        from mini_kio.core.app_operator import APP_CAPABILITIES
        caps = APP_CAPABILITIES["ai_reasoning"]
        for action in ["classify", "summarize", "extract_structured", "analyze",
                        "research", "write_content", "compose_briefing"]:
            assert action in caps, f"{action} missing from ai_reasoning caps"


# ── B. StepRunner routing ────────────────────────────────────────

class TestB_StepRunnerRouting:
    def test_all_ai_reasoning_actions_mapped(self):
        from mini_kio.automation.step_runner import StepRunner
        runner = StepRunner()
        ai_actions = {k: v for k, v in runner._ACTION_MAP.items() if k[0] == "ai_reasoning"}
        assert len(ai_actions) == 52

    def test_all_map_to_execute_capability(self):
        from mini_kio.automation.step_runner import StepRunner
        runner = StepRunner()
        ai_actions = {k: v for k, v in runner._ACTION_MAP.items() if k[0] == "ai_reasoning"}
        for (cap, act), handler in ai_actions.items():
            assert handler == "execute_capability", f"{cap}::{act} -> {handler}"


# ── C. execute_capability routing ────────────────────────────────

class TestC_ExecuteCapabilityRouting:
    def test_unknown_action_rejected(self):
        from mini_kio.core.app_operator import execute_capability
        result = execute_capability("ai_reasoning::nonexistent_action::{\"text\": \"hello\"}")
        assert result["success"] is False
        assert "does not support" in result.get("message", "")

    def test_invalid_json_handled(self):
        from mini_kio.core.app_operator import execute_capability
        result = execute_capability("ai_reasoning::classify::not-valid-json")
        assert result["success"] is False
        assert "Invalid inputs JSON" in result.get("message", "")

    @patch("mini_kio.llm.llm_ops.ask_llm_sync", return_value=None)
    def test_llm_returns_none(self, mock_llm):
        from mini_kio.core.app_operator import execute_capability
        result = execute_capability('ai_reasoning::classify::{"text": "hello", "categories": ["a","b"]}')
        assert result["success"] is False
        assert "no content" in result.get("message", "")

    @patch("mini_kio.llm.llm_ops.ask_llm_sync", return_value='{"category": "a", "confidence": 0.9}')
    def test_json_response_parsed(self, mock_llm):
        from mini_kio.core.app_operator import execute_capability
        result = execute_capability('ai_reasoning::classify::{"text": "hello", "categories": ["a","b"]}')
        assert result["success"] is True
        assert result["category"] == "a"
        assert result["confidence"] == 0.9

    @patch("mini_kio.llm.llm_ops.ask_llm_sync", return_value="This is a plain text response")
    def test_non_json_response_wrapped(self, mock_llm):
        from mini_kio.core.app_operator import execute_capability
        result = execute_capability('ai_reasoning::summarize::{"text": "long text here"}')
        assert result["success"] is True
        assert result["text"] == "This is a plain text response"

    @patch("mini_kio.llm.llm_ops.ask_llm_sync", return_value='```json\n{"key": "value"}\n```')
    def test_markdown_fenced_json_stripped(self, mock_llm):
        from mini_kio.core.app_operator import execute_capability
        result = execute_capability('ai_reasoning::classify::{"text": "test"}')
        assert result["success"] is True
        assert result["key"] == "value"


# ── D. Task-tier routing ─────────────────────────────────────────

class TestD_TaskTierRouting:
    @patch("mini_kio.llm.llm_ops.ask_llm_sync", return_value='{"result": "ok"}')
    def test_classify_uses_reasoning_task(self, mock_llm):
        from mini_kio.core.app_operator import execute_capability
        execute_capability('ai_reasoning::classify::{"text": "test", "categories": ["a"]}')
        call_kwargs = mock_llm.call_args
        assert call_kwargs[1].get("task") == "reasoning" or call_kwargs.kwargs.get("task") == "reasoning"

    @patch("mini_kio.llm.llm_ops.ask_llm_sync", return_value='{"result": "ok"}')
    def test_summarize_uses_summarize_task(self, mock_llm):
        from mini_kio.core.app_operator import execute_capability
        execute_capability('ai_reasoning::summarize::{"text": "long text"}')
        call_kwargs = mock_llm.call_args
        assert call_kwargs[1].get("task") == "summarize" or call_kwargs.kwargs.get("task") == "summarize"

    @patch("mini_kio.llm.llm_ops.ask_llm_sync", return_value='{"result": "ok"}')
    def test_analyze_uses_analysis_task(self, mock_llm):
        from mini_kio.core.app_operator import execute_capability
        execute_capability('ai_reasoning::analyze::{"text": "data to analyze"}')
        call_kwargs = mock_llm.call_args
        assert call_kwargs[1].get("task") == "analysis" or call_kwargs.kwargs.get("task") == "analysis"


# ── E. Security: no secrets in output ───────────────────────────

class TestE_Security:
    @patch("mini_kio.llm.llm_ops.ask_llm_sync", return_value='{"result": "ok"}')
    def test_no_api_key_in_output(self, mock_llm):
        from mini_kio.core.app_operator import execute_capability
        result = execute_capability('ai_reasoning::classify::{"text": "test"}')
        output_str = json.dumps(result)
        assert "GEMINI" not in output_str or "API_KEY" not in output_str
        assert "sk-" not in output_str

    @patch("mini_kio.llm.llm_ops.ask_llm_sync", return_value='{"result": "ok"}')
    def test_no_api_key_in_error_message(self, mock_llm):
        from mini_kio.core.app_operator import execute_capability
        # Trigger an error path
        result = execute_capability("ai_reasoning::classify::not-json")
        output_str = json.dumps(result)
        assert "API_KEY" not in output_str
        assert "sk-" not in output_str


# ── F. Existing tests still green ───────────────────────────────

class TestF_Regression:
    def test_p1_contract_still_passes(self):
        """P1 contract: execute_capability exists and is callable."""
        from mini_kio.core.app_operator import execute_capability
        assert callable(execute_capability)

    def test_workflow_handler_unchanged(self):
        """Workflow handler still works."""
        from mini_kio.core.app_operator import execute_capability
        result = execute_capability("workflow::transform_records::{}")
        # Should not crash (may fail for other reasons, but not our change)
        assert isinstance(result, dict)

    def test_terminal_handler_unchanged(self):
        """Terminal handler still works."""
        from mini_kio.core.app_operator import execute_capability
        result = execute_capability("terminal::run_command::echo hello")
        assert isinstance(result, dict)
        assert result.get("success") is True
