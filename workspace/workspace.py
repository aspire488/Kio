from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Protocol


class WorkspaceState(Enum):
    """Possible states of a :class:`Workspace`.

    - ``INITIALIZING`` – The workspace is being set up.
    - ``READY`` – Ready for use.
    - ``BUSY`` – Actively processing work.
    - ``SUSPENDED`` – Temporarily paused.
    - ``CLOSED`` – No longer usable.
    """

    INITIALIZING = auto()
    READY = auto()
    BUSY = auto()
    SUSPENDED = auto()
    CLOSED = auto()


@dataclass
class Workspace:
    """A lightweight description of a workspace.

    Attributes
    ----------
    id: str
        Unique identifier for the workspace.
    name: str
        Human‑readable name.
    state: WorkspaceState
        Current lifecycle state.
    metadata: Dict[str, Any]
        Arbitrary additional information.
    """

    id: str
    name: str
    state: WorkspaceState = WorkspaceState.INITIALIZING
    metadata: Dict[str, Any] = field(default_factory=dict)
