"""Profiles placeholder for BrowserFacade.
"""

from __future__ import annotations

def list_profiles() -> list[str]:
    return []

def create_profile(name: str) -> bool:
    return False

__all__ = ["list_profiles", "create_profile"]
