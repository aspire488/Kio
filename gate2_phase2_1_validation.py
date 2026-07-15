
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add the project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from mini_kio.core.app_operator import launch_app, APP_REGISTRY

def test_alias_resolution():
    print("Testing Alias Resolution...")
    # Mocking subprocess.Popen to avoid actually opening apps
    with patch("subprocess.Popen") as mock_popen, \
         patch("shutil.which") as mock_which, \
         patch("mini_kio.core.app_operator._verify_process_started_windows") as mock_verify:
        
        mock_verify.return_value = True
        mock_which.return_value = "C:\\FakePath\\chrome.exe"
        
        # Test "browser" alias
        result = launch_app("browser")
        print(f"  'browser' -> {result}")
        assert result["success"] == True
        assert "Opened browser" in result["message"]
        
        # Test "editor" alias
        mock_which.return_value = "C:\\FakePath\\Code.exe"
        result = launch_app("editor")
        print(f"  'editor' -> {result}")
        assert result["success"] == True
        assert "Opened editor" in result["message"]

def test_registry_priority():
    print("Testing Registry Priority...")
    with patch("subprocess.Popen") as mock_popen, \
         patch("pathlib.Path.exists") as mock_exists, \
         patch("mini_kio.core.app_operator._verify_process_started_windows") as mock_verify:
        
        mock_exists.return_value = True
        mock_verify.return_value = True
        
        # Test "chrome" (explicit path in registry)
        result = launch_app("chrome")
        print(f"  'chrome' -> {result}")
        assert result["success"] == True
        
def test_malformed_rejection():
    print("Testing Malformed Rejection...")
    with patch("subprocess.run") as mock_run, \
         patch("shutil.which") as mock_which, \
         patch("mini_kio.core.app_operator._fuzzy_app_discovery") as mock_fuzzy:
        
        mock_run.return_value = MagicMock(returncode=1)
        mock_which.return_value = None
        mock_fuzzy.return_value = None
        
        # This will hit the "last resort" cmd start
        # To strictly test rejection, we mock Popen to fail or check the logic
        with patch("subprocess.Popen", side_effect=Exception("Failed")):
            result = launch_app("non_existent_app_xyz")
            print(f"  'non_existent_app_xyz' -> {result}")
            assert result["success"] == False

if __name__ == "__main__":
    try:
        test_alias_resolution()
        test_registry_priority()
        test_malformed_rejection()
        print("\nALL PHASE 2.1 LOGIC TESTS PASSED.")
    except Exception as e:
        print(f"\nTESTS FAILED: {e}")
        sys.exit(1)
