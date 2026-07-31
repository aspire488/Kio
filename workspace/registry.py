"""Workspace Registry

Simple in-memory registry for Workspace objects used by the OpenWork adapter.
"""

from typing import Dict, List

from .workspace import Workspace

_workspaces: Dict[str, Workspace] = {}

def register_workspace(ws: Workspace) -> None:
    """Add or replace a workspace in the registry."""
    _workspaces[ws.id] = ws

def get_workspace(ws_id: str) -> Workspace | None:
    """Retrieve a workspace by its ID."""
    return _workspaces.get(ws_id)

def list_workspaces() -> List[Workspace]:
    """Return a list of all registered workspaces."""
    return list(_workspaces.values())

def clear_registry() -> None:
    """Remove all workspaces – primarily for testing/reset purposes."""
    _workspaces.clear()
