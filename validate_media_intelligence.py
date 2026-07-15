import os
import sys
import logging
from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO)

def run_chain(chain, chain_name):
    print(f"\n{'='*20} {chain_name} {'='*20}")
    for i, input_text in enumerate(chain, 1):
        print(f"\n[{i}] USER: {input_text}")
        result = dispatch_channel_input(input_text, channel="local_test")
        message = result.get("message", "(no message)")
        print(f"[{i}] KIO: \n{message}")
        # print(f"    (success: {result.get('success')}, orchestrated: {result.get('_orchestrated')})")

def main():
    runtime = bootstrap_runtime()
    
    # Chain 1: Interstellar
    chain_interstellar = [
        "Interstellar",
        "Who directed it?",
        "Explain story",
        "Trailer",
        "Yes",
        "Ending explained"
    ]
    
    # Chain 2: Atomic Habits
    chain_atomic = [
        "Who wrote Atomic Habits?",
        "Summary",
        "Audiobook",
        "Yes"
    ]
    
    # Chain 3: The Bear
    chain_bear = [
        "Who created The Bear?",
        "Cast",
        "Trailer",
        "Yes"
    ]

    # Chain 4: Believer
    chain_believer = [
        "Who sings Believer?",
        "Lyrics meaning",
        "Play song",
        "Spotify"
    ]

    # Chain 5: FIFA World Cup
    chain_fifa = [
        "What happened in FIFA World Cup 2022?",
        "Who scored most goals?",
        "History",
        "Highlights"
    ]

    # Chain 6: Arbitrary questions
    chain_misc = [
        "What is quantum tunneling?",
        "Explain simply",
        "Rust programming language",
        "Why use it?",
        "French Revolution",
        "Summary"
    ]

    # run_chain(chain_interstellar, "INTERSTELLAR CHAIN")
    # run_chain(chain_atomic, "ATOMIC HABITS CHAIN")
    # run_chain(chain_bear, "THE BEAR CHAIN")
    # run_chain(chain_believer, "BELIEVER CHAIN")
    # run_chain(chain_fifa, "FIFA WORLD CUP CHAIN")
    run_chain(chain_misc, "MISC QUESTIONS CHAIN")

if __name__ == "__main__":
    main()
