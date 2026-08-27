"""
capability_registry.py — Gate 5.1 Capability Session Registry

Separates browser capability ownership from process ownership.
Tracks browser sessions (tabs/URLs) independently of process lifecycle.
"""

import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_CAPABILITY_LIMIT = 24

@dataclass
class CapabilityEntry:
    capability_id: str
    canonical_target: str
    browser: str
    url: str
    created_at: float
    last_used: float
    active: bool = True
    process_ref: Optional[str] = None
    browser_pid: Optional[int] = None
    ownership_scope: str = "kio"
    temp_profile_dir: Optional[str] = None


class CapabilityRegistry:
    def __init__(self, mcp_runtime: object | None = None):
        self._sessions: dict[str, CapabilityEntry] = {}
        self._counter: int = 0
        self._mcp_runtime: object | None = mcp_runtime
        self._diag: Dict[str, int] = {
            "capability_registered": 0,
            "capability_resolved": 0,
            "capability_deactivated": 0,
            "capability_lookup_failed": 0,
        }

    def set_mcp_runtime(self, mcp_runtime: object) -> None:
        """Inject MCPRuntime so capability discovery can use MCP tool registry."""
        self._mcp_runtime = mcp_runtime

    def get_mcp_tools(self, server_id: str | None = None) -> list[object]:
        """Delegate to MCPRuntime.registry for tool discovery."""
        if self._mcp_runtime is None:
            return []
        try:
            return self._mcp_runtime.list_tools(server_id=server_id)
        except Exception:
            return []

    def register(self, canonical_target: str, browser: str, url: str, browser_pid: Optional[int] = None, temp_profile_dir: Optional[str] = None) -> str:
        self._counter += 1
        cap_id = f"cap_{int(time.time())}_{self._counter:04d}"
        entry = CapabilityEntry(
            capability_id=cap_id,
            canonical_target=canonical_target.lower().strip(),
            browser=browser.lower().strip(),
            url=url,
            created_at=time.time(),
            last_used=time.time(),
            active=True,
            browser_pid=browser_pid,
            temp_profile_dir=temp_profile_dir,
        )
        self._sessions[cap_id] = entry
        # Enforce limit by evicting oldest inactive sessions
        if len(self._sessions) > _CAPABILITY_LIMIT:
            self._evict_oldest_inactive()
        self._diag["capability_registered"] += 1
        return cap_id

    def resolve_by_target(self, canonical_target: str) -> Optional[CapabilityEntry]:
        key = canonical_target.lower().strip()
        for entry in reversed(list(self._sessions.values())):
            if entry.canonical_target == key and entry.active:
                entry.last_used = time.time()
                self._diag["capability_resolved"] += 1
                return entry
        self._diag["capability_lookup_failed"] += 1
        return None

    def resolve_by_id(self, capability_id: str) -> Optional[CapabilityEntry]:
        entry = self._sessions.get(capability_id)
        if entry and entry.active:
            entry.last_used = time.time()
            self._diag["capability_resolved"] += 1
            return entry
        self._diag["capability_lookup_failed"] += 1
        return None

    def get_latest_active(self) -> Optional[CapabilityEntry]:
        for entry in reversed(list(self._sessions.values())):
            if entry.active:
                return entry
        return None

    def deactivate(self, capability_id: str) -> bool:
        entry = self._sessions.get(capability_id)
        if entry and entry.active:
            entry.active = False
            self._diag["capability_deactivated"] += 1
            return True
        return False

    def deactivate_by_target(self, canonical_target: str) -> bool:
        key = canonical_target.lower().strip()
        for entry in self._sessions.values():
            if entry.canonical_target == key and entry.active:
                entry.active = False
                self._diag["capability_deactivated"] += 1
                return True
        return False

    def has_active_session(self, canonical_target: str) -> bool:
        return self.resolve_by_target(canonical_target) is not None

    def active_count(self) -> int:
        return sum(1 for e in self._sessions.values() if e.active)

    def _evict_oldest_inactive(self):
        inactive = [(cid, e) for cid, e in self._sessions.items() if not e.active]
        if inactive:
            inactive.sort(key=lambda x: x[1].last_used)
            for cid, _ in inactive[:len(inactive) - _CAPABILITY_LIMIT + self.active_count()]:
                del self._sessions[cid]

    def get_diagnostics(self) -> Dict[str, int]:
        return dict(self._diag)

    def resolve(self, intent_type: "IntentType", action: str) -> Optional[str]:
        """Map IntentType + action to capability name using dynamic registry.
        
        This replaces the hardcoded mapping in _CapabilityResolver.
        """
        from mini_kio.core.pipeline.types import IntentType
        
        # Built-in intent-to-capability mapping (extensible)
        intent_map = {
            IntentType.GREETING: "conversation",
            IntentType.SOCIAL: "conversation",
            IntentType.IDENTITY: "conversation",
            IntentType.DESKTOP_OPEN: "desktop",
            IntentType.DESKTOP_CLOSE: "desktop",
            IntentType.SEARCH: "desktop",
            IntentType.MEDIA_PLAY: "media",
            IntentType.MEDIA_TRANSPORT: "media",
            IntentType.BROWSER_FOCUS: "browser",
            IntentType.BROWSER_TABS: "browser",
            IntentType.BROWSER_NAVIGATE: "browser",
            IntentType.SYSTEM: "system",
            IntentType.OPERATIONAL: "operational",
            IntentType.KNOWLEDGE: "knowledge",
            IntentType.MULTI_STEP: "coordinator",
            IntentType.ENTITY_QUERY: "media",
            IntentType.INFORMATION: "media",
            IntentType.CONVERSATION: "conversation",
            IntentType.FILE: "desktop",
            IntentType.DESKTOP_ACTION: "desktop_action",
            IntentType.MEMORY: "memory",
            IntentType.MCP: "mcp",
            IntentType.CREDENTIAL: "credential",
            IntentType.UTILITY: "utility",
            IntentType.UNKNOWN: "conversation",
        }
        
        # Check for specific action overrides
        action_map = {
            "search_youtube": "media",
            "play_youtube": "media",
        }
        
        if action in action_map:
            return action_map[action]
        
        return intent_map.get(intent_type)


_CAPABILITY_REGISTRY = None


def get_capability_registry() -> CapabilityRegistry:
    global _CAPABILITY_REGISTRY
    if _CAPABILITY_REGISTRY is None:
        _CAPABILITY_REGISTRY = CapabilityRegistry()
        # Auto-wire MCPRuntime if available
        try:
            from mini_kio.core.runtime import get_runtime
            rt = get_runtime()
            if rt is not None and rt.mcp_runtime is not None:
                _CAPABILITY_REGISTRY.set_mcp_runtime(rt.mcp_runtime)
        except Exception:
            pass
    return _CAPABILITY_REGISTRY


def reset_capability_registry():
    global _CAPABILITY_REGISTRY
    _CAPABILITY_REGISTRY = None
