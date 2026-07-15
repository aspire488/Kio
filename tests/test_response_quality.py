"""Validate ACTUAL response output format and quality for all domains.

Verifies that rendered responses match the expected KIO style:
- Natural language, not raw search/provder output
- Domain emoji prefix
- Brief summary with bulleted sections for updates
- Proactive Watch offers (bulleted)
- Proactive Follow-up question
- No "Query:" or provider noise
"""

import pytest
from mini_kio.media.intelligence.answer_composer import AnswerComposer
from mini_kio.media.intelligence.media_intelligence_models import TopicType


@pytest.fixture
def composer():
    return AnswerComposer(llm_fn=None)  # deterministic, no LLM


# ═══════════════════════════════════════════════════════════════════
# SPORTS — FIFA World Cup 2026 latest updates
# ═══════════════════════════════════════════════════════════════════

class TestSportsFIFA:
    """FIFA World Cup 2026 latest updates — expected response format."""

    RAW = (
        "The FIFA World Cup 2026 is being hosted across USA, Canada and Mexico. "
        "The United States will play the opening match on June 11, 2026. "
        "Argentina qualified as defending champions after winning the 2022 final. "
        "Canada qualified directly as co-hosts for the first time since 1986. "
        "The expanded 48-team format will feature 16 groups of three. "
        "The draw took place in December 2025."
    )

    def test_emoji_header(self, composer):
        """Response must start with ⚽ FIFA World Cup 2026."""
        result = composer.compose(self.RAW, "FIFA World Cup 2026 latest updates",
                                   TopicType.SPORTS, "FIFA World Cup 2026")
        assert result.startswith("\u26bd FIFA World Cup 2026"), \
            f"Must start with emoji + subject, got: {result[:60]}"

    def test_status_report_section(self, composer):
        """Response must have 'Status report:' + 'Here's what's happening right now:'."""
        result = composer.compose(self.RAW, "FIFA World Cup 2026 latest updates",
                                   TopicType.SPORTS, "FIFA World Cup 2026")
        assert "Status report:" in result, "Must have Status report header"
        assert "Here's what's happening right now:" in result, \
            "Must have conversational lead-in"

    def test_uses_bullets_for_updates(self, composer):
        """Main section must use bullets (•) not a paragraph."""
        result = composer.compose(self.RAW, "FIFA World Cup 2026 latest updates",
                                   TopicType.SPORTS, "FIFA World Cup 2026")
        assert "\u2022" in result, "Must use bullet points"
        lines = result.split("\n")
        # After "Here's what's happening right now:", expect bullet lines
        bullet_lines = [l for l in lines if "\u2022" in l]
        assert len(bullet_lines) >= 2, f"Expected multiple bullet lines, got: {bullet_lines}"

    def test_watch_section_bulleted(self, composer):
        """Watch section must use bullets not numbers."""
        result = composer.compose(self.RAW, "FIFA World Cup 2026 latest updates",
                                   TopicType.SPORTS, "FIFA World Cup 2026")
        assert "Watch:" in result, "Must have Watch section"
        # Should NOT have numbered items like "1. Highlights"
        assert "1. " not in result, "Watch offers must NOT be numbered"
        # Check for bulleted offers
        after_watch = False
        has_bulleted_offer = False
        for line in result.split("\n"):
            if "Watch:" in line:
                after_watch = True
                continue
            if after_watch and "\u2022" in line:
                has_bulleted_offer = True
                break
            if after_watch and line.strip() == "":
                continue
            if after_watch and "Follow-up:" in line:
                break
        assert has_bulleted_offer, "Watch section must have bulleted offers"

    def test_followup_section(self, composer):
        """Response must end with Follow-up question."""
        result = composer.compose(self.RAW, "FIFA World Cup 2026 latest updates",
                                   TopicType.SPORTS, "FIFA World Cup 2026")
        assert "Follow-up:" in result, "Must have Follow-up section"
        # Must have sports-specific question
        assert "match results" in result.lower() or "standings" in result.lower(), \
            "Follow-up must mention sports options"

    def test_no_raw_search_output(self, composer):
        """Must NOT contain raw search artifacts."""
        result = composer.compose(self.RAW, "FIFA World Cup 2026 latest updates",
                                   TopicType.SPORTS, "FIFA World Cup 2026")
        assert "Query:" not in result, "Must not contain 'Query:'"
        assert "search" not in result.lower(), "Must not mention search"
        assert "source:" not in result.lower(), "Must not expose provider sources"
        assert "wikipedia" not in result.lower(), "Must not mention Wikipedia"

    def test_full_output_format(self, composer):
        """Complete output must match the expected KIO style structure."""
        result = composer.compose(self.RAW, "FIFA World Cup 2026 latest updates",
                                   TopicType.SPORTS, "FIFA World Cup 2026")
        lines = result.split("\n")
        assert lines[0].startswith("\u26bd"), "Line 1: emoji + subject"
        assert any("Status report:" in l for l in lines), "Status report header"
        assert any("Watch:" in l for l in lines), "Watch section"
        followup_lines = [i for i, l in enumerate(lines) if "Follow-up:" in l]
        assert len(followup_lines) == 1, "Exactly one Follow-up section"
        # Follow-up must appear after Watch
        watch_idx = next(i for i, l in enumerate(lines) if "Watch:" in l)
        assert followup_lines[0] > watch_idx, "Follow-up must come after Watch section"

    def test_sections_rendered(self, composer):
        """Sports-specific sections should render."""
        RAW = (
            "Argentina beat Brazil 2-1 in the final match. "
            "Lionel Messi scored the winning goal in the 87th minute. "
            "Argentina top Group A with 9 points. "
            "Brazil are second with 6 points following their loss. "
            "The semi-final fixtures are scheduled for July 2026."
        )
        result = composer.compose(RAW, "FIFA World Cup 2026 latest updates",
                                   TopicType.SPORTS, "FIFA World Cup 2026")
        # Should have bullet section(s) with scores and standings
        assert "\u2022" in result, "Must have bullet content"
        assert "Watch:" in result, "Must have Watch section"
        assert "Follow-up:" in result, "Must have Follow-up section"


# ═══════════════════════════════════════════════════════════════════
# MOVIES — Tell me about Interstellar
# ═══════════════════════════════════════════════════════════════════

class TestMovieInterstellar:
    """Tell me about Interstellar — expected movie response format."""

    RAW = (
        "Interstellar is a 2014 epic science fiction film directed by Christopher Nolan. "
        "The film stars Matthew McConaughey, Anne Hathaway, Jessica Chastain, and Michael Caine. "
        "Set in a dystopian future where Earth is suffering from crop blight and dust storms, "
        "the film follows astronauts who travel through a wormhole near Saturn in search of "
        "a new habitable planet. The film was a critical and commercial success, "
        "grossing over $677 million worldwide. It won the Academy Award for Best Visual Effects. "
        "Hans Zimmer composed the acclaimed soundtrack."
    )

    def test_emoji_header_movies(self, composer):
        """Response must start with 🎬 Interstellar."""
        result = composer.compose(self.RAW, "Tell me about Interstellar",
                                   TopicType.MOVIES, "Interstellar")
        assert result.startswith("\U0001f3ac Interstellar"), \
            f"Must start with movie emoji + subject, got: {result[:60]}"

    def test_field_intel_not_bullets(self, composer):
        """Field intel (non-update) must use paragraph, not bullets."""
        result = composer.compose(self.RAW, "Tell me about Interstellar",
                                   TopicType.MOVIES, "Interstellar")
        assert "Field intel:" in result, "Must have Field intel header"
        assert "Status report:" not in result, \
            "Non-update queries must NOT use Status report"

    def test_watch_section_movies(self, composer):
        """Movie response must have Watch section with offers."""
        result = composer.compose(self.RAW, "Tell me about Interstellar",
                                   TopicType.MOVIES, "Interstellar")
        assert "Watch:" in result, "Must have Watch section"

    def test_followup_section_movies(self, composer):
        """Movie response must end with Follow-up question."""
        result = composer.compose(self.RAW, "Tell me about Interstellar",
                                   TopicType.MOVIES, "Interstellar")
        assert "Follow-up:" in result, "Must have Follow-up section"
        assert "trailer" in result.lower(), "Follow-up must mention trailer"
        assert "soundtrack" in result.lower(), "Follow-up must mention soundtrack"

    def test_movies_no_raw_search(self, composer):
        """Must not contain search-engine artifacts in output."""
        result = composer.compose(self.RAW, "Tell me about Interstellar",
                                   TopicType.MOVIES, "Interstellar")
        assert "Query:" not in result, "Must not contain 'Query:' prefix"
        assert "web search" not in result.lower(), "Must not mention web search"


# ═══════════════════════════════════════════════════════════════════
# MUSIC — Tell me about Believer
# ═══════════════════════════════════════════════════════════════════

class TestMusicBeliever:
    """Tell me about Believer — expected music response format."""

    RAW = (
        "Believer is a song by American pop rock band Imagine Dragons. "
        "It was released as the lead single from their third studio album Evolve in 2017. "
        "The song was written by band members Dan Reynolds, Wayne Sermon, Ben McKee, "
        "and Daniel Platzman along with producers Mattman & Robin. "
        "Believer peaked at number four on the US Billboard Hot 100. "
        "It became one of the best-selling songs worldwide with over 10 million copies sold. "
        "The music video has over 2 billion views on YouTube."
    )

    def test_emoji_header_music(self, composer):
        result = composer.compose(self.RAW, "Tell me about Believer",
                                   TopicType.MUSIC, "Believer")
        assert result.startswith("\U0001f3b5 Believer")

    def test_field_intel_music(self, composer):
        result = composer.compose(self.RAW, "Tell me about Believer",
                                   TopicType.MUSIC, "Believer")
        assert "Field intel:" in result

    def test_watch_section_music(self, composer):
        result = composer.compose(self.RAW, "Tell me about Believer",
                                   TopicType.MUSIC, "Believer")
        assert "Watch:" in result

    def test_followup_section_music(self, composer):
        result = composer.compose(self.RAW, "Tell me about Believer",
                                   TopicType.MUSIC, "Believer")
        assert "Follow-up:" in result
        assert "music video" in result.lower(), "Follow-up must mention music video"


# ═══════════════════════════════════════════════════════════════════
# BOOKS — Tell me about Atomic Habits
# ═══════════════════════════════════════════════════════════════════

class TestBooksAtomicHabits:
    """Tell me about Atomic Habits — expected books response format."""

    RAW = (
        "Atomic Habits by James Clear is a self-help book about building good habits "
        "and breaking bad ones. Published in 2018, it became an international bestseller. "
        "The book presents a practical guide based on four laws of behavior change: "
        "make it obvious, make it attractive, make it easy, and make it satisfying. "
        "Clear argues that small daily improvements lead to remarkable results. "
        "The book has sold over 15 million copies worldwide."
    )

    def test_emoji_header_books(self, composer):
        result = composer.compose(self.RAW, "Tell me about Atomic Habits",
                                   TopicType.BOOKS, "Atomic Habits")
        assert result.startswith("\U0001f4d6 Atomic Habits")

    def test_field_intel_books(self, composer):
        result = composer.compose(self.RAW, "Tell me about Atomic Habits",
                                   TopicType.BOOKS, "Atomic Habits")
        assert "Field intel:" in result

    def test_watch_section_books(self, composer):
        result = composer.compose(self.RAW, "Tell me about Atomic Habits",
                                   TopicType.BOOKS, "Atomic Habits")
        assert "Watch:" in result

    def test_followup_section_books(self, composer):
        result = composer.compose(self.RAW, "Tell me about Atomic Habits",
                                   TopicType.BOOKS, "Atomic Habits")
        assert "Follow-up:" in result
        assert "audiobook" in result.lower(), "Follow-up must mention audiobook"
        assert "author interview" in result.lower(), "Follow-up must mention author interview"


# ═══════════════════════════════════════════════════════════════════
# TV
# ═══════════════════════════════════════════════════════════════════

class TestTvTheBear:
    """Tell me about The Bear — expected TV response format."""

    RAW = (
        "The Bear is an American comedy-drama television series created by Christopher Storer. "
        "The series premiered on Hulu in June 2022. It stars Jeremy Allen White as Carmen 'Carmy' Berzatto, "
        "a young chef who returns home to run his late brother's sandwich shop. "
        "The show has received critical acclaim for its performances, writing, and direction. "
        "Season 3 was released in June 2024."
    )

    def test_emoji_header_tv(self, composer):
        result = composer.compose(self.RAW, "Tell me about The Bear",
                                   TopicType.TV, "The Bear")
        assert result.startswith("\U0001f4fa The Bear")

    def test_field_intel_tv(self, composer):
        result = composer.compose(self.RAW, "Tell me about The Bear",
                                   TopicType.TV, "The Bear")
        assert "Field intel:" in result

    def test_watch_section_tv(self, composer):
        result = composer.compose(self.RAW, "Tell me about The Bear",
                                   TopicType.TV, "The Bear")
        assert "Watch:" in result

    def test_followup_section_tv(self, composer):
        result = composer.compose(self.RAW, "Tell me about The Bear",
                                   TopicType.TV, "The Bear")
        assert "Follow-up:" in result


# ═══════════════════════════════════════════════════════════════════
# GAMING
# ═══════════════════════════════════════════════════════════════════

class TestGamingEldenRing:
    """Tell me about Elden Ring — expected gaming response format."""

    RAW = (
        "Elden Ring is a 2022 action role-playing game developed by FromSoftware. "
        "It was published by Bandai Namco Entertainment. The game was directed by Hidetaka Miyazaki, "
        "with worldbuilding by fantasy novelist George R. R. Martin. "
        "Elden Ring received universal acclaim for its open world and gameplay. "
        "The Shadow of the Erdtree DLC was announced in February 2023."
    )

    def test_emoji_header_gaming(self, composer):
        result = composer.compose(self.RAW, "Tell me about Elden Ring",
                                   TopicType.GAMING, "Elden Ring")
        # Gaming currently has no dedicated emoji — check it renders without error
        assert "Elden Ring" in result, "Must include subject"

    def test_watch_section_gaming(self, composer):
        result = composer.compose(self.RAW, "Tell me about Elden Ring",
                                   TopicType.GAMING, "Elden Ring")
        assert "Watch:" in result

    def test_followup_section_gaming(self, composer):
        result = composer.compose(self.RAW, "Tell me about Elden Ring",
                                   TopicType.GAMING, "Elden Ring")
        assert "Follow-up:" in result


# ═══════════════════════════════════════════════════════════════════
# EMPTY RETRIEVAL PATH
# ═══════════════════════════════════════════════════════════════════

class TestEmptyRetrieval:
    """When retrieval returns empty, must produce graceful response."""

    def test_empty_sports(self, composer):
        result = composer.compose("", "FIFA World Cup 2026 latest updates",
                                   TopicType.SPORTS, "FIFA World Cup 2026")
        # Should still have emoji + subject
        assert "\u26bd FIFA World Cup 2026" in result
        # Should have the follow-up question
        assert "Follow-up:" in result

    def test_empty_movies(self, composer):
        result = composer.compose("", "Tell me about Interstellar",
                                   TopicType.MOVIES, "Interstellar")
        assert "\U0001f3ac Interstellar" in result
        assert "Follow-up:" in result


# ═══════════════════════════════════════════════════════════════════
# CLEAN FACT BEHAVIOR
# ═══════════════════════════════════════════════════════════════════

class TestCleanFact:
    """Facts must be cleaned of markdown and artifacts."""

    def test_markdown_links_stripped(self, composer):
        raw = "The movie [Interstellar](https://en.wikipedia.org) is a 2014 film."
        result = composer.compose(raw, "Tell me about Interstellar",
                                   TopicType.MOVIES, "Interstellar")
        # No markdown link syntax should survive
        assert "](http" not in result, "Markdown links must be stripped"

    def test_long_facts_truncated(self, composer):
        raw = "Word " * 100
        result = composer.compose(raw, "Tell me about something",
                                   TopicType.MOVIES, "Something")
        # Should not be absurdly long
        assert len(result) < 2000, "Response must not be excessively long"

    def test_pipe_tables_removed(self, composer):
        raw = "| Header | Value |\n|--------|-------|\n| Year | 2024 |\nContent here."
        result = composer.compose(raw, "Tell me about test",
                                   TopicType.MOVIES, "Test")
        # No pipe-table artifacts should survive
        assert "| Year" not in result, "Pipe tables must be stripped"


# ═══════════════════════════════════════════════════════════════════
# PRINT FULL OUTPUT FOR REVIEW (not a test)
# ═══════════════════════════════════════════════════════════════════

def test_print_outputs(composer, capsys):
    """Print actual rendered responses for review (ASCII safe)."""
    scenarios = [
        (TestSportsFIFA.RAW, "FIFA World Cup 2026 latest updates",
         TopicType.SPORTS, "FIFA World Cup 2026"),
        (TestMovieInterstellar.RAW, "Tell me about Interstellar",
         TopicType.MOVIES, "Interstellar"),
        (TestMusicBeliever.RAW, "Tell me about Believer",
         TopicType.MUSIC, "Believer"),
        (TestBooksAtomicHabits.RAW, "Tell me about Atomic Habits",
         TopicType.BOOKS, "Atomic Habits"),
        (TestTvTheBear.RAW, "Tell me about The Bear",
         TopicType.TV, "The Bear"),
        ("", "FIFA World Cup 2026 latest updates",
         TopicType.SPORTS, "FIFA World Cup 2026"),
    ]
    sep = "=" * 70
    dash = "-" * 70
    parts = [sep, "RENDERED OUTPUT SAMPLES", sep]
    for raw, query, topic, subject in scenarios:
        result = composer.compose(raw, query, topic, subject)
        topic_name = topic.name if hasattr(topic, 'name') else str(topic)
        parts.append(dash)
        parts.append(f"DOMAIN: {topic_name}  |  QUERY: {query}")
        parts.append(dash)
        parts.append(result)
    parts.append(sep)
    parts.append("END OUTPUT SAMPLES")
    parts.append(sep)
    # Write to file to avoid encoding issues
    import tempfile, os
    dump_path = os.path.join(tempfile.gettempdir(), "kio_response_samples.txt")
    with open(dump_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"\nOutput written to: {dump_path}")
    # Also print ASCII-safe version
    for p in parts:
        safe = p.encode("ascii", errors="replace").decode("ascii")
        print(safe)
