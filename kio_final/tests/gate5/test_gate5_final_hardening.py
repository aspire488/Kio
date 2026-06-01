"""
test_gate5_final_hardening.py — Final Gate 5 Stabilization Validation

Validates:
1. Compound typo normalization
2. Emoji sanitization
3. Browser canonicalization
4. Educational authority precedence
5. Safe tab ownership
6. Stale handle protection
"""

import pytest
from mini_kio.llm.input_normalizer import InputNormalizer
from mini_kio.core.routing_utils import get_browser_routing, get_browser_registry
from mini_kio.browser.browser_tab_controller import BrowserTabController
from mini_kio.browser.browser_action_validator import BrowserActionValidator
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.llm.intent_models import IntentType, IntentClassification, ExtractedIntent
from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult, ExecutionAuditMetadata

def test_emoji_sanitization():
    normalizer = InputNormalizer()
    text = "Open chrome🙂‍↕️"
    sanitized = normalizer.sanitize(text)
    assert "🙂‍↕️" not in sanitized
    assert sanitized == "open chrome"
    assert normalizer.get_diag()["emoji_sanitize_applied"] is True

def test_url_preservation_during_sanitize():
    normalizer = InputNormalizer()
    text = "Open https://google.com/search?q=kio! 🙂"
    sanitized = normalizer.sanitize(text)
    assert "https://google.com/search?q=kio!" in sanitized
    assert "🙂" not in sanitized
    assert "!" in sanitized # preserve punctuation

def test_compound_typo_normalization():
    normalizer = InputNormalizer()
    text = "pythn baiscs"
    normalized = normalizer.normalize_typos(text)
    assert normalized == "python basics"
    
    text2 = "recusrion in pythn"
    normalized2 = normalizer.normalize_typos(text2)
    assert normalized2 == "recursion in python"
    assert normalizer.get_diag()["typo_normalization_applied"] is True

def test_browser_canonicalization():
    # Reset registry diag
    get_browser_registry()._diag["browser_canonicalization_used"] = 0
    
    # Test IG -> Instagram
    route = get_browser_routing("ig")
    assert "instagram" in route["target"]
    assert route["canonical_target"] == "instagram"
    assert get_browser_registry().get_diagnostics()["browser_canonicalization_used"] > 0

    # Test Insta -> Instagram
    route2 = get_browser_routing("insta")
    assert "instagram" in route2["target"]
    assert route2["canonical_target"] == "instagram"

def test_educational_authority_precedence():
    responder = ConversationResponder()
    
    # Mock orchestration for "teach me python"
    intent = ExtractedIntent("teach me python", "teach me python", 1.0, IntentType.EDUCATIONAL)
    classification = IntentClassification(intent, is_safe=True)
    orchestration = OrchestrationResponse(
        state=OrchestrationState.CONVERSATIONAL,
        response_text="teach me python",
        intent_type=IntentType.EDUCATIONAL,
        metadata={"educational_state_preserved": True}
    )
    
    mock_audit = ExecutionAuditMetadata("user", "validated", "none", True)
    handoff = RuntimeHandoffResult(True, ExecutionClassification.CONVERSATIONAL_ONLY, "Lesson 1", mock_audit)
    
    response = responder.generate("teach me python", orchestration, handoff)
    assert "Python" in response or "couldn't retrieve information" in response
    assert responder.get_context_diagnostics()["educational_authority_used"] > 0

def test_safe_tab_ownership():
    controller = BrowserTabController()
    validator = BrowserActionValidator(controller)
    
    # 1. Register a KIO tab
    controller.track_tab("tab_123", "chrome_1", "https://kio.dev", "KIO")
    
    # 2. Validate destructive action on KIO tab -> PASS
    assert validator.validate_action("close_tab", "tab_123") is True
    
    # 3. Validate destructive action on unknown tab -> FAIL
    assert validator.validate_action("close_tab", "user_tab_456") is False
    assert validator.get_diagnostics()["destructive_action_blocked"] > 0

def test_stale_handle_protection():
    controller = BrowserTabController()
    # Mock an old tab
    controller.track_tab("old_tab", "chrome_1", "...", "...")
    controller._tabs["old_tab"].created_at = 0 # Epoch
    
    controller.prune_stale_tabs(max_age_s=3600)
    assert "old_tab" not in controller._tabs
    assert controller.get_diagnostics()["stale_handle_protection_triggered"] > 0
