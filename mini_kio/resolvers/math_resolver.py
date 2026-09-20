import re
import ast
import math
import operator
import logging
from typing import Optional
from mini_kio.resolvers.base import BaseResolver
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext

logger = logging.getLogger(__name__)

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    """Evaluate an AST node containing only arithmetic — no function calls, names, or imports."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return _SAFE_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported AST node: {type(node).__name__}")

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
                tree = ast.parse(expr_eval, mode='eval')
                result = _safe_eval(tree)
                return f"{text.strip()} = {result}"

        except Exception as e:
            logger.warning(f"Math resolution failed: {e}")
        
        return None
