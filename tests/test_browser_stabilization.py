"""
test_browser_stabilization.py — Browser Connector Stabilization Validation

Covers all validation test cases from the patch spec.
"""
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import patch, MagicMock

from mini_kio.core.command_parser import parse_command, is_multi_step
from mini_kio.core.command_router import handle_command
from mini_kio.core.app_operator import _normalize_web_target_to_url
from mini_kio.core import config


# ── Parser Tests (Problems 1, 2, 4) ───────────────────────────────────────

def test_parse_open_single():
    steps = parse_command("open github")
    assert steps == [{"action": "open", "target": "github"}], f"Got {steps}"

def test_parse_open_and():
    steps = parse_command("open github and youtube")
    assert len(steps) == 2, f"Expected 2 steps, got {len(steps)}: {steps}"
    assert steps[0] == {"action": "open", "target": "github"}
    assert steps[1] == {"action": "open", "target": "youtube"}

def test_parse_open_then():
    steps = parse_command("open github then youtube")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "github"}
    assert steps[1] == {"action": "open", "target": "youtube"}

def test_parse_open_comma():
    steps = parse_command("open github, youtube")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "github"}
    assert steps[1] == {"action": "open", "target": "youtube"}

def test_parse_open_plus():
    steps = parse_command("open github + youtube")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "github"}
    assert steps[1] == {"action": "open", "target": "youtube"}

def test_parse_open_multi_comma():
    steps = parse_command("open github, youtube, reddit")
    assert len(steps) == 3, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "github"}
    assert steps[1] == {"action": "open", "target": "youtube"}
    assert steps[2] == {"action": "open", "target": "reddit"}

def test_parse_open_then_multi():
    steps = parse_command("open github then youtube then reddit")
    assert len(steps) == 3, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "github"}
    assert steps[1] == {"action": "open", "target": "youtube"}
    assert steps[2] == {"action": "open", "target": "reddit"}

def test_parse_open_notion_docs_leetcode():
    steps = parse_command("open notion docs leetcode")
    # Without commas, "notion docs leetcode" should be single step (no connector)
    # The space-separated list without connectors is treated as one target
    assert len(steps) == 1, f"Got {steps}"

def test_parse_open_notion_comma_docs_comma_leetcode():
    steps = parse_command("open notion, docs, leetcode")
    assert len(steps) == 3, f"Got {steps}"
    assert steps[0]["target"] == "notion"
    assert steps[1]["target"] == "docs"
    assert steps[2]["target"] == "leetcode"

def test_parse_close_and():
    steps = parse_command("close github and youtube")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "close", "target": "github"}
    assert steps[1] == {"action": "close", "target": "youtube"}

def test_parse_close_then():
    steps = parse_command("close github then youtube then reddit")
    assert len(steps) == 3, f"Got {steps}"

def test_parse_focus():
    steps = parse_command("focus github")
    assert steps == [{"action": "focus", "target": "github"}], f"Got {steps}"

def test_parse_open_chrome_and_github():
    """Problem 4: browser-first phrases"""
    steps = parse_command("open chrome and github")
    assert len(steps) == 2, f"Got {steps}"
    # Step 1 opens chrome browser, Step 2 opens github
    assert steps[0] == {"action": "open", "target": "chrome"}
    assert steps[1] == {"action": "open", "target": "github"}

def test_parse_open_chrome_then_github():
    steps = parse_command("open chrome then github")
    assert len(steps) == 2, f"Got {steps}"

def test_parse_open_browser_and_youtube():
    steps = parse_command("open browser and youtube")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "browser"}
    assert steps[1] == {"action": "open", "target": "youtube"}

def test_parse_open_browser_and_reddit():
    steps = parse_command("open browser and reddit")
    assert len(steps) == 2, f"Got {steps}"

def test_parse_open_claude_and_gemini():
    steps = parse_command("open claude and gemini")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "claude"}
    assert steps[1] == {"action": "open", "target": "gemini"}

def test_parse_open_github_and_chrome():
    steps = parse_command("open github and chrome")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "github"}
    assert steps[1] == {"action": "open", "target": "chrome"}

def test_parse_open_qwen_and_claude():
    """Open qwen.chat.ai and claude"""
    steps = parse_command("open qwen.chat.ai and claude")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "qwen.chat.ai"}
    assert steps[1] == {"action": "open", "target": "claude"}

def test_parse_open_stack_overflow():
    """Problem 3: multi-word => single step"""
    steps = parse_command("open stack overflow")
    assert len(steps) == 1, f"Got {steps}"

def test_parse_open_hacker_news():
    steps = parse_command("open hacker news")
    assert len(steps) == 1, f"Got {steps}"

def test_parse_open_github_then_focus_github():
    """Problem 5: natural chained"""
    steps = parse_command("open github then focus github")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "github"}
    assert steps[1] == {"action": "focus", "target": "github"}

def test_parse_open_reddit_then_focus_reddit():
    steps = parse_command("open reddit then focus reddit")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "reddit"}
    assert steps[1] == {"action": "focus", "target": "reddit"}

def test_parse_open_claude_then_focus_claude():
    steps = parse_command("open claude then focus claude")
    assert len(steps) == 2, f"Got {steps}"
    assert steps[0] == {"action": "open", "target": "claude"}
    assert steps[1] == {"action": "focus", "target": "claude"}

def test_parse_not_multi_step_search():
    """'search for cats and dogs' must NOT be multi-step"""
    steps = parse_command("search for cats and dogs")
    assert len(steps) == 1, f"Got {steps}"
    assert steps[0]["action"] == "search"

def test_parse_not_multi_step_play():
    """'play music and rain' must NOT be multi-step"""
    steps = parse_command("play music and rain")
    assert len(steps) == 1, f"Got {steps}"
    assert steps[0]["action"] in ("youtube_play", "play")


# ── Domain Inference Tests (Problem 3) ────────────────────────────────────

def test_domain_inference_stack_overflow():
    url = _normalize_web_target_to_url("stack overflow")
    assert url == "https://stackoverflow.com", f"Got {url}"

def test_domain_inference_hacker_news():
    # "hackernews" may or may not collapse; if it does, should work
    url = _normalize_web_target_to_url("hacker news")
    assert url == "https://hackernews.com", f"Got {url}"

def test_domain_inference_leetcode():
    url = _normalize_web_target_to_url("leetcode")
    assert url == "https://leetcode.com", f"Got {url}"

def test_domain_inference_notion():
    url = _normalize_web_target_to_url("notion")
    assert url == "https://notion.so", f"Got {url}"

def test_domain_inference_reddit():
    url = _normalize_web_target_to_url("reddit")
    assert url == "https://reddit.com", f"Got {url}"

def test_domain_inference_github():
    url = _normalize_web_target_to_url("github")
    assert url == "https://github.com", f"Got {url}"

def test_domain_inference_perplexity():
    url = _normalize_web_target_to_url("perplexity")
    # Single-label inference defaults to .com, not .ai
    assert url == "https://perplexity.com", f"Got {url}"


# ── Multi-step Detection (is_multi_step) ──────────────────────────────────

def test_is_multi_step_open_and():
    assert is_multi_step("open github and youtube") is True

def test_is_multi_step_open_then():
    assert is_multi_step("open github then youtube") is True

def test_is_multi_step_open_comma():
    assert is_multi_step("open github, youtube") is True

def test_is_multi_step_open_plus():
    assert is_multi_step("open github + youtube") is True

def test_is_multi_step_close_and():
    assert is_multi_step("close github and youtube") is True

def test_is_multi_step_focus():
    assert is_multi_step("open github then focus github") is True

def test_is_multi_step_open_then_then():
    assert is_multi_step("open github then youtube then reddit") is True

def test_is_multi_step_search_for_cats_remains_single():
    assert is_multi_step("search for cats and dogs") is False

def test_is_multi_step_open_multi_comma():
    assert is_multi_step("open github, youtube, reddit") is True


# ── is_multi_step for close commands ──────────────────────────────────────

def test_is_multi_step_close_then():
    assert is_multi_step("close github then youtube") is True

def test_is_multi_step_close_and_web():
    assert is_multi_step("close notion and docs") is True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
