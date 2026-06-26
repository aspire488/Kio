from typing import Optional
from mini_kio.resolvers.base import BaseResolver
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext
from mini_kio.llm.llm_ops import ask_llm_sync

class ReasoningResolver(BaseResolver):
    """Handles structured reasoning for dilemmas and tradeoffs."""
    
    def resolve(self, text: str, state: SessionState, trace: TraceContext) -> Optional[str]:
        system_prompt = (
            "You are in Structured Reasoning Mode. "
            "You must provide a balanced analysis following this EXACT format:\n"
            "1. Assumptions: [list]\n"
            "2. Known Facts: [list]\n"
            "3. Unknowns: [list]\n"
            "4. Constraints: [list]\n"
            "5. Decision: [direct choice or recommendation]\n"
            "6. Reasoning: [explanation]\n"
            "7. Tradeoffs: [consequences of the choice]\n\n"
            "Do not use conversational filler. Be analytical and objective."
        )
        
        trace.add_step("ReasoningResolver: initiating structured reasoning")
        
        reply = ask_llm_sync(text, system_prompt=system_prompt, task_type="reasoning")
        return reply
