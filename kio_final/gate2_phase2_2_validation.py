
import sys
import os
import time
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from mini_kio.core.app_operator import launch_app, close_app, APP_REGISTRY
from mini_kio.core.runtime import bootstrap_runtime, _CURRENT_RUNTIME
from mini_kio.core.execution_boundary import execute_action

def validate_ownership_isolation():
    print("--- GATE 2 PHASE 2.2 OWNERSHIP ISOLATION VALIDATION ---")
    
    # 1. Setup Runtime
    runtime = bootstrap_runtime()
    
    # 2. Setup Test App
    test_script = "import time; time.sleep(60)"
    test_cmd = [sys.executable, "-c", test_script]
    APP_REGISTRY["test_app"] = {
        "exe": "python.exe",
        "process": "python.exe",
        "system": False
    }

    # Start manual instance
    print("Step 1: Starting manual test_app (untracked)...")
    manual_proc = subprocess.Popen(test_cmd)
    manual_pid = manual_proc.pid
    print(f"  Manual PID: {manual_pid}")
    
    try:
        # 3. Verify untracked isolation (no wildcard kill)
        print("Step 2: Verify untracked isolation...")
        # Ensure registry is empty for this app
        runtime.tracked_processes = [p for p in runtime.tracked_processes if p["name"] != "test_app"]
        
        res_close = execute_action("close_app", "test_app")
        print(f"  Close untracked result: {res_close}")
        assert res_close["success"] == False
        assert "No tracked process found" in res_close["message"]
        
        # Verify Manual survives
        manual_alive = manual_proc.poll() is None
        print(f"  Manual Alive: {manual_alive} (Expect True)")
        assert manual_alive == True
        
        # 4. Verify targeted kill logic (Mocked subprocess to avoid /F issues)
        print("Step 3: Verify targeted kill parameters...")
        runtime.register_tracked_process(pid=manual_pid, name="test_app", target="test_app")
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            res = execute_action("close_app", "test_app")
            
            # Find the taskkill call among potentially other calls (like tasklist)
            taskkill_call = None
            for call in mock_run.call_args_list:
                args = call[0][0]
                if "taskkill" in args:
                    taskkill_call = args
                    break
            
            print(f"  Taskkill call found: {taskkill_call}")
            assert taskkill_call is not None
            assert "/T" in taskkill_call
            assert "/PID" in taskkill_call
            assert str(manual_pid) in taskkill_call
            assert "/IM" not in taskkill_call, "WILDCARD DETECTED!"
            assert res["success"] == True

    finally:
        if manual_proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(manual_pid), "/F", "/T"], capture_output=True)
            
    print("--- VALIDATION PASSED ---")

if __name__ == "__main__":
    validate_ownership_isolation()
