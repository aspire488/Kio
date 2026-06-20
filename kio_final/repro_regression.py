
import logging
import sys
import os

# Mocking and setup
from mini_kio.core.command_router import handle_command
from mini_kio.media.media_manager import MediaManager

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("repro")

def test_turn(query):
    print(f"\n>>> USER: {query}")
    result = handle_command(query)
    print(f"<<< KIO: {result.get('message')}")
    return result

def run_repro():
    # Test A & B reproduction
    test_turn("Tell me about Interstellar")
    test_turn("who directed it")
    test_turn("show movie clips")
    
    # Test C reproduction
    MediaManager.get_instance().get_context().reset()
    test_turn("show movie clips")
    test_turn("Interstellar")
    test_turn("behind the scenes")

if __name__ == "__main__":
    run_repro()
