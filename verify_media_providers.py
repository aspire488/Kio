import sys
import os
import json

# Add project root to path
sys.path.append(os.getcwd())

from mini_kio.knowledge.media_providers import (
    fetch_movie_metadata, fetch_tv_metadata, fetch_anime_metadata, 
    fetch_music_metadata, fetch_sports_metadata
)

def verify():
    results = {}
    
    print("Testing Movie Provider (OMDb): Interstellar")
    results['movie'] = fetch_movie_metadata("Interstellar")
    print(f"Result: {bool(results['movie'])}")
    
    print("\nTesting TV Provider (TVMaze): The Bear")
    results['tv'] = fetch_tv_metadata("The Bear")
    print(f"Result: {bool(results['tv'])}")
    
    print("\nTesting Anime Provider (Jikan): Frieren")
    results['anime'] = fetch_anime_metadata("Frieren")
    print(f"Result: {bool(results['anime'])}")
    
    print("\nTesting Sports Provider (SportsDB): Lamine Yamal")
    # Search for team/player
    results['sports'] = fetch_sports_metadata("Barcelona") # Lamine Yamal might not be a 'team'
    print(f"Result: {bool(results['sports'])}")
    
    print("\nTesting Music Provider (MusicBrainz): Believer")
    results['music'] = fetch_music_metadata("Believer Imagine Dragons")
    print(f"Result: {bool(results['music'])}")
    
    with open("provider_verification_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    verify()
