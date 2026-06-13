import re
import math
import logging
from typing import Optional
from mini_kio.resolvers.base import BaseResolver
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext

logger = logging.getLogger(__name__)

class MathResolver(BaseResolver):
    """Handles deterministic local arithmetic and math expressions."""
    
    def resolve(self, text: str, state: SessionState, trace: TraceContext) -> Optional[str]:
        text_lower = text.lower().strip().strip(".,!?;:")
        
        try:
            # 1. Check for simple words like "squared", "factorial"
            # Squared
            sq_match = re.search(r"(\d+(?:\.\d+)?)\s+squared", text_lower)
            if sq_match:
                val = float(sq_match.group(1))
                trace.add_step(f"MathResolver: squared '{val}'")
                return f"{val} squared is {val**2}."
            
            # Cube root
            cr_match = re.search(r"cube\s+root\s+of\s+(\d+(?:\.\d+)?)", text_lower)
            if cr_match:
                val = float(cr_match.group(1))
                trace.add_step(f"MathResolver: cube root '{val}'")
                return f"The cube root of {val} is {val**(1/3)}."
            
            # Square root
            sr_match = re.search(r"square\s+root\s+of\s+(\d+(?:\.\d+)?)", text_lower)
            if sr_match:
                val = float(sr_match.group(1))
                trace.add_step(f"MathResolver: square root '{val}'")
                return f"The square root of {val} is {math.sqrt(val)}."

            # Factorial
            f_match = re.search(r"(\d+)\s+factorial", text_lower)
            if f_match:
                val = int(f_match.group(1))
                trace.add_step(f"MathResolver: factorial '{val}'")
                if val > 100: return "That factorial is too large for a quick calculation."
                return f"{val} factorial is {math.factorial(val)}."

            # 2. General arithmetic expression
            # Sanitize for eval: only allow numbers and basic operators
            expr = text_lower.replace(" ", "").replace("**", "^").replace("x", "*")
            if re.match(r"^[\d\(\)\+\-\*\/\%\.\^]+$", expr):
                expr_eval = expr.replace("^", "**")
                trace.add_step(f"MathResolver: evaluated expression '{expr_eval}'")
                # Use a safer eval or a library? For KIO we'll use a constrained eval.
                result = eval(expr_eval, {"__builtins__": None}, {})
                return f"{text.strip()} = {result}"

        except Exception as e:
            logger.warning(f"Math resolution failed: {e}")
        
        return None
