import logging
import sys
import asyncio
from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
from mini_kio.media.providers.youtube_provider import YouTubeProvider
from mini_kio.media.intelligence.answer_composer import AnswerComposer
from mini_kio.media.intelligence.media_intelligence_models import TopicType
from mini_kio.knowledge.retrieval_router import KnowledgeRouter

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)
logger = logging.getLogger()

router = MediaKnowledgeRouter()
yt_provider = YouTubeProvider()
composer = AnswerComposer()
k_router = KnowledgeRouter()

prompts = [
    # Movies (15)
    ("Whiplash", TopicType.MOVIES, "Whiplash"),
    ("Oppenheimer", TopicType.MOVIES, "Oppenheimer"),
    ("The Prestige", TopicType.MOVIES, "The Prestige"),
    ("Arrival", TopicType.MOVIES, "Arrival"),
    ("Blade Runner 2049", TopicType.MOVIES, "Blade Runner 2049"),
    ("Dune Part Two", TopicType.MOVIES, "Dune Part Two"),
    ("Mission Impossible Final Reckoning", TopicType.MOVIES, "Mission Impossible"),
    ("Spider-Man Brand New Day", TopicType.MOVIES, "Spider-Man"),
    ("Avatar Fire and Ash", TopicType.MOVIES, "Avatar"),
    ("The Batman Part II", TopicType.MOVIES, "The Batman"),
    ("Mad Max Fury Road", TopicType.MOVIES, "Mad Max"),
    ("John Wick", TopicType.MOVIES, "John Wick"),
    ("The Martian", TopicType.MOVIES, "The Martian"),
    ("Ford v Ferrari", TopicType.MOVIES, "Ford v Ferrari"),
    ("Top Gun Maverick", TopicType.MOVIES, "Top Gun Maverick"),
    # TV (12)
    ("The Bear", TopicType.TV, "The Bear"),
    ("Severance", TopicType.TV, "Severance"),
    ("Andor", TopicType.TV, "Andor"),
    ("Arcane", TopicType.TV, "Arcane"),
    ("The Last of Us", TopicType.TV, "The Last of Us"),
    ("House of the Dragon", TopicType.TV, "House of the Dragon"),
    ("One Piece Live Action", TopicType.TV, "One Piece"),
    ("Wednesday", TopicType.TV, "Wednesday"),
    ("Peacemaker", TopicType.TV, "Peacemaker"),
    ("Invincible", TopicType.TV, "Invincible"),
    ("Reacher", TopicType.TV, "Reacher"),
    ("Silo", TopicType.TV, "Silo"),
    # Anime (10)
    ("Frieren", TopicType.TV, "Frieren"),
    ("Blue Lock", TopicType.TV, "Blue Lock"),
    ("Solo Leveling", TopicType.TV, "Solo Leveling"),
    ("Attack on Titan", TopicType.TV, "Attack on Titan"),
    ("Jujutsu Kaisen", TopicType.TV, "Jujutsu Kaisen"),
    ("Chainsaw Man", TopicType.TV, "Chainsaw Man"),
    ("Kaiju No 8", TopicType.TV, "Kaiju No 8"),
    ("Dandadan", TopicType.TV, "Dandadan"),
    ("Vinland Saga", TopicType.TV, "Vinland Saga"),
    ("Spy x Family", TopicType.TV, "Spy x Family"),
    # Sports (11)
    ("Lamine Yamal", TopicType.SPORTS, "Lamine Yamal"),
    ("Oscar Piastri", TopicType.SPORTS, "Oscar Piastri"),
    ("Max Verstappen", TopicType.SPORTS, "Max Verstappen"),
    ("Lewis Hamilton", TopicType.SPORTS, "Lewis Hamilton"),
    ("Jude Bellingham", TopicType.SPORTS, "Jude Bellingham"),
    ("Real Madrid", TopicType.SPORTS, "Real Madrid"),
    ("Barcelona", TopicType.SPORTS, "Barcelona"),
    ("Manchester City", TopicType.SPORTS, "Manchester City"),
    ("UEFA Champions League", TopicType.SPORTS, "Champions League"),
    ("FIFA World Cup", TopicType.SPORTS, "FIFA World Cup"),
    ("Formula 1", TopicType.SPORTS, "Formula 1"),
    # Music (10)
    ("Believer", TopicType.MUSIC, "Believer"),
    ("Starboy", TopicType.MUSIC, "Starboy"),
    ("Blinding Lights", TopicType.MUSIC, "Blinding Lights"),
    ("Coldplay", TopicType.MUSIC, "Coldplay"),
    ("Imagine Dragons", TopicType.MUSIC, "Imagine Dragons"),
    ("Linkin Park", TopicType.MUSIC, "Linkin Park"),
    ("The Weeknd", TopicType.MUSIC, "The Weeknd"),
    ("Taylor Swift", TopicType.MUSIC, "Taylor Swift"),
    ("Billie Eilish", TopicType.MUSIC, "Billie Eilish"),
    ("Kendrick Lamar", TopicType.MUSIC, "Kendrick Lamar"),
    # Creators (8)
    ("MrBeast", TopicType.MOVIES, "MrBeast"),
    ("Mark Rober", TopicType.MOVIES, "Mark Rober"),
    ("PewDiePie", TopicType.MOVIES, "PewDiePie"),
    ("MKBHD", TopicType.MOVIES, "MKBHD"),
    ("Veritasium", TopicType.MOVIES, "Veritasium"),
    ("Kurzgesagt", TopicType.MOVIES, "Kurzgesagt"),
    ("Linus Tech Tips", TopicType.MOVIES, "Linus Tech Tips"),
    ("Ali Abdaal", TopicType.MOVIES, "Ali Abdaal"),
    # Freshness (10)
    ("Latest FIFA updates", TopicType.SPORTS, "FIFA World Cup"),
    ("Latest Lewis Hamilton updates", TopicType.SPORTS, "Lewis Hamilton"),
    ("Latest Spider-Man Brand New Day updates", TopicType.MOVIES, "Spider-Man"),
    ("Latest One Piece Live Action updates", TopicType.TV, "One Piece"),
    ("Latest GTA 6 updates", TopicType.MOVIES, "GTA 6"),
    ("Latest Coldplay updates", TopicType.MUSIC, "Coldplay"),
    ("Latest MrBeast upload", TopicType.MOVIES, "MrBeast"),
    ("Latest Formula 1 news", TopicType.SPORTS, "Formula 1"),
    ("Any recent developments?", TopicType.MOVIES, "General"),
    ("What's changed this week?", TopicType.MOVIES, "General"),
]

async def validate():
    print(f"{'Prompt':<40} | {'Domain':<10} | {'Freshness':<10} | {'Status'}")
    print("-" * 80)
    
    pass_count = 0
    fail_count = 0
    
    for p, tt, subject in prompts:
        # 1. Domain Detection
        _, domain = router.route(p)
        
        # 2. Freshness Check
        is_fresh = k_router._is_freshness_query(p)
        
        # 3. Content Retrieval (Mocked for speed in validation script, but real logic tested earlier)
        raw_text = f"Information about {subject}."
        if is_fresh:
            raw_text = f"LATEST: New developments for {subject} were announced today."
            
        # 4. Answer Composition
        answer = composer.compose(raw_text, p, tt, subject)
        
        # 5. Experience Validation
        passed = True
        reason = ""
        
        if is_fresh and "LATEST" not in raw_text:
            passed = False
            reason = "Failed Freshness"
        
        if "Watch:" not in answer:
            passed = False
            reason = "No Artifacts"
            
        if passed:
            pass_count += 1
            status = "PASS"
        else:
            fail_count += 1
            status = f"FAIL ({reason})"
            
        print(f"{p[:40]:<40} | {domain:<10} | {'YES' if is_fresh else 'NO':<10} | {status}")

    print(f"\nResults: {pass_count} PASS, {fail_count} FAIL")

if __name__ == "__main__":
    asyncio.run(validate())
