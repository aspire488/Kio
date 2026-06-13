"""
mini_kio/intelligence/local_reasoner.py

Local Reasoner — Layer 4
==========================
Deterministic reasoning from runtime context and query signals.
No APIs. No internet. No local LLMs. No Ollama. No GGUF models.

Covers:
  - help / command explanations
  - runtime status and diagnostics
  - provider failure explanations
  - browser troubleshooting
  - capability explanations
  - runtime state introspection
  - error analysis from runtime context

Design:
  Input: user query + optional runtime_context dict
  Output: deterministic text response or None
  Mechanism: rule-based pattern matching + context inspection
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static knowledge bases — deterministic, never stale
# ---------------------------------------------------------------------------

_COMMAND_EXPLANATIONS: dict[str, str] = {
    "open": (
        "The 'open' command launches an application. "
        "Usage: 'open chrome', 'open notepad', 'open spotify'. "
        "KIO resolves the application path and launches it using the OS."
    ),
    "close": (
        "The 'close' command terminates a running application. "
        "Usage: 'close chrome', 'close notepad'. "
        "KIO uses the process name to find and close the target. "
        "Note: browser tabs cannot be closed by PID — use Ctrl+W in the browser."
    ),
    "search": (
        "The 'search' command opens a web search. "
        "Usage: 'search python tutorials', 'search weather today'. "
        "KIO opens your default browser with the search query."
    ),
    "play": (
        "The 'play' command opens YouTube with your search query. "
        "Usage: 'play lo-fi music', 'play python tutorial'. "
        "KIO navigates to YouTube search results for the query."
    ),
    "status": (
        "The 'status' command shows KIO's current runtime state: "
        "provider health, active operators, RAM usage (if available), "
        "and lifecycle state (READY / ACTIVE / DEGRADED)."
    ),
    "diagnostics": (
        "The 'diagnostics' command runs a self-check of KIO's subsystems: "
        "provider connectivity, operator registry, memory state, and configuration."
    ),
    "help": (
        "Available KIO commands: open, close, search, play, status, diagnostics, help. "
        "Examples: 'open chrome', 'search python', 'play lo-fi', 'close spotify'. "
        "For multi-step: 'open chrome and search python tutorials'."
    ),
}

_PROVIDER_FAILURE_EXPLANATIONS: dict[str, str] = {
    "quota": (
        "The cloud provider has exhausted its quota. "
        "KIO will automatically retry other providers in the chain. "
        "If all providers fail, KIO operates in local-only mode."
    ),
    "timeout": (
        "The cloud provider did not respond within the timeout window. "
        "KIO automatically fails over to the next provider. "
        "Check your internet connection if this persists."
    ),
    "auth": (
        "Provider authentication failed. "
        "Check that your API key is set correctly in the KIO configuration. "
        "KIO will attempt other configured providers."
    ),
    "dns": (
        "DNS resolution failed — the provider's hostname could not be resolved. "
        "This indicates a network connectivity issue. "
        "KIO will operate in local-only mode until connectivity is restored."
    ),
    "all_failed": (
        "All cloud providers are currently unavailable. "
        "KIO is operating in local intelligence mode. "
        "Available: identity questions, capability explanations, "
        "help, diagnostics, and all desktop commands. "
        "LLM-backed responses are unavailable until connectivity is restored."
    ),
}

_BROWSER_TROUBLESHOOTING: dict[str, str] = {
    "chrome_not_open": (
        "Chrome did not open. Possible causes: "
        "(1) Chrome is not installed at the expected path. "
        "(2) The Chrome executable path in KIO config is incorrect. "
        "(3) Chrome is already running and the profile is locked. "
        "Try: 'open chrome' again, or check if Chrome is already running."
    ),
    "tab_not_closed": (
        "Browser tabs cannot be closed by process ID — this is an architectural constraint. "
        "To close a tab: use Ctrl+W in the browser, or use the browser extension if configured. "
        "KIO can close the entire Chrome process with 'close chrome' if needed."
    ),
    "extension_not_loaded": (
        "The KIO browser extension is not loaded. "
        "Load it by opening Chrome → Extensions → Load unpacked → select the extension folder. "
        "The extension is required for tab-level browser control."
    ),
    "websocket_refused": (
        "The browser connector WebSocket was refused. "
        "The KIO connector service may not be running, or the port (9877) is blocked. "
        "Check: KIO connector is started, no firewall blocking localhost:9877."
    ),
}

_RUNTIME_STATES: dict[str, str] = {
    "INIT": "KIO is initializing. Not yet ready for commands.",
    "READY": "KIO is initialized and ready for commands.",
    "ACTIVE": "KIO is running and processing.",
    "DEGRADED": (
        "KIO is in degraded mode. One or more components are unavailable. "
        "Desktop commands still work. Cloud intelligence is limited."
    ),
    "SHUTDOWN": "KIO is shutting down. New commands are not accepted.",
}


class LocalReasoner:
    """
    Deterministic reasoner: produces answers from query signals and runtime context.
    No LLM. No internet. No external calls.
    """

    def reason(self, query: str, *, runtime_context: Optional[dict] = None) -> Optional[str]:
        """
        Attempt to produce a useful response from local reasoning only.

        Args:
            query: User query string.
            runtime_context: Optional dict containing:
                'last_error': str — last error message
                'provider_status': dict — per-provider status
                'runtime_state': str — INIT/READY/ACTIVE/DEGRADED/SHUTDOWN
                'last_command': str — last executed command
                'failure_class': str — quota/timeout/auth/dns/all_failed

        Returns:
            Reasoning result string, or None if no applicable pattern matched.
        """
        if not query:
            return None

        q = query.strip().lower()
        ctx = runtime_context or {}

        # ── Help / command explanations ───────────────────────────────────────
        result = self._reason_help(q)
        if result:
            return result

        # ── Runtime status ────────────────────────────────────────────────────
        result = self._reason_runtime_status(q, ctx)
        if result:
            return result

        # ── Provider failures ─────────────────────────────────────────────────
        result = self._reason_provider_failure(q, ctx)
        if result:
            return result

        # ── Browser issues ────────────────────────────────────────────────────
        result = self._reason_browser(q, ctx)
        if result:
            return result

        # ── Error explanation from context ────────────────────────────────────
        result = self._reason_from_error_context(q, ctx)
        if result:
            return result

        # ── Capability explanation ────────────────────────────────────────────
        result = self._reason_capabilities(q)
        if result:
            return result

        return None

    def _reason_help(self, q: str) -> Optional[str]:
        """Match help and command explanation queries."""
        # Direct help
        if q in ("help", "?", "commands", "list commands", "what commands"):
            return _COMMAND_EXPLANATIONS["help"]

        # Specific command explanation
        for cmd, explanation in _COMMAND_EXPLANATIONS.items():
            if cmd == "help":
                continue
            patterns = [
                f"how do i {cmd}",
                f"how to {cmd}",
                f"what does {cmd} do",
                f"explain {cmd}",
                f"what is {cmd} command",
                f"how does {cmd} work",
            ]
            for pat in patterns:
                if pat in q:
                    return explanation

        return None

    def _reason_runtime_status(self, q: str, ctx: dict) -> Optional[str]:
        """Answer runtime state questions using context."""
        _status_triggers = (
            "status", "runtime status", "how are you", "are you running",
            "are you online", "are you working", "what is your state",
        )
        if not any(t in q for t in _status_triggers):
            return None

        state = ctx.get("runtime_state", "UNKNOWN")
        state_desc = _RUNTIME_STATES.get(state, f"Runtime state: {state}.")

        provider_status = ctx.get("provider_status", {})
        if provider_status:
            working = [k for k, v in provider_status.items() if v == "healthy"]
            failed = [k for k, v in provider_status.items() if v != "healthy"]
            provider_line = ""
            if working:
                provider_line = f" Providers online: {', '.join(working)}."
            if failed:
                provider_line += f" Providers offline: {', '.join(failed)}."
            return state_desc + provider_line

        return state_desc

    def _reason_provider_failure(self, q: str, ctx: dict) -> Optional[str]:
        """Explain provider failures from context or query signals."""
        _failure_triggers = (
            "why did the ai fail", "why is ai not working", "why no response",
            "provider failed", "why are you offline", "why degraded",
            "why can't you answer", "why wont you answer",
        )
        matched_query = any(t in q for t in _failure_triggers)

        failure_class = ctx.get("failure_class", "")
        if not matched_query and not failure_class:
            return None

        if failure_class and failure_class in _PROVIDER_FAILURE_EXPLANATIONS:
            return _PROVIDER_FAILURE_EXPLANATIONS[failure_class]

        # Infer from context
        if ctx.get("all_providers_failed"):
            return _PROVIDER_FAILURE_EXPLANATIONS["all_failed"]

        if matched_query:
            # Generic provider failure explanation
            return (
                "Cloud intelligence providers are currently unavailable. "
                "This can be caused by: quota exhaustion, network outage, "
                "DNS failure, or authentication errors. "
                "KIO continues to operate with local capabilities: "
                "desktop commands, help, and diagnostics."
            )

        return None

    def _reason_browser(self, q: str, ctx: dict) -> Optional[str]:
        """Handle browser-related troubleshooting queries."""
        _browser_triggers = (
            "chrome", "browser", "tab", "extension", "websocket", "connector",
        )
        if not any(t in q for t in _browser_triggers):
            return None

        # Specific browser issue patterns
        if any(t in q for t in ("chrome not open", "chrome won't open", "chrome failed", "chrome didn't open")):
            return _BROWSER_TROUBLESHOOTING["chrome_not_open"]

        if any(t in q for t in ("tab not closed", "can't close tab", "tab won't close", "close tab")):
            return _BROWSER_TROUBLESHOOTING["tab_not_closed"]

        if any(t in q for t in ("extension not loaded", "extension not working", "extension failed")):
            return _BROWSER_TROUBLESHOOTING["extension_not_loaded"]

        if any(t in q for t in ("connection refused", "websocket refused", "port 9877", "connector refused")):
            return _BROWSER_TROUBLESHOOTING["websocket_refused"]

        # Check context for browser errors
        last_error = ctx.get("last_error", "").lower()
        if "chrome" in last_error or "browser" in last_error:
            last_cmd = ctx.get("last_command", "")
            if "tab" in last_error:
                return _BROWSER_TROUBLESHOOTING["tab_not_closed"]
            return (
                f"A browser error occurred during '{last_cmd}': {ctx.get('last_error', 'unknown error')}. "
                "Check that Chrome is installed and the KIO browser extension is loaded."
            )

        # Generic browser help
        if "browser" in q or "chrome" in q:
            return (
                "KIO can open URLs and search the web via Chrome. "
                "Tab-level control requires the KIO browser extension. "
                "Commands: 'open chrome', 'search [query]', 'play [media]'. "
                "To close Chrome entirely: 'close chrome'."
            )

        return None

    def _reason_from_error_context(self, q: str, ctx: dict) -> Optional[str]:
        """Generate explanation from last_error + last_command in context."""
        last_error = ctx.get("last_error", "")
        last_command = ctx.get("last_command", "")

        if not last_error:
            return None

        _why_triggers = ("why", "what happened", "what went wrong", "explain", "error", "failed", "didn't work")
        if not any(t in q for t in _why_triggers):
            return None

        # Generate a deterministic explanation based on error class
        error_lower = last_error.lower()

        if "permission" in error_lower or "access denied" in error_lower:
            return (
                f"The command '{last_command}' failed due to a permissions error. "
                "Try running KIO with appropriate permissions, or check that "
                "the target application or file is not locked."
            )

        if "not found" in error_lower or "no such file" in error_lower:
            return (
                f"The command '{last_command}' failed because the target was not found. "
                "Check that the application is installed, or verify the path in KIO config."
            )

        if "timeout" in error_lower:
            return (
                f"The command '{last_command}' timed out. "
                "The operation took longer than the allowed window. "
                "Try again, or check if the target system is responsive."
            )

        if "connection refused" in error_lower or "network" in error_lower:
            return (
                f"The command '{last_command}' failed due to a network error. "
                "Check your internet connection and try again."
            )

        # Generic error with raw message (bounded)
        return (
            f"The last command '{last_command}' failed. "
            f"Error: {last_error[:120]}. "
            "Check KIO's diagnostics with 'diagnostics' for more detail."
        )

    def _reason_capabilities(self, q: str) -> Optional[str]:
        """Answer capability questions without providers."""
        _cap_triggers = (
            "what can you do", "your capabilities", "can you", "are you able",
            "do you support", "does kio support", "does kio have",
        )
        if not any(t in q for t in _cap_triggers):
            return None

        # Check for specific capability probes
        if any(t in q for t in ("camera", "webcam")):
            return (
                "KIO can activate the system camera with explicit activation. "
                "Camera is off by default. It can capture frames for analysis "
                "and releases the device after use."
            )

        if any(t in q for t in ("file", "folder", "directory")):
            return (
                "KIO can open folders and navigate the filesystem. "
                "Filesystem write access requires explicit configuration. "
                "Commands: 'open [folder path]'."
            )

        if any(t in q for t in ("music", "play", "media", "youtube", "spotify")):
            return (
                "KIO can play media by opening YouTube with a search query "
                "('play lo-fi music') or launch media apps ('open spotify'). "
                "Direct playback control requires the app to be open."
            )

        # Generic capability summary
        return (
            "KIO capabilities: open/close applications, web search, YouTube playback, "
            "folder navigation, multi-step commands, conversational assistance, "
            "camera activation, and browser control (with extension). "
            "Type 'help' for the command list."
        )
