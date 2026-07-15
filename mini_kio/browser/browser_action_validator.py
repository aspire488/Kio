"""
browser_action_validator.py — Browser Security Gating

Validates browser actions against safety policies.
"""

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

class ActionSeverity(Enum):
    READ = "READ"
    WRITE = "WRITE"
    DESTRUCTIVE_TAB = "DESTRUCTIVE_TAB"
    DESTRUCTIVE_WINDOW = "DESTRUCTIVE_WINDOW"

class BrowserActionValidator:
    """Validation layer for browser operations."""

    def __init__(self, tab_controller):
        self._tab_controller = tab_controller
        self._diag = {
            "destructive_action_blocked": 0
        }

    def validate_action(self, action_type: str, target_tab_id: Optional[str] = None) -> bool:
        """
        Validate if an action is safe to perform.
        Destructive actions are only allowed on KIO-owned tabs.
        """
        severity = self._classify_action(action_type)
        
        if severity in (ActionSeverity.DESTRUCTIVE_TAB, ActionSeverity.DESTRUCTIVE_WINDOW):
            if not target_tab_id:
                # Bulk destructive action on unknown targets
                self._diag["destructive_action_blocked"] += 1
                logger.warning(f"Blocked bulk destructive action: {action_type}")
                return False
            
            if not self._tab_controller.is_owned(target_tab_id):
                self._diag["destructive_action_blocked"] += 1
                logger.warning(f"Blocked destructive action on unowned tab {target_tab_id}: {action_type}")
                return False
        
        return True

    def _classify_action(self, action_type: str) -> ActionSeverity:
        """Classify action by destructive potential."""
        action_type = action_type.lower()
        if "close" in action_type:
            if "window" in action_type or "browser" in action_type:
                return ActionSeverity.DESTRUCTIVE_WINDOW
            return ActionSeverity.DESTRUCTIVE_TAB
        if "delete" in action_type or "remove" in action_type or "clear" in action_type:
            return ActionSeverity.DESTRUCTIVE_TAB
        if "write" in action_type or "input" in action_type or "click" in action_type:
            return ActionSeverity.WRITE
        return ActionSeverity.READ

    def get_diagnostics(self) -> dict:
        return dict(self._diag)
