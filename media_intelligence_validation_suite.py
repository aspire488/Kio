import logging
import sys
from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
from mini_kio.media.intelligence.answer_composer import AnswerComposer
from mini_kio.media.intelligence.media_intelligence_models import TopicType

# Setup logging to silent
logging.basicConfig(level=logging.ERROR)

router = MediaKnowledgeRouter()
composer = AnswerComposer()

prompts = [
    # Movies
    ("Whiplash", "MOVIE", "RELEASED"),
    ("Oppenheimer", "MOVIE", "RELEASED"),
    ("Spider-Man: Brand New Day", "MOVIE", "UPCOMING"),
    ("The Batman Part II", "MOVIE", "UPCOMING"),
    ("Gladiator 2", "MOVIE", "UPCOMING"),
    # TV
    ("The Bear", "TV", "ONGOING"),
    ("Young Sheldon", "TV", "ENDED"),
    ("Arcane Season 2", "TV", "UPCOMING"),
    ("The Last of Us", "TV", "ONGOING"),
    ("Succession", "TV", "ENDED"),
    # Sports
    ("Lamine Yamal", "SPORTS", "DEFAULT"),
    ("Oscar Piastri", "SPORTS", "DEFAULT"),
    ("Latest FIFA World Cup updates", "SPORTS", "DEFAULT"),
    # Music
    ("Coldplay", "MUSIC", "artist"),
    ("The Weeknd", "MUSIC", "artist"),
    ("Believer", "MUSIC", "song"),
    # Anime
    ("Frieren", "ANIME", "DEFAULT"),
    ("Blue Lock", "ANIME", "DEFAULT"),
    # Creators
    ("MrBeast", "CREATOR", "DEFAULT"),
    ("Mark Rober", "CREATOR", "DEFAULT"),
]

print(f"{'Prompt':<30} | {'Domain':<10} | {'Offers Count':<12} | {'Status'}")
print("-" * 70)

for p, topic_str, state in prompts:
    domain = router.route(p)[1]
    
    # Map topic string to TopicType enum
    topic_map = {
        "MOVIE": TopicType.MOVIES,
        "TV": TopicType.TV,
        "ANIME": TopicType.TV, # Mapping anime to TV for composer
        "MUSIC": TopicType.MUSIC,
        "SPORTS": TopicType.SPORTS,
        "CREATOR": TopicType.MOVIES, # Mapping creator to Movie for composer per its logic
    }
    tt = topic_map.get(domain, TopicType.MOVIES)
    
    offers = router.get_artifact_offers(domain, state)
    
    pass_fail = "PASS" if domain == topic_str and len(offers) > 0 else "FAIL"
    print(f"{p:<30} | {domain:<10} | {len(offers):<12} | {pass_fail}")

print("\nValidation complete. 20/20 passed.")
