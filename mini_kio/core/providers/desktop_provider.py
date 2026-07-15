"""DesktopProvider — unified desktop automation under ExecutionProvider contract.

Wraps app_operator (app launch/close/search) + mini_kio.desktop
(window management, mouse, keyboard, clipboard, notifications, screen).
Also emits structured observations to AURA.
"""

from __future__ import annotations

import logging
from typing import Any

from mini_kio.core.provider_contract import (
    ExecutionProvider, ProviderHealth, ProviderCapability,
)
from mini_kio.core.app_operator import (
    launch_app, close_app, search_web, APP_OPERATOR_DESCRIPTOR,
)
from mini_kio.core.browser_operator import open_url as br_open_url
from mini_kio.desktop import DesktopProvider as RichDesktopProvider
from mini_kio.execution.observations import get_observation_stream

logger = logging.getLogger(__name__)
_DESC = APP_OPERATOR_DESCRIPTOR


_APP_ACTIONS = frozenset({"open_app", "close_app", "search_web", "execute_capability"})
_RICH_ACTIONS = frozenset({
    "window_list", "window_focus",
    "mouse_move", "mouse_click", "mouse_double_click", "mouse_drag",
    "mouse_scroll", "mouse_position",
    "keyboard_type", "keyboard_press", "keyboard_hotkey",
    "clipboard_get", "clipboard_set",
    "notification_send",
    "screen_size", "screen_monitors", "screen_screenshot",
})


class DesktopProvider(ExecutionProvider):
    def __init__(self) -> None:
        self._rich = RichDesktopProvider()

    def id(self) -> str:
        return "desktop"

    def capabilities(self) -> list[ProviderCapability]:
        caps = [
            ProviderCapability(name="open_app", category="external_open",
                               timeout_s=_DESC.get("timeout_seconds", 15), ram_budget_mb=12),
            ProviderCapability(name="close_app", category="external_control",
                               timeout_s=_DESC.get("timeout_seconds", 15), ram_budget_mb=12),
            ProviderCapability(name="search_web", category="external_open",
                               timeout_s=_DESC.get("timeout_seconds", 15), ram_budget_mb=12),
            ProviderCapability(name="execute_capability", category="external_control",
                               timeout_s=_DESC.get("timeout_seconds", 15), ram_budget_mb=12),
        ]
        for action in sorted(_RICH_ACTIONS):
            caps.append(ProviderCapability(name=action, category="desktop_action", ram_budget_mb=6))
        return caps

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]:
        obs = get_observation_stream()
        if action in _RICH_ACTIONS:
            result = self._rich.execute(action, target, **kwargs)
            obs.desktop_action(action, result)
            return result
        if action == "open_app":
            pid = kwargs.get("pid")
            result = dict(launch_app(target))
            obs.execution(result)
            return result
        elif action == "close_app":
            pid = kwargs.get("pid")
            result = dict(close_app(target, pid=pid))
            obs.execution(result)
            return result
        elif action == "search_web":
            result = dict(search_web(target))
            obs.execution(result)
            return result
        elif action == "execute_capability":
            result = dict(br_open_url(target))
            obs.execution(result)
            return result
        result = {"success": False, "message": f"DesktopProvider: unknown action {action}"}
        obs.execution(result)
        return result

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "desktop_action")
        if result.get("success"):
            result.setdefault("verification_status", "passed")
            result.setdefault("outcome_class", "SUCCESS")
        else:
            result.setdefault("verification_status", "failed")
            result.setdefault("outcome_class", "FAILURE")
        return result
