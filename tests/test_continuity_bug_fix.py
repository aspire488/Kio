import logging
import os
from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input
from mini_kio.core.continuity_resolver import ContinuityResolver

# Configure logging to capture our new markers
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_test_a():
    print("\n--- Test A: Cross-domain Subject Cleanup ---")
    rt = bootstrap_runtime()
    
    # Step 1: Establish technical subject
    print("User: explain python decorators")
    res1 = dispatch_channel_input("explain python decorators")
    print(f"KIO: {res1.get('message')[:50]}...")
    
    # Verify state
    state = ContinuityResolver.get_state()
    print(f"State subject: {state.active_subject}")
    
    # Step 2: Sports query (unrelated)
    print("\nUser: what happened in the brazil match")
    res2 = dispatch_channel_input("what happened in the brazil match")
    
    # Verify subject was updated or at least 'python decorators' was evicted
    print(f"State subject AFTER sports: {state.active_subject}")
    
    if "brazil" in str(state.active_subject).lower():
        print("PASS: Subject updated to Brazil")
    elif state.active_subject != "python decorators":
         print(f"PASS: Subject 'python decorators' evicted (current: {state.active_subject})")
    else:
        print("FAIL: Subject 'python decorators' still persists")

def run_test_b():
    print("\n--- Test B: Sports Context Registration ---")
    # Fresh state
    ContinuityResolver.reset()
    rt = bootstrap_runtime()
    
    print("User: latest fifa world cup updates")
    dispatch_channel_input("latest fifa world cup updates")
    
    print("\nUser: what happened in the brazil match")
    dispatch_channel_input("what happened in the brazil match")
    # Check for [FOLLOWUP_FALLTHROUGH] in logs manually or via mock if needed
    # But here we just check if it works

def run_test_c():
    print("\n--- Test C: Replay Resolution ---")
    ContinuityResolver.reset()
    bootstrap_runtime()
    
    print("User: play believer")
    dispatch_channel_input("play believer")
    
    print("\nUser: play it again")
    res = dispatch_channel_input("play it again")
    # Should see [REPLAY_RESOLVED] or [FOLLOWUP_RESOLVED]
    print(f"KIO: {res.get('message')}")

if __name__ == "__main__":
    os.environ["KIO_TEST_MODE"] = "0" # We need real logic execution
    try:
        run_test_a()
        run_test_b()
        run_test_c()
    except Exception as e:
        print(f"Test crashed: {e}")
        import traceback
        traceback.print_exc()
