import pytest
from mini_kio.core.command_router import handle_command
from mini_kio.core.runtime_response_formatter import _extract_url_name, format_result
from mini_kio.llm.conversation_context import ConversationContext
from mini_kio.llm.tone_normalizer import ToneNormalizer
from mini_kio.llm.identity_guard import IdentityGuard

def test_bug1_identity_consistency():
    # Test deterministic routing for identity
    res = handle_command("What exactly are you?")
    assert "KIO" in res["message"]
    assert "Joel" in res["message"]
    
    res = handle_command("Who built you?")
    assert "Joel" in res["message"]
    
    res = handle_command("Why were you created?")
    assert "operating companion" in res["message"].lower()
    
    # Test IdentityGuard rewrite
    guard = IdentityGuard()
    rewritten, violations = guard.check_and_rewrite("This was made by Meta.", "Who made you?")
    assert "Joel" in rewritten
    assert "Meta" not in rewritten

def test_bug3_pronoun_resolution():
    from mini_kio.core.context_manager import SessionContext
    ctx = SessionContext(session_id="p12_pronoun_test")
    ctx.active_entity = None
    ctx.last_target = "Spotify"

    resolved = ctx.resolved_text("close this")
    assert "close Spotify" in resolved

    resolved = ctx.resolved_text("open it")
    assert "open Spotify" in resolved

def test_bug4_url_leakage():
    # Test browser_operator style normalization via formatter
    name = _extract_url_name("https://github.com")
    assert name == "GitHub"
    
    from mini_kio.core.runtime_response_formatter import format_close_app
    msg = format_close_app("https://web.telegram.org", True, {"capability_closed": True, "capability_name": "Telegram"})
    assert "https://" not in msg
    assert "Telegram" in msg

def test_bug5_generic_web_naming():
    # Test subdomain handling
    assert _extract_url_name("web.telegram.org") == "Telegram"
    assert _extract_url_name("chrome::open_url::https://web.telegram.org::telegram") == "Telegram"

def test_bug6_empty_command_noise():
    res = handle_command("")
    assert res["success"] is True
    assert res["message"] == ""
    
    res = handle_command("   ")
    assert res["success"] is True
    assert res["message"] == ""

def test_bug7_context_continuity():
    ctx = ConversationContext()
    ctx.append_exchange("Tell me about World Cup", "The World Cup is a football tournament.")
    
    resolved = ctx.resolve_reference("Portugal")
    assert "Portugal" in resolved
    assert "World Cup" in resolved

def test_bug8_achievement_tone():
    normalizer = ToneNormalizer()
    res = normalizer.normalize("That's a huge relief... what was the problem?")
    assert "progress" in res.lower() or "issue" in res.lower()
    assert "?" not in res

if __name__ == "__main__":
    pytest.main([__file__])
