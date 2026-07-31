from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InterfaceRequest:
    text: str
    channel: str = "terminal"
    user_id: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InterfaceResponse:
    success: bool = False
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
