import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

from mini_kio.knowledge.retrieval_router import KnowledgeRouter
from mini_kio.media.media_manager import MediaManager

# Configure logging to stdout for capture
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

def simulate_conversation():
    router = KnowledgeRouter()
    mm = MediaManager.get_instance()
    adapter = mm._intelligence_adapter

    print("\n=== CONVERSATION 1 ===")
    q1 = "Tell me about Christopher Nolan's movie Interstellar and show me available media."
    print(f"User: {q1}")
    res1 = router.route(q1)
    print(f"KIO:\n{res1}")

    q2 = "Who directed it?"
    print(f"\nUser: {q2}")
    # Simulate LLM deciding it's a follow-up for media
    res2 = adapter.handle(q2)
    print(f"KIO: {res2.response_text}")

    q3 = "Are there any interviews with Christopher Nolan about the film?"
    print(f"\nUser: {q3}")
    res3 = adapter.handle(q3)
    print(f"KIO: {res3.response_text}")

    q4 = "Show them."
    print(f"\nUser: {q4}")
    res4 = adapter.handle(q4)
    print(f"KIO: {res4.response_text}")

    q5 = "Play the first one."
    print(f"\nUser: {q5}")
    res5 = adapter.handle(q5)
    print(f"KIO: {res5.response_text}")

    print("\n=== CONVERSATION 2 ===")
    q6 = "Tell me about Spider-Man Brand New Day and any upcoming trailers."
    print(f"User: {q6}")
    res6 = router.route(q6)
    print(f"KIO:\n{res6}")

    q7 = "Play the trailer."
    print(f"\nUser: {q7}")
    res7 = adapter.handle(q7)
    print(f"KIO: {res7.response_text}")

    print("\n=== CONVERSATION 3 ===")
    q8 = "Tell me about the TV series The Bear and show me available media."
    print(f"User: {q8}")
    res8 = router.route(q8)
    print(f"KIO:\n{res8}")

    print("\n=== CONVERSATION 4 ===")
    q9 = "Tell me about Imagine Dragons' song Believer and show me available media."
    print(f"User: {q9}")
    res9 = router.route(q9)
    print(f"KIO:\n{res9}")

    q10 = "Are there any live performances?"
    print(f"\nUser: {q10}")
    res10 = adapter.handle(q10)
    print(f"KIO: {res10.response_text}")

    q11 = "Play one."
    print(f"\nUser: {q11}")
    res11 = adapter.handle(q11)
    print(f"KIO: {res11.response_text}")

    print("\n=== CONVERSATION 5 ===")
    q12 = "What are the latest FIFA World Cup developments and what can I watch related to them?"
    print(f"User: {q12}")
    res12 = router.route(q12)
    print(f"KIO:\n{res12}")

    q13 = "Show highlights."
    print(f"\nUser: {q13}")
    res13 = adapter.handle(q13)
    print(f"KIO: {res13.response_text}")

    q14 = "Play them."
    print(f"\nUser: {q14}")
    res14 = adapter.handle(q14)
    print(f"KIO: {res14.response_text}")

if __name__ == "__main__":
    simulate_conversation()
