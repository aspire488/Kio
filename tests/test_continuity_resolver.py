"""Tests for the Global Continuity Resolver (Phase 2 — Runtime-Aware)."""

import pytest
from mini_kio.core.continuity_resolver import (
    ContinuityResolver, ContinuityState, ResolvedContinuation,
    DomainContinuationType, ContinuationContext,
)
from mini_kio.core.continuity_context_provider import ContinuityContextProvider


def setup_function():
    ContinuityResolver.reset()


@pytest.fixture(autouse=True)
def fresh_resolver():
    ContinuityResolver.reset()
    yield


# ── Helpers: stub provider methods ─────────────────────────────────────────────

def _stub_provider(overrides: dict):
    """Patch ContinuityContextProvider static methods with test doubles."""
    originals = {}

    def _patch(method, impl):
        originals[method] = getattr(ContinuityContextProvider, method)
        setattr(ContinuityContextProvider, method, staticmethod(impl))

    for method, impl in overrides.items():
        _patch(method, impl)

    def restore():
        for method, orig in originals.items():
            setattr(ContinuityContextProvider, method, staticmethod(orig))

    return restore


# ── Domain Detection ────────────────────────────────────────────────────────


class TestDomainDetection:
    def test_media_domain_from_play(self):
        r = ContinuityResolver.resolve("play messi highlights")
        assert r.domain == DomainContinuationType.MEDIA
        assert not r.is_continuation

    def test_media_domain_from_trailer(self):
        r = ContinuityResolver.resolve("show trailer")
        assert r.domain == DomainContinuationType.MEDIA

    def test_media_domain_from_sports(self):
        r = ContinuityResolver.resolve("fifa world cup standings")
        assert r.domain == DomainContinuationType.MEDIA

    def test_media_domain_from_highlights(self):
        r = ContinuityResolver.resolve("highlights")
        assert r.domain == DomainContinuationType.MEDIA

    def test_media_domain_from_play_it(self):
        r = ContinuityResolver.resolve("play it")
        assert r.domain == DomainContinuationType.MEDIA

    def test_media_domain_from_latest(self):
        r = ContinuityResolver.resolve("latest marvel updates")
        assert r.domain == DomainContinuationType.MEDIA

    def test_browser_domain_from_search_in_chrome(self):
        r = ContinuityResolver.resolve("search python in chrome")
        assert r.domain == DomainContinuationType.BROWSER

    def test_browser_domain_from_open(self):
        r = ContinuityResolver.resolve("open chrome")
        assert r.domain == DomainContinuationType.BROWSER

    def test_browser_domain_from_next_result(self):
        r = ContinuityResolver.resolve("open next result")
        assert r.domain == DomainContinuationType.BROWSER

    def test_browser_domain_from_summarize_page(self):
        r = ContinuityResolver.resolve("summarize this page")
        assert r.domain == DomainContinuationType.BROWSER

    def test_browser_domain_from_list_tabs(self):
        r = ContinuityResolver.resolve("list tabs")
        assert r.domain == DomainContinuationType.BROWSER

    def test_research_domain_from_research(self):
        r = ContinuityResolver.resolve("research GPT-5")
        assert r.domain == DomainContinuationType.RESEARCH

    def test_research_domain_from_summarize(self):
        r = ContinuityResolver.resolve("summarize that")
        assert r.domain == DomainContinuationType.RESEARCH

    def test_research_domain_from_sources(self):
        r = ContinuityResolver.resolve("give sources")
        assert r.domain == DomainContinuationType.RESEARCH

    def test_research_domain_from_compare(self):
        r = ContinuityResolver.resolve("compare it with claude")
        assert r.domain == DomainContinuationType.RESEARCH

    def test_file_domain_from_create_file(self):
        r = ContinuityResolver.resolve("create python file")
        assert r.domain == DomainContinuationType.FILE

    def test_file_domain_from_open_folder(self):
        r = ContinuityResolver.resolve("open folder")
        assert r.domain == DomainContinuationType.FILE

    def test_file_domain_from_fix_bug(self):
        r = ContinuityResolver.resolve("fix bug")
        assert r.domain == DomainContinuationType.FILE

    def test_task_domain_from_todo(self):
        r = ContinuityResolver.resolve("make a todo list")
        assert r.domain == DomainContinuationType.TASK

    def test_task_domain_from_add_task(self):
        r = ContinuityResolver.resolve("add another task")
        assert r.domain == DomainContinuationType.TASK

    def test_system_domain_from_shutdown(self):
        r = ContinuityResolver.resolve("shutdown")
        assert r.domain == DomainContinuationType.SYSTEM

    def test_system_domain_from_brightness(self):
        r = ContinuityResolver.resolve("increase brightness")
        assert r.domain == DomainContinuationType.SYSTEM

    def test_system_domain_from_again(self):
        r = ContinuityResolver.resolve("do that again")
        assert r.domain == DomainContinuationType.SYSTEM

    def test_system_domain_from_again_short(self):
        r = ContinuityResolver.resolve("again")
        assert r.domain == DomainContinuationType.SYSTEM

    def test_conversation_domain_from_tell_me(self):
        r = ContinuityResolver.resolve("tell me about transformers")
        assert r.domain == DomainContinuationType.CONVERSATION

    def test_conversation_domain_from_explain(self):
        r = ContinuityResolver.resolve("explain simpler")
        assert r.domain == DomainContinuationType.CONVERSATION

    def test_conversation_domain_from_hello(self):
        r = ContinuityResolver.resolve("hello")
        assert r.domain == DomainContinuationType.CONVERSATION

    def test_unknown_domain_for_gibberish(self):
        r = ContinuityResolver.resolve("asdfghjkl")
        assert r.domain == DomainContinuationType.UNKNOWN
        assert not r.is_continuation


# ── Continuity Resolution ────────────────────────────────────────────────────


class TestContinuityResolution:
    def test_continuation_with_active_media_domain(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_subject("fifa world cup")
        r = ContinuityResolver.resolve("continue")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.MEDIA

    def test_continuation_with_active_browser_domain(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
        ContinuityResolver.set_state_subject("chrome")
        r = ContinuityResolver.resolve("continue")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.BROWSER

    def test_affirmative_with_active_domain(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_subject("marvel trailer")
        r = ContinuityResolver.resolve("yes")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.MEDIA

    def test_affirmative_with_active_browser_domain(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
        r = ContinuityResolver.resolve("ok")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.BROWSER

    def test_next_marker_media(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_subject("marvel trailer")
        r = ContinuityResolver.resolve("more")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.MEDIA

    def test_next_marker_research(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.RESEARCH)
        r = ContinuityResolver.resolve("next")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.RESEARCH

    def test_pronoun_reference_resolves_subject(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_subject("marvel trailer")
        r = ContinuityResolver.resolve("play it")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.MEDIA
        assert "marvel trailer" in r.resolved_text.lower()

    def test_pronoun_resolution_no_subject_fresh(self):
        r = ContinuityResolver.resolve("play it")
        assert r.domain == DomainContinuationType.MEDIA
        assert r.is_continuation is False

    def test_pronoun_this_with_active_browser(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
        ContinuityResolver.set_state_subject("claude code page")
        r = ContinuityResolver.resolve("summarize this")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.RESEARCH  # keyword-detected, not overridden
        assert "claude code page" in r.resolved_text.lower()

    def test_pronoun_that_with_active_research(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.RESEARCH)
        ContinuityResolver.set_state_subject("GPT-5 paper")
        r = ContinuityResolver.resolve("summarize that")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.RESEARCH
        assert "GPT-5 paper" in r.resolved_text.lower() or "gpt-5" in r.resolved_text.lower()


# ── State Updates ────────────────────────────────────────────────────────────


class TestStateUpdates:
    def test_update_state_sets_active_domain(self):
        assert ContinuityResolver.get_state().active_domain is None
        ContinuityResolver.update_state(
            {"success": True, "target": "chrome", "action": "open_app"},
            "open chrome",
            DomainContinuationType.BROWSER,
        )
        state = ContinuityResolver.get_state()
        assert state.active_domain == DomainContinuationType.BROWSER
        assert state.active_subject == "chrome"
        assert state.last_success is True

    def test_update_state_subject_from_result(self):
        ContinuityResolver.update_state(
            {"success": True, "target": "fifa world cup highlights", "action": "play"},
            "play fifa world cup highlights",
            DomainContinuationType.MEDIA,
        )
        state = ContinuityResolver.get_state()
        assert state.active_subject == "fifa world cup highlights"

    def test_state_reset(self):
        ContinuityResolver.update_state(
            {"success": True}, "test", DomainContinuationType.MEDIA,
        )
        assert ContinuityResolver.get_state().active_domain == DomainContinuationType.MEDIA
        ContinuityResolver.reset()
        assert ContinuityResolver.get_state().active_domain is None


# ── End-to-End Workflow Simulations ─────────────────────────────────────────


class TestMediaWorkflow:
    def test_media_continuity_followup_shows_highlights(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_subject("fifa world cup")
        r = ContinuityResolver.resolve("show highlights")
        assert r.is_continuation or r.domain == DomainContinuationType.MEDIA

    def test_media_continuity_affirmative_play_it(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_subject("gta 6 gameplay")
        r = ContinuityResolver.resolve("play it")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.MEDIA


class TestBrowserWorkflow:
    def test_browser_continuity_search_chrome(self):
        r = ContinuityResolver.resolve("search for Claude Code")
        assert r.domain in (DomainContinuationType.BROWSER, DomainContinuationType.RESEARCH)

    def test_browser_next_result(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
        ContinuityResolver.set_state_subject("claude code")
        r = ContinuityResolver.resolve("open next result")
        assert r.is_continuation or r.domain == DomainContinuationType.BROWSER

    def test_browser_summarize_page(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
        ContinuityResolver.set_state_subject("claude code page")
        r = ContinuityResolver.resolve("summarize this page")
        assert r.domain == DomainContinuationType.BROWSER


class TestResearchWorkflow:
    def test_research_then_compare(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.RESEARCH)
        ContinuityResolver.set_state_subject("GPT-5")
        r = ContinuityResolver.resolve("compare it with claude")
        assert r.is_continuation or r.domain == DomainContinuationType.RESEARCH

    def test_research_give_sources(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.RESEARCH)
        ContinuityResolver.set_state_subject("GPT-5")
        r = ContinuityResolver.resolve("give sources")
        assert r.is_continuation or r.domain == DomainContinuationType.RESEARCH


class TestConversationWorkflow:
    def test_conversation_continuity(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.CONVERSATION)
        ContinuityResolver.set_state_subject("transformers")
        r = ContinuityResolver.resolve("continue")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.CONVERSATION

    def test_conversation_explain_simpler(self):
        r = ContinuityResolver.resolve("explain simpler")
        assert r.domain == DomainContinuationType.CONVERSATION


class TestFileWorkflow:
    def test_file_create_then_fix(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.FILE)
        ContinuityResolver.set_state_subject("script.py")
        r = ContinuityResolver.resolve("fix bug")
        assert r.is_continuation or r.domain == DomainContinuationType.FILE

    def test_file_create_then_run(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.FILE)
        ContinuityResolver.set_state_subject("script.py")
        r = ContinuityResolver.resolve("continue")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.FILE


class TestTaskWorkflow:
    def test_task_add_then_remove(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.TASK)
        r = ContinuityResolver.resolve("add another task")
        assert r.domain == DomainContinuationType.TASK

    def test_task_next(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.TASK)
        r = ContinuityResolver.resolve("next")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.TASK


class TestSystemWorkflow:
    def test_system_again(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.SYSTEM)
        ContinuityResolver.set_state_subject("brightness")
        r = ContinuityResolver.resolve("do that again")
        assert r.is_continuation or r.domain == DomainContinuationType.SYSTEM
        assert "brightness" in r.resolved_text.lower() if r.is_continuation else True

    def test_system_brightness_increase(self):
        r = ContinuityResolver.resolve("increase brightness")
        assert r.domain == DomainContinuationType.SYSTEM


# ── Edge Cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_command(self):
        r = ContinuityResolver.resolve("")
        assert r.domain == DomainContinuationType.UNKNOWN
        assert not r.is_continuation

    def test_whitespace_command(self):
        r = ContinuityResolver.resolve("   ")
        assert r.domain == DomainContinuationType.UNKNOWN

    def test_no_continuity_without_state(self):
        r = ContinuityResolver.resolve("continue")
        assert not r.is_continuation

    def test_affirmative_without_state_fresh(self):
        r = ContinuityResolver.resolve("yes")
        assert not r.is_continuation

    def test_new_explicit_command_overrides_continuity(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        r = ContinuityResolver.resolve("list tabs")
        assert r.domain == DomainContinuationType.BROWSER
        assert not r.is_continuation

    def test_pronoun_without_subject_no_continuity(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
        r = ContinuityResolver.resolve("summarize that")
        assert r.is_continuation is False


# ── Phase 2: Runtime-Aware Continuity (T8 Priority) ──────────────────────────


class TestRuntimeReferenceResolution:
    """T8-1: Explicit runtime references (again, do it again) with runtime state."""

    def test_again_with_runtime_state_resolves(self):
        restore = _stub_provider({
            "get_last_successful_interaction": lambda action_type=None: {
                "success": True, "action": "play", "target": "messi highlights",
            },
        })
        try:
            ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
            r = ContinuityResolver.resolve("again")
            assert r.is_continuation
            assert "play" in r.resolved_text.lower()
            assert "messi" in r.resolved_text.lower()
        finally:
            restore()

    def test_do_it_again_with_runtime_state(self):
        restore = _stub_provider({
            "get_last_successful_interaction": lambda action_type=None: {
                "success": True, "action": "search", "target": "python tutorials",
            },
        })
        try:
            ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
            r = ContinuityResolver.resolve("do it again")
            assert r.is_continuation
            assert "search" in r.resolved_text.lower()
        finally:
            restore()

    def test_again_without_runtime_state_falls_through(self):
        restore = _stub_provider({
            "get_last_successful_interaction": lambda action_type=None: None,
        })
        try:
            r = ContinuityResolver.resolve("again")
            assert r.domain == DomainContinuationType.SYSTEM
            assert not r.is_continuation
        finally:
            restore()


class TestPendingActionResolution:
    """T8-2: Pending actions from MediaContext resolve before keyword matching."""

    def test_play_it_with_pending_media(self):
        restore = _stub_provider({
            "get_pending_media_action": lambda: {
                "action": "play_media", "query": "fifa world cup highlights", "domain": None,
            },
        })
        try:
            r = ContinuityResolver.resolve("play it")
            assert r.is_continuation
            assert r.domain == DomainContinuationType.MEDIA
            assert "fifa world cup highlights" in r.resolved_text
        finally:
            restore()

    def test_yes_with_pending_media(self):
        restore = _stub_provider({
            "get_pending_media_action": lambda: {
                "action": "play_media", "query": "gta 6 trailer", "domain": None,
            },
        })
        try:
            r = ContinuityResolver.resolve("yes")
            assert r.is_continuation
            assert r.domain == DomainContinuationType.MEDIA
            assert "play" in r.resolved_text.lower()
            assert "gta 6" in r.resolved_text.lower()
        finally:
            restore()

    def test_show_it_with_pending_media(self):
        restore = _stub_provider({
            "get_pending_media_action": lambda: {
                "action": "play_media", "query": "marvel trailer", "domain": None,
            },
        })
        try:
            r = ContinuityResolver.resolve("show it")
            assert r.is_continuation
            assert r.domain == DomainContinuationType.MEDIA
            assert "marvel trailer" in r.resolved_text
        finally:
            restore()

    def test_no_pending_action_falls_through_to_keywords(self):
        restore = _stub_provider({
            "get_pending_media_action": lambda: None,
        })
        try:
            r = ContinuityResolver.resolve("play it")
            assert r.domain == DomainContinuationType.MEDIA
            assert not r.is_continuation
        finally:
            restore()


class TestEnhancedPronounResolution:
    """T8-3/T8-4: Active domain + subject with runtime MediaContext enrichment."""

    def test_pronoun_with_active_browser_subject(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
        ContinuityResolver.set_state_subject("claude code docs")
        r = ContinuityResolver.resolve("close it")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.BROWSER
        assert "claude code docs" in r.resolved_text

    def test_pronoun_with_active_research_subject(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.RESEARCH)
        ContinuityResolver.set_state_subject("GPT-5 paper")
        r = ContinuityResolver.resolve("summarize it")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.RESEARCH
        assert "GPT-5 paper" in r.resolved_text

    def test_pronoun_with_active_conversation_subject(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.CONVERSATION)
        ContinuityResolver.set_state_subject("quantum computing")
        r = ContinuityResolver.resolve("tell me more about it")
        assert r.is_continuation
        assert "quantum computing" in r.resolved_text


class TestDomainContinuityPriority:
    """T8: Runtime state beats keyword inference in priority chain."""

    def test_runtime_ref_beats_system_keyword(self):
        restore = _stub_provider({
            "get_last_successful_interaction": lambda action_type=None: {
                "success": True, "action": "play", "target": "fifa highlights",
            },
            "get_pending_media_action": lambda: None,
        })
        try:
            ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
            r = ContinuityResolver.resolve("again")
            assert r.is_continuation
            assert "play" in r.resolved_text.lower()
        finally:
            restore()

    def test_pending_action_beats_keyword_detection(self):
        """Pending media action beats 'summarize' keyword mapping to RESEARCH."""
        restore = _stub_provider({
            "get_pending_media_action": lambda: {
                "action": "play_media", "query": "fifa world cup highlights", "domain": None,
            },
            "get_last_successful_interaction": lambda action_type=None: None,
        })
        try:
            r = ContinuityResolver.resolve("play it")
            assert r.is_continuation
            assert r.domain == DomainContinuationType.MEDIA
        finally:
            restore()

    def test_active_domain_beats_keyword_mismatch(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.FILE)
        ContinuityResolver.set_state_subject("script.py")
        r = ContinuityResolver.resolve("do that again")
        assert r.is_continuation or r.domain == DomainContinuationType.FILE

    def test_new_explicit_command_still_overrides(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        r = ContinuityResolver.resolve("list tabs")
        assert r.domain == DomainContinuationType.BROWSER
        assert not r.is_continuation


class TestContinuityMarkersAllDomains:
    """Full coverage: continuation/affirmative + next markers on all 7 domains."""

    @pytest.mark.parametrize("domain", [
        DomainContinuationType.MEDIA,
        DomainContinuationType.BROWSER,
        DomainContinuationType.RESEARCH,
        DomainContinuationType.CONVERSATION,
        DomainContinuationType.FILE,
        DomainContinuationType.TASK,
        DomainContinuationType.SYSTEM,
    ])
    def test_continue_marker_all_domains(self, domain):
        ContinuityResolver.set_state_domain(domain)
        ContinuityResolver.set_state_subject("test subject")
        r = ContinuityResolver.resolve("continue")
        assert r.is_continuation
        assert r.domain == domain

    @pytest.mark.parametrize("domain", [
        DomainContinuationType.MEDIA,
        DomainContinuationType.BROWSER,
        DomainContinuationType.RESEARCH,
        DomainContinuationType.CONVERSATION,
        DomainContinuationType.FILE,
        DomainContinuationType.TASK,
        DomainContinuationType.SYSTEM,
    ])
    def test_affirmative_marker_all_domains(self, domain):
        ContinuityResolver.set_state_domain(domain)
        r = ContinuityResolver.resolve("yes")
        assert r.is_continuation
        assert r.domain == domain

    @pytest.mark.parametrize("domain", [
        DomainContinuationType.MEDIA,
        DomainContinuationType.BROWSER,
        DomainContinuationType.RESEARCH,
        DomainContinuationType.CONVERSATION,
        DomainContinuationType.FILE,
        DomainContinuationType.TASK,
        DomainContinuationType.SYSTEM,
    ])
    def test_next_marker_all_domains(self, domain):
        ContinuityResolver.set_state_domain(domain)
        r = ContinuityResolver.resolve("more")
        assert r.is_continuation
        assert r.domain == domain

    def test_another_one_with_media_state(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_subject("rock music")
        r = ContinuityResolver.resolve("another one")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.MEDIA

    def test_next_one_with_task_state(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.TASK)
        r = ContinuityResolver.resolve("next one")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.TASK


class TestCommunicationScenarios:
    """Realistic end-to-end scenarios from the communication plan."""

    def test_play_it_no_context_resolved_to_media(self):
        restore = _stub_provider({
            "get_pending_media_action": lambda: None,
            "get_last_successful_interaction": lambda action_type=None: None,
        })
        try:
            r = ContinuityResolver.resolve("play it")
            assert r.domain == DomainContinuationType.MEDIA
            assert not r.is_continuation
        finally:
            restore()

    def test_play_it_with_pending_context(self):
        restore = _stub_provider({
            "get_pending_media_action": lambda: {
                "action": "play_media", "query": "fifa world cup highlights", "domain": None,
            },
            "get_last_successful_interaction": lambda action_type=None: None,
        })
        try:
            r = ContinuityResolver.resolve("play it")
            assert r.is_continuation
            assert "fifa world cup highlights" in r.resolved_text
        finally:
            restore()

    def test_show_it_with_pending_context(self):
        restore = _stub_provider({
            "get_pending_media_action": lambda: {
                "action": "play_media", "query": "gta 6 gameplay", "domain": None,
            },
            "get_last_successful_interaction": lambda action_type=None: None,
        })
        try:
            r = ContinuityResolver.resolve("show it")
            assert r.is_continuation
            assert "gta 6 gameplay" in r.resolved_text
        finally:
            restore()

    def test_close_it_with_browser_subject(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
        ContinuityResolver.set_state_subject("claude code tab")
        r = ContinuityResolver.resolve("close it")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.BROWSER
        assert "claude code tab" in r.resolved_text

    def test_summarize_it_with_research_subject(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.RESEARCH)
        ContinuityResolver.set_state_subject("GPT-5 architecture")
        r = ContinuityResolver.resolve("summarize it")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.RESEARCH
        assert "GPT-5 architecture" in r.resolved_text

    def test_tell_me_more_with_conversation_state(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.CONVERSATION)
        ContinuityResolver.set_state_subject("transformers")
        r = ContinuityResolver.resolve("tell me more")
        assert r.domain == DomainContinuationType.CONVERSATION
        assert not r.is_continuation  # "tell me" is a conversation keyword, not a marker

    def test_email_it_with_conversation_subject(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.CONVERSATION)
        ContinuityResolver.set_state_subject("meeting notes")
        r = ContinuityResolver.resolve("email it")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.CONVERSATION
        assert "meeting notes" in r.resolved_text


class TestBedrockScenarios:
    """Test scenarios that must not regress from Phase 1."""

    def test_media_continuity_preserved(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_subject("fifa world cup")
        r = ContinuityResolver.resolve("continue")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.MEDIA

    def test_browser_continuity_preserved(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
        ContinuityResolver.set_state_subject("chrome")
        r = ContinuityResolver.resolve("ok")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.BROWSER

    def test_research_continuity_preserved(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.RESEARCH)
        ContinuityResolver.set_state_subject("GPT-5")
        r = ContinuityResolver.resolve("next")
        assert r.is_continuation
        assert r.domain == DomainContinuationType.RESEARCH

    def test_empty_command_unchanged(self):
        r = ContinuityResolver.resolve("")
        assert r.domain == DomainContinuationType.UNKNOWN
        assert not r.is_continuation

    def test_explicit_media_command_with_active_state(self):
        ContinuityResolver.set_state_domain(DomainContinuationType.BROWSER)
        ContinuityResolver.set_state_subject("chrome")
        r = ContinuityResolver.resolve("play fifa")
        assert r.domain == DomainContinuationType.MEDIA
        assert not r.is_continuation
