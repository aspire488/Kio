import os
from mini_kio.intelligence.retrieval_router import RetrievalRouter, RetrievalTopic

def test_retrieval():
    router = RetrievalRouter()
    queries = [
        "What is quantum tunneling?",
        "Who created The Bear?",
        "What happened in FIFA World Cup 2022?",
        "Explain Kubernetes.",
        "Who wrote Atomic Habits?",
        "Why is the sky blue?",
        "Who directed Interstellar?",
        "What is Rust programming language?",
        "What happened in the French Revolution?"
    ]
    
    for q in queries:
        print(f"\nQuery: {q}")
        res = router.retrieve(q)
        if res:
            print(f"Title: {res.title}")
            print(f"Source: {res.source}")
            print(f"Summary: {res.summary[:200]}...")
        else:
            print("Failed to retrieve.")

if __name__ == "__main__":
    test_retrieval()
