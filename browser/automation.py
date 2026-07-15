"""Automation utilities for BrowserFacade.

Provides thin wrappers around browser_operator scripting actions.
"""

from __future__ import annotations

from mini_kio.core import browser_operator as bo

def evaluate(script: str, arg: Any | None = None) -> dict:
    payload = {"expression": script}
    if arg is not None:
        payload["arg"] = arg
    import json
    return bo.browser_evaluate(json.dumps(payload))

def fill(selector: str, value: str) -> dict:
    payload = {"selector": selector, "value": value}
    import json
    return bo.browser_fill(json.dumps(payload))

__all__ = ["evaluate", "fill"]
