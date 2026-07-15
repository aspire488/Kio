import enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

# Ponytail: simple definitions, minimal needed for registry.

AdapterState = enum.Enum("AdapterState", "REGISTERED LOADED UNLOADED SHUTDOWN")

@dataclass(frozen=True)
class AdapterInfo:
    """Metadata about an adapter discovered in the adapters package."""
    id: str
    version: str
    capabilities: List[str]
    state: AdapterState = AdapterState.REGISTERED
    module: str = ""

@dataclass
class AdapterHealth:
    """Result of an adapter's health check."""
    id: str
    status: bool
    details: Optional[str] = None

# simple alias types
AdapterCapability = str
AdapterVersion = str