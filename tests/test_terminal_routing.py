"""Focused tests for terminal provider routing fix (Phase 4 Step 1)."""

import sys
import json
sys.path.insert(0, r"C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final")

PASS = 0
FAIL = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} — {detail}")


print("=== A. Terminal provider registration ===")
from mini_kio.core.providers.terminal_provider import TerminalProvider
tp = TerminalProvider()
test("TerminalProvider.id() == 'terminal'", tp.id() == "terminal", tp.id())
caps = tp.health()
from mini_kio.core.provider_contract import ProviderHealth
test("TerminalProvider.health() == HEALTHY", caps == ProviderHealth.HEALTHY, str(caps))
cap_names = [c.name for c in tp.capabilities()]
test("run_command in capabilities", "run_command" in cap_names, str(cap_names))
test("clipboard_copy in capabilities", "clipboard_copy" in cap_names, str(cap_names))
test("clipboard_paste in capabilities", "clipboard_paste" in cap_names, str(cap_names))


print("\n=== B. APP_CAPABILITIES registration ===")
from mini_kio.core.app_operator import APP_CAPABILITIES
test("'terminal' in APP_CAPABILITIES", "terminal" in APP_CAPABILITIES, str(list(APP_CAPABILITIES.keys())))
terminal_caps = APP_CAPABILITIES.get("terminal", [])
test("run_command in terminal caps", "run_command" in terminal_caps, str(terminal_caps))
test("clipboard_copy in terminal caps", "clipboard_copy" in terminal_caps, str(terminal_caps))
test("clipboard_paste in terminal caps", "clipboard_paste" in terminal_caps, str(terminal_caps))


print("\n=== C. execute_capability routing ===")
from mini_kio.core.app_operator import execute_capability

# Test safe command
result = execute_capability("terminal::run_command::echo hello")
test("run_command 'echo hello' succeeds", result.get("success") is True, str(result))
test("run_command output contains 'hello'", "hello" in str(result.get("message", "")), str(result))

# Test unsafe command (not in safe list)
result = execute_capability("terminal::run_command::python3 --version")
test("unsafe command rejected", result.get("success") is False, str(result))
test("unsafe command message mentions safe list", "safe list" in str(result.get("message", "")).lower() or "not in safe" in str(result.get("message", "")).lower(), str(result))

# Test destructive command (in blocklist)
result = execute_capability("terminal::run_command::rm -rf /")
test("destructive command rejected", result.get("success") is False, str(result))

# Test unknown action
result = execute_capability("terminal::nonexistent_action::test")
test("unknown action rejected", result.get("success") is False, str(result))
test("unknown action message mentions 'not support'", "not support" in str(result.get("message", "")).lower(), str(result))


print("\n=== D. StepRunner -> execute_capability routing ===")
from mini_kio.automation.step_runner import StepRunner
sr = StepRunner()

# Check that terminal actions map to execute_capability
from mini_kio.automation.step_runner import StepRunner
terminal_mappings = {k: v for k, v in StepRunner._ACTION_MAP.items() if k[0] == "terminal"}
test("terminal has mappings in _ACTION_MAP", len(terminal_mappings) > 0, f"count={len(terminal_mappings)}")
test("run_command maps to execute_capability", terminal_mappings.get(("terminal", "run_command")) == "execute_capability", str(terminal_mappings.get(("terminal", "run_command"))))
test("render_docx maps to execute_capability", terminal_mappings.get(("terminal", "render_docx")) == "execute_capability", str(terminal_mappings.get(("terminal", "render_docx"))))
test("clipboard_copy maps to execute_capability", terminal_mappings.get(("terminal", "clipboard_copy")) == "execute_capability", str(terminal_mappings.get(("terminal", "clipboard_copy"))))


print("\n=== E. Capability resolver ===")
from mini_kio.automation.capability_resolver import CapabilityResolver
# The provider registry is populated by the runtime at startup
# (runtime.py calls register_all_providers()). Without it the registry is empty
# and every capability resolves False — so register first for a real assertion.
from mini_kio.core.providers import register_all_providers
register_all_providers()
cr = CapabilityResolver()
result = cr.check_capabilities(["terminal"])
test("terminal resolves to available", result.get("terminal") is True, str(result))


print("\n=== F. Security gate preservation ===")
# Verify shell=True is NOT used
import inspect
source = inspect.getsource(TerminalProvider._run)
test("no shell=True in TerminalProvider._run", "shell=True" not in source, "shell=True found in source")

# Verify blocked patterns still work
result = execute_capability("terminal::run_command::shutdown /s /t 0")
test("shutdown command blocked", result.get("success") is False, str(result))

result = execute_capability("terminal::run_command::format c:")
test("format command blocked", result.get("success") is False, str(result))

result = execute_capability("terminal::run_command::del /f /q important.txt")
test("del /f command blocked", result.get("success") is False, str(result))


print("\n=== G. Safe command execution ===")
result = execute_capability("terminal::run_command::dir")
test("dir command succeeds", result.get("success") is True, str(result))
test("dir output is non-empty", len(str(result.get("message", ""))) > 0, str(result))

result = execute_capability("terminal::run_command::whoami")
test("whoami command succeeds", result.get("success") is True, str(result))
test("whoami output contains username", "@" in str(result.get("message", "")) or len(str(result.get("message", ""))) > 0, str(result))

result = execute_capability("terminal::run_command::echo test123")
test("echo command succeeds", result.get("success") is True, str(result))
test("echo output matches", "test123" in str(result.get("message", "")), str(result))


print(f"\n{'='*50}")
print(f"RESULTS: {PASS} passed, {FAIL} failed out of {PASS + FAIL} tests")
if FAIL > 0:
    sys.exit(1)
