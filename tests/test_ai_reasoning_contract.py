"""Step 9: Focused tests for ai_reasoning output-field contract repair."""
import json
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ask_llm_sync is imported locally inside execute_capability, so we patch
# it at its source module, not on app_operator.
_MOCK_TARGET = "mini_kio.llm.llm_ops.ask_llm_sync"


class TestA_ActionOutputFieldsMapping:
    """Verify the _ACTION_OUTPUT_FIELDS dict covers all 47 YAML actions."""

    def test_mapping_exists_in_source(self):
        import mini_kio.core.app_operator as mod
        source = open(mod.__file__, encoding="utf-8").read()
        assert "_ACTION_OUTPUT_FIELDS" in source

    def test_mapping_covers_47_actions(self):
        import re
        import mini_kio.core.app_operator as mod
        source = open(mod.__file__, encoding="utf-8").read()
        # Find the dict block between _ACTION_OUTPUT_FIELDS = { and the closing }
        start = source.index("_ACTION_OUTPUT_FIELDS")
        dict_block = source[start:start+4000]
        entries = re.findall(r'"(\w+)":\s*\[', dict_block)
        assert len(entries) >= 47, f"Expected >= 47 entries, got {len(entries)}"

    def test_classify_has_category_and_confidence(self):
        import re
        import mini_kio.core.app_operator as mod
        source = open(mod.__file__, encoding="utf-8").read()
        start = source.index("_ACTION_OUTPUT_FIELDS")
        chunk = source[start:start+4000]
        match = re.search(r'"classify":\s*\[(.*?)\]', chunk)
        assert match, "classify entry not found in _ACTION_OUTPUT_FIELDS"
        fields = re.findall(r'"(\w+)"', match.group(1))
        assert "category" in fields
        assert "confidence" in fields

    def test_triage_ticket_has_all_four_fields(self):
        import re
        import mini_kio.core.app_operator as mod
        source = open(mod.__file__, encoding="utf-8").read()
        start = source.index("_ACTION_OUTPUT_FIELDS")
        chunk = source[start:start+4000]
        match = re.search(r'"triage_ticket":\s*\[(.*?)\]', chunk)
        assert match, "triage_ticket entry not found"
        fields = re.findall(r'"(\w+)"', match.group(1))
        for f in ["topic", "urgency", "sentiment", "suggested_reply"]:
            assert f in fields, f"triage_ticket missing field: {f}"

    def test_summarize_includes_all_fields(self):
        import re
        import mini_kio.core.app_operator as mod
        source = open(mod.__file__, encoding="utf-8").read()
        start = source.index("_ACTION_OUTPUT_FIELDS")
        chunk = source[start:start+4000]
        match = re.search(r'"summarize":\s*\[(.*?)\]', chunk)
        assert match
        fields = re.findall(r'"(\w+)"', match.group(1))
        for f in ["summary", "action_items", "key_points"]:
            assert f in fields


class TestB_SystemPromptConstruction:
    """Verify the system prompt includes field names for known actions."""

    def test_classify_prompt_includes_category(self):
        import re
        import mini_kio.core.app_operator as mod
        source = open(mod.__file__, encoding="utf-8").read()
        # Find the prompt construction block
        assert "EXACTLY these fields" in source
        # Verify the prompt template exists
        assert "_required = _ACTION_OUTPUT_FIELDS.get(cap)" in source

    def test_fallback_prompt_for_unknown_action(self):
        import mini_kio.core.app_operator as mod
        source = open(mod.__file__, encoding="utf-8").read()
        assert "else:" in source
        assert "no markdown fences, no explanation." in source


class TestC_ExtractOutputsSimulation:
    """Simulate StepRunner._extract_outputs to verify field extraction works."""

    def _extract(self, result, declared_outputs):
        result_data = result.get("data", result.get("result", result))
        outputs = {}
        for name in declared_outputs:
            if isinstance(result_data, dict) and name in result_data:
                outputs[name] = result_data[name]
            elif name in result:
                outputs[name] = result[name]
            else:
                outputs[name] = None
        return outputs

    def test_classify_fields_extracted(self):
        result = {"success": True, "category": "tech", "confidence": 0.9}
        out = self._extract(result, ["category", "confidence"])
        assert out["category"] == "tech"
        assert out["confidence"] == 0.9

    def test_triage_fields_extracted(self):
        result = {"success": True, "topic": "Auth", "urgency": "high",
                  "sentiment": "angry", "suggested_reply": "Helping."}
        out = self._extract(result, ["topic", "urgency", "sentiment", "suggested_reply"])
        assert all(v is not None for v in out.values())

    def test_summarize_fields_extracted(self):
        result = {"success": True, "summary": "Up 15%", "action_items": ["Do X"], "key_points": ["A"]}
        out = self._extract(result, ["summary", "action_items", "key_points"])
        assert out["summary"] == "Up 15%"
        assert out["action_items"] == ["Do X"]

    def test_wrong_keys_yield_none(self):
        result = {"success": True, "KIO": "tech"}
        out = self._extract(result, ["category", "confidence"])
        assert out["category"] is None
        assert out["confidence"] is None


class TestD_MockAdapterPath:
    """Test the full adapter path with mocked LLM."""

    def _run(self, action, inputs, mock_content):
        from unittest.mock import patch
        from mini_kio.core.app_operator import execute_capability
        target = f"ai_reasoning::{action}::{json.dumps(inputs)}"
        with patch(_MOCK_TARGET, return_value=mock_content):
            return execute_capability(target)

    def test_classify_returns_correct_fields(self):
        r = self._run("classify", {"item": "bug", "categories": ["tech"]},
                       json.dumps({"category": "tech", "confidence": 0.95}))
        assert r["success"] is True
        assert r["category"] == "tech"
        assert r["confidence"] == 0.95

    def test_triage_returns_all_fields(self):
        r = self._run("triage_ticket", {"subject": "broken", "body": "help"},
                       json.dumps({"topic": "Login", "urgency": "high",
                                   "sentiment": "angry", "suggested_reply": "Fixing."}))
        assert r["success"] is True
        assert r["topic"] == "Login"
        assert r["urgency"] == "high"
        assert r["sentiment"] == "angry"
        assert r["suggested_reply"] == "Fixing."

    def test_summarize_returns_all_fields(self):
        r = self._run("summarize", {"text": "revenue up"},
                       json.dumps({"summary": "Q3 strong", "action_items": ["Publish"],
                                   "key_points": ["Up 15%"]}))
        assert r["success"] is True
        assert r["summary"] == "Q3 strong"
        assert r["action_items"] == ["Publish"]

    def test_markdown_fenced_json_stripped(self):
        r = self._run("classify", {"item": "x", "categories": ["a"]},
                       '```json\n{"category": "a", "confidence": 1.0}\n```')
        assert r["success"] is True
        assert r["category"] == "a"

    def test_malformed_json_wrapped(self):
        r = self._run("classify", {"item": "x"}, "not json")
        assert r["success"] is True
        assert r["text"] == "not json"

    def test_empty_response(self):
        from unittest.mock import patch
        from mini_kio.core.app_operator import execute_capability
        target = "ai_reasoning::classify::{\"item\": \"x\"}"
        with patch(_MOCK_TARGET, return_value=None):
            r = execute_capability(target)
        assert r["success"] is False
        assert "no content" in r["message"].lower()

    def test_unknown_action_rejected(self):
        from mini_kio.core.app_operator import execute_capability
        r = execute_capability("ai_reasoning::nonexistent::{\"x\":1}")
        assert r["success"] is False

    def test_invalid_json_inputs(self):
        from mini_kio.core.app_operator import execute_capability
        r = execute_capability("ai_reasoning::classify::not-json")
        assert r["success"] is False
        assert "invalid" in r["message"].lower()

    def test_no_secrets_in_output(self):
        r = self._run("classify", {"item": "x"}, json.dumps({"category": "a", "confidence": 1}))
        blob = json.dumps(r).lower()
        assert "sk-" not in blob
        assert "api_key" not in blob
        assert "gsk_" not in blob


class TestE_ProviderRouting:
    """Verify task-tier routing still works through ask_llm_sync."""

    def test_classify_uses_reasoning_task(self):
        from unittest.mock import patch
        from mini_kio.core.app_operator import execute_capability
        target = 'ai_reasoning::classify::{"item":"x"}'
        with patch(_MOCK_TARGET, return_value='{"category":"a","confidence":1}') as m:
            execute_capability(target)
            _, kwargs = m.call_args
            assert kwargs.get("task") == "reasoning"

    def test_summarize_uses_summarize_task(self):
        from unittest.mock import patch
        from mini_kio.core.app_operator import execute_capability
        target = 'ai_reasoning::summarize::{"text":"hi"}'
        with patch(_MOCK_TARGET, return_value='{"summary":"hi"}') as m:
            execute_capability(target)
            _, kwargs = m.call_args
            assert kwargs.get("task") == "summarize"

    def test_unknown_action_uses_analysis_task(self):
        from unittest.mock import patch
        from mini_kio.core.app_operator import execute_capability
        target = 'ai_reasoning::research::{"topic":"AI"}'
        with patch(_MOCK_TARGET, return_value='{"findings":"x"}') as m:
            execute_capability(target)
            _, kwargs = m.call_args
            assert kwargs.get("task") == "analysis"
