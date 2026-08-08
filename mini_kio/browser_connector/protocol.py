"""
protocol.py - Browser Connector V1 Protocol

Message types, validation, and serialization for the KIO ? Extension protocol.

Wire format: JSON over WebSocket (RFC 6455)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class MessageType(str, Enum):
    """All message types in the connector protocol."""
    CONNECT = "connect"
    CONNECTED = "connected"
    OPEN_TAB = "open_tab"
    CLOSE_TAB = "close_tab"
    FOCUS_TAB = "focus_tab"
    NAVIGATE_TAB = "navigate_tab"
    LIST_TABS = "list_tabs"
    RESULT = "result"
    TAB_CLOSED = "tab_closed"
    TAB_UPDATED = "tab_updated"
    PING = "ping"
    PONG = "pong"
    EXECUTE_SCRIPT = "execute_script"
    ERROR = "error"


@dataclass
class Message:
    """Base message - all fields optional for flexible validation."""
    type: str
    command_id: Optional[str] = None
    token: Optional[str] = None
    build: Optional[str] = None
    url: Optional[str] = None
    tab_id: Optional[int] = None
    title: Optional[str] = None
    window_id: Optional[int] = None
    success: Optional[bool] = None
    error: Optional[str] = None
    script: Optional[str] = None
    args: Optional[list] = None
    message: Optional[str] = None
    tabs: Optional[list[dict]] = None

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps({k: v for k, v in d.items() if v is not None})

    @classmethod
    def from_json(cls, raw: str) -> "Message":
        d = json.loads(raw)
        return cls(**d)


@dataclass
class OwnedTab:
    """A tab owned by KIO - tracked in TabRegistry."""
    tab_id: int
    url: str
    title: str = ""
    window_id: int = 0
    created_at: float = field(default_factory=lambda: __import__("time").time())
    is_owned: bool = False
    audible: bool = False
    active: bool = False
    last_accessed: float = 0.0

    def to_dict(self) -> dict:
        return {"tab_id": self.tab_id, "url": self.url,
                "title": self.title, "window_id": self.window_id,
                "created_at": self.created_at, "is_owned": self.is_owned,
                "audible": self.audible, "active": self.active,
                "last_accessed": self.last_accessed}

    @classmethod
    def from_dict(cls, d: dict) -> "OwnedTab":
        return cls(
            tab_id=int(d["tab_id"]),
            url=d["url"],
            title=d.get("title", ""),
            window_id=d.get("window_id", 0),
            created_at=d.get("created_at", __import__("time").time()),
            is_owned=d.get("is_owned", False),
            audible=d.get("audible", False),
            active=d.get("active", False),
            last_accessed=d.get("last_accessed", 0.0),
        )


class VerificationCode(str, Enum):
    """Structured outcome of an externally-visible browser action."""
    VERIFIED = "VERIFIED"          # Observable state matches the request
    PARTIAL = "PARTIAL"           # State reached but could not be fully confirmed
    TIMEOUT = "TIMEOUT"           # State never reached before deadline
    FAILED = "FAILED"             # State contradicts the request
    NOT_VERIFIED = "NOT_VERIFIED" # No verification was possible


@dataclass
class TabResult:
    """Result of a tab operation."""
    success: bool
    command_id: str = ""
    tab: Optional[OwnedTab] = None
    tabs: Optional[list[OwnedTab]] = None
    error: str = ""
    message: str = ""
    verification: str = VerificationCode.NOT_VERIFIED.value

    def to_dict(self) -> dict:
        d = {"success": self.success, "command_id": self.command_id,
             "message": self.message, "verification": self.verification}
        if self.tab:
            d["tab"] = self.tab.to_dict()
        if self.tabs is not None:
            d["tabs"] = [t.to_dict() for t in self.tabs]
        if self.error:
            d["error"] = self.error
        return d


def new_command_id() -> str:
    return uuid4().hex[:12]


def validate_connect(msg: Message) -> Optional[str]:
    """Validate connect message. Returns error string or None."""
    if msg.type != MessageType.CONNECT:
        return f"expected 'connect', got '{msg.type}'"
    if not msg.token or not isinstance(msg.token, str):
        return "missing or invalid token"
    if len(msg.token) < 4:
        return "token too short (min 4 chars)"
    return None


def validate_open_tab(msg: Message) -> Optional[str]:
    """Validate open_tab command. Returns error string or None."""
    if msg.type != MessageType.OPEN_TAB:
        return f"expected 'open_tab', got '{msg.type}'"
    if not msg.url or not isinstance(msg.url, str):
        return "missing or invalid url"
    if not msg.url.startswith(("http://", "https://")):
        return "url must start with http:// or https://"
    if len(msg.url) > 2048:
        return "url exceeds 2048 character limit"
    return None


def validate_close_tab(msg: Message) -> Optional[str]:
    """Validate close_tab command. Returns error string or None."""
    if msg.type != MessageType.CLOSE_TAB:
        return f"expected 'close_tab', got '{msg.type}'"
    if msg.tab_id is None or not isinstance(msg.tab_id, int):
        return "missing or invalid tab_id"
    if msg.tab_id < 1:
        return "invalid tab_id (must be positive)"
    return None


def validate_focus_tab(msg: Message) -> Optional[str]:
    """Validate focus_tab command. Returns error string or None."""
    if msg.type != MessageType.FOCUS_TAB:
        return f"expected 'focus_tab', got '{msg.type}'"
    if msg.tab_id is None or not isinstance(msg.tab_id, int):
        return "missing or invalid tab_id"
    if msg.tab_id < 1:
        return "invalid tab_id (must be positive)"
    return None


def validate_navigate_tab(msg: Message) -> Optional[str]:
    """Validate navigate_tab command. Returns error string or None."""
    if msg.type != MessageType.NAVIGATE_TAB:
        return f"expected 'navigate_tab', got '{msg.type}'"
    if msg.tab_id is None or not isinstance(msg.tab_id, int):
        return "missing or invalid tab_id"
    if msg.tab_id < 1:
        return "invalid tab_id (must be positive)"
    if not msg.url or not isinstance(msg.url, str):
        return "missing or invalid url"
    if not msg.url.startswith(("http://", "https://")):
        return "url must start with http:// or https://"
    if len(msg.url) > 2048:
        return "url exceeds 2048 character limit"
    return None


def validate_execute_script(msg: Message) -> Optional[str]:
    """Validate execute_script command. Returns error string or None."""
    if msg.type != MessageType.EXECUTE_SCRIPT:
        return f"expected 'execute_script', got '{msg.type}'"
    if msg.tab_id is None or not isinstance(msg.tab_id, int):
        return "missing or invalid tab_id"
    if msg.tab_id < 1:
        return "invalid tab_id (must be positive)"
    if not msg.script or not isinstance(msg.script, str):
        return "missing or invalid script"
    return None


_COMMAND_VALIDATORS = {
    MessageType.OPEN_TAB: validate_open_tab,
    MessageType.CLOSE_TAB: validate_close_tab,
    MessageType.FOCUS_TAB: validate_focus_tab,
    MessageType.NAVIGATE_TAB: validate_navigate_tab,
    MessageType.EXECUTE_SCRIPT: validate_execute_script,
}


def validate_command(msg: Message) -> Optional[str]:
    """Route to the correct validator based on message type."""
    validator = _COMMAND_VALIDATORS.get(msg.type)
    if validator is None:
        return f"unknown command type: {msg.type}"
    return validator(msg)


def serialize(msg: Message) -> str:
    """Serialize a Message to JSON string."""
    return msg.to_json()


def deserialize(raw: str) -> Message:
    """Deserialize a JSON string to Message.

    Raises ValueError on invalid JSON or structure.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("empty message")
    try:
        return Message.from_json(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"invalid JSON: {e}") from e