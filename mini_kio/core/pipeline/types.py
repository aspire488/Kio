from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional


class IntentType(enum.Enum):
    UNKNOWN = "unknown"
    GREETING = "greeting"
    SOCIAL = "social"
    IDENTITY = "identity"
    DESKTOP_OPEN = "desktop_open"
    DESKTOP_CLOSE = "desktop_close"
    SEARCH = "search"
    MEDIA_PLAY = "media_play"
    MEDIA_TRANSPORT = "media_transport"
    BROWSER_FOCUS = "browser_focus"
    BROWSER_TABS = "browser_tabs"
    BROWSER_NAVIGATE = "browser_navigate"
    SYSTEM = "system"
    OPERATIONAL = "operational"
    CONVERSATION = "conversation"
    KNOWLEDGE = "knowledge"
    MULTI_STEP = "multi_step"
    ENTITY_QUERY = "entity_query"
    INFORMATION = "information"
    MEMORY = "memory"
    FILE = "file"
    MCP = "mcp"
    CREDENTIAL = "credential"


@dataclass
class RoutingDecision:
    intent_type: IntentType
    action: str
    target: str
    raw_text: str
    normalized_text: str
    confidence: float = 1.0
    entity: Optional[str] = None
    platform: Optional[str] = None
    session_id: str = "local_0"
    channel: str = "unknown"
    user_id: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionContext:
    session_id: str
    channel: str
    user_id: int
    decision: RoutingDecision
    request_id: str = ""
