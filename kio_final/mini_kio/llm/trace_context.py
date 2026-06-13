from dataclasses import dataclass, field
from typing import Optional, Any, List, Dict
from mini_kio.llm.intent_models import IntentType

@dataclass
class TraceContext:
    """Observability container for tracking execution paths."""
    detected_intent: Optional[IntentType] = None
    selected_resolver: Optional[str] = None
    search_providers_used: List[str] = field(default_factory=list)
    confidence_score: Optional[float] = None
    memory_retrieved: List[str] = field(default_factory=list)
    identity_guard_actions: List[str] = field(default_factory=list)
    execution_path: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: str):
        self.execution_path.append(step)
