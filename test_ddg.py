import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mini_kio.knowledge import duckduckgo_provider

queries = [
    "Atomic Habits author",
    "Atomic Habits writer creator",
    "Atomic Habits",
]

for q in queries:
    print(f"{'='*70}")
    print(f"QUERY: {q!r}")
    print(f"{'='*70}")
    try:
        result = duckduckgo_provider.search(q)
    except Exception as e:
        result = None
        print(f"EXCEPTION: {e}")
    if result:
        print(f"RESULT LENGTH: {len(result)} chars")
        print(f"FIRST 500 CHARS:")
        print(result[:500])
    else:
        print("RESULT: empty")
    print()
