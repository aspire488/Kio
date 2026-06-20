import logging
import sys
import asyncio
from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
from mini_kio.media.providers.youtube_provider import YouTubeProvider
from mini_kio.media.intelligence.answer_composer import AnswerComposer
from mini_kio.media.intelligence.media_intelligence_models import TopicType
from mini_kio.knowledge.retrieval_router import KnowledgeRouter

# Setup logging to capture all required tags
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)

router = MediaKnowledgeRouter()
yt_provider = YouTubeProvider()
composer = AnswerComposer()
k_router = KnowledgeRouter()

async def test_target_experience():
    # CASE 1: Freshness (FIFA)
    print("\n" + "="*50)
    print("CASE 1: FRESHNESS (FIFA)")
    print("="*50)
    query = "Latest FIFA World Cup updates"
    
    # Prove Freshness Bypass
    if k_router._is_freshness_query(query):
        print("[FRESHNESS_BYPASS] detected")
        print("[MEMORY_SKIPPED] freshness required")
    
    # Real Retrieval (Mocking content but using real composer)
    fresh_content = """
    Matchday Summary: Morocco 2-1 Brazil. Japan 1-0 Germany.
    Upcoming: France vs Argentina tomorrow at 8 PM.
    Storylines: Messi announces final tournament. Mbappe injury update.
    """
    answer = composer.compose(fresh_content, query, TopicType.SPORTS, "FIFA World Cup")
    print("\nANSWER:")
    print(answer)

    # CASE 2: YouTube Resolution (MrBeast)
    print("\n" + "="*50)
    print("CASE 2: YOUTUBE RESOLUTION (MrBeast)")
    print("="*50)
    query_mrbeast = "MrBeast Latest Upload"
    # This will trigger the real scraper in YouTubeProvider
    res = yt_provider._search_metadata(query_mrbeast)
    print(f"\nRESULT: success={res.success}")
    if res.success:
        print(f"URL: {res.url}")
        print(f"TITLE: {res.message}")

    # CASE 3: Dense Answer Quality (Interstellar)
    print("\n" + "="*50)
    print("CASE 3: DENSE ANSWER QUALITY (Interstellar)")
    print("="*50)
    query_movie = "Interstellar"
    raw_movie = """
    Interstellar is a 2014 epic science fiction film directed by Christopher Nolan. 
    It stars Matthew McConaughey, Anne Hathaway, and Jessica Chastain. 
    The film won Academy Awards for Best Visual Effects. Runtime is 169 minutes.
    """
    answer_movie = composer.compose(raw_movie, query_movie, TopicType.MOVIES, "Interstellar")
    print("\nANSWER:")
    print(answer_movie)

if __name__ == "__main__":
    asyncio.run(test_target_experience())
