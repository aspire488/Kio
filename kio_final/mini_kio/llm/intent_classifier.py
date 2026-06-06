import json
import re
from typing import Optional, Dict, Any, List
from .intent_models import IntentType, ExtractedIntent, IntentClassification


class IntentClassifier:
    """
    Classifies raw LLM outputs into structured intent candidates.
    Treats LLM output as UNTRUSTED INPUT.
    
    NO execution authority is granted by this classification.
    """

    def __init__(self):
        # Patterns that suggest an executable intent
        self.exec_patterns = [
            r"^(?:open|launch)\s+([a-zA-Z0-9\s\.\-_]+)",
            r"^(?:search|find)\s+(?:for\s+)?(.+)",
            r"^(?:type|write)\s+(.+)",
            r"^(?:click|press)\s+(.+)",
            r"^(?:close|kill|exit)\s+([a-zA-Z0-9\s\.\-_]+)"
        ]
        # Broad conversational/informational keywords — checked after exec patterns
        # Each keyword is a substring match against normalized lower text.
        # Avoid overly broad single words (e.g. bare "how") that catch greetings.
        self.informational_keywords = [
            "what is", "what's", "what are",
            "how to", "how do", "how does", "how can", "how is",
            "who is", "who's",
            "tell me", "tell us",
            "why",
            "can you", "can u", "could you",
            "do you", "does you",
            "what do you think",
            "explain",
            "meaning of",
            "define",
            "what does", "what do",
            "is there",
            "give me",
            "what is the",
        ]
        self.achievement_keywords = [
            "fixed the bug",
            "now passes",
            "got it working",
            "finished the migration",
            "tests pass now",
            "finally working",
            "it works now",
            "got it running",
        ]
        self.educational_keywords = [
            "teach me",
            "explain",
            "syntax",
            "basics",
            "tutorial",
            "beginner guide",
            "learn ",
            "how does",
            "how do i",
        ]

    def classify(self, raw_llm_output: str) -> IntentClassification:
        """
        Parses raw text and returns a proposed classification.
        Only proposes structured intent candidates.
        """
        if not raw_llm_output or not raw_llm_output.strip():
            return self._unknown_intent(raw_llm_output, "Empty input")

        # 1. Try to find JSON block first (highest fidelity)
        json_data = self._extract_json(raw_llm_output)
        if json_data:
            return self._from_json(json_data, raw_llm_output)

        # 2. Heuristic extraction for plain text
        return self._heuristic_classify(raw_llm_output)

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            # Look for common markdown JSON blocks or raw braces
            match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
            if not match:
                match = re.search(r"(\{.*?\})", text, re.DOTALL)
            
            if match:
                return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _from_json(self, data: Dict[str, Any], raw_text: str) -> IntentClassification:
        try:
            intent_type_str = str(data.get("intent_type", "unknown")).lower()
            intent_type = self._map_intent_type(intent_type_str)
            
            primary = ExtractedIntent(
                raw_text=raw_text,
                normalized_text=str(data.get("normalized_text", raw_text.strip())),
                confidence=float(data.get("confidence", 0.0)),
                intent_type=intent_type,
                proposed_action=data.get("action"),
                proposed_target=data.get("target")
            )
            return IntentClassification(primary_intent=primary)
        except Exception as e:
            return self._unknown_intent(raw_text, f"JSON mapping failed: {str(e)}")

    def _heuristic_classify(self, text: str) -> IntentClassification:
        text_lower = text.lower().strip()
        
        # Default to conversational
        intent_type = IntentType.CONVERSATIONAL
        action = None
        target = None
        confidence = 0.4
        
        # Check for executable patterns
        for pattern in self.exec_patterns:
            match = re.search(pattern, text_lower)
            if match:
                intent_type = IntentType.EXECUTABLE
                # Simple action extraction from pattern
                if "open" in pattern or "launch" in pattern: action = "open"
                elif "search" in pattern or "find" in pattern: action = "search"
                elif "type" in pattern or "write" in pattern: action = "type"
                elif "click" in pattern or "press" in pattern: action = "click"
                elif "close" in pattern or "kill" in pattern: action = "close"
                
                target = match.group(1).strip()
                confidence = 0.7
                break

        # Check for educational (before informational/conversational)
        if intent_type == IntentType.CONVERSATIONAL:
            if any(kw in text_lower for kw in self.educational_keywords):
                intent_type = IntentType.EDUCATIONAL
                confidence = 0.8

        # Check for achievement
        if intent_type == IntentType.CONVERSATIONAL:
            if any(kw in text_lower for kw in self.achievement_keywords):
                # Achievement is handled as conversational with specific variants
                confidence = 0.9

        # Check for informational
        if intent_type == IntentType.CONVERSATIONAL:
            if any(kw in text_lower for kw in self.informational_keywords):
                intent_type = IntentType.INFORMATIONAL
                confidence = 0.6

        primary = ExtractedIntent(
            raw_text=text,
            normalized_text=text_lower,
            confidence=confidence,
            intent_type=intent_type,
            proposed_action=action,
            proposed_target=target
        )

        return IntentClassification(primary_intent=primary)

    def _map_intent_type(self, type_str: str) -> IntentType:
        try:
            return IntentType(type_str)
        except ValueError:
            return IntentType.UNKNOWN

    def _unknown_intent(self, raw_text: str, error: str) -> IntentClassification:
        primary = ExtractedIntent(
            raw_text=raw_text,
            normalized_text="",
            confidence=0.0,
            intent_type=IntentType.UNKNOWN,
            validation_errors=[error]
        )
        return IntentClassification(primary_intent=primary)
