
import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from mini_kio.core.command_router import handle_command

def test_command(cmd):
    print(f"\nTesting: {cmd}")
    result = handle_command(cmd)
    print(f"Result: {result}")
    return result

if __name__ == "__main__":
    # 1. Greetings
    test_command("Hello")
    test_command("hi")
    
    # 2. Malformed chain vs valid single step
    test_command("Search cats and dogs")
    test_command("Open chrome and")
    test_command("search cats and")
    
    # 3 & 4. Play ambiguity
    test_command("Play messi")
    
    # 5. Play with target (Spotify)
    test_command("Play believer on Spotify")
    
    # 6. Play with target (YouTube)
    test_command("Play messi on youtube")
    
    # 7. Browser-targeted search
    test_command("Search messi in edge")
    
    # 8. UWP close (mocking a PID for calc)
    from mini_kio.core.app_operator import close_app
    print("\nTesting: Close calc (mocked PID 12345)")
    # Note: This will likely fail taskkill but we want to see the message if it "succeeds" or the UWP honesty check
    # Actually, let's just test the logic by calling it and seeing how it handles a non-existent PID
    # But wait, close_app requires a name that matches Calculator in registry
    result = close_app("calculator", pid=999999) # Very unlikely PID
    print(f"Result: {result}")
