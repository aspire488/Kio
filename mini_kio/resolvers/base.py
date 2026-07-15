from abc import ABC, abstractmethod
from typing import Optional
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext

class BaseResolver(ABC):
    """Abstract base class for all KIO resolvers."""
    
    @abstractmethod
    def resolve(self, text: str, state: SessionState, trace: TraceContext) -> Optional[str]:
        """
        Attempt to resolve the user request.
        
        Returns:
            A string response if resolved, or None if the resolver cannot handle it.
        """
        pass
