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
            r"^(?:play)\s+(.+)",
            r"^(?:watch)\s+(.+)",
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

    def _is_greeting(self, text: str) -> bool:
        """Detect social/greeting utterances.

        Uses the canonical phrase sets from mini_kio.core.phrases — the single
        source of truth for greeting, acknowledgement, and thanks vocabulary.
        No duplicate phrase lists.
        """
        clean = text.lower().strip().strip(".,!?;: ")
        from mini_kio.core.phrases import GREETINGS, ACKNOWLEDGEMENTS, THANKS
        social = THANKS | {"appreciate it", "bye", "goodbye", "okay", "ok", "sure"}
        return clean in GREETINGS or clean in ACKNOWLEDGEMENTS or clean in social

    def _heuristic_classify(self, text: str) -> IntentClassification:
        text_lower = text.lower().strip()
        
        # Default to conversational
        intent_type = IntentType.CONVERSATIONAL
        action = None
        target = None
        confidence = 0.4
        
        # 0. Social/Greeting — highest priority, never treated as informational
        if self._is_greeting(text_lower):
            intent_type = IntentType.CONVERSATIONAL
            confidence = 0.95
            primary = ExtractedIntent(
                raw_text=text,
                normalized_text=text_lower,
                confidence=confidence,
                intent_type=intent_type,
                proposed_action=action,
                proposed_target=target
            )
            return IntentClassification(primary_intent=primary)
        
        # 1. Check for Math (Deterministic resolution preferred)
        if re.search(r"^\s*[\d\(\)\s\+\-\*\/\%\^\.\*\*]+\s*$", text_lower) and any(op in text_lower for op in "+-*/%^"):
            intent_type = IntentType.MATH
            confidence = 1.0
        elif any(kw in text_lower for kw in ["calculate", "squared", "cube root", "factorial", "square root", "to the power of"]):
            intent_type = IntentType.MATH
            confidence = 0.9

        # 2. Check for Reasoning (Generic detection)
        elif any(kw in text_lower for kw in ["choose one", "must decide", "forced choice", "tradeoff", "pick between", "compare and decide"]):
            intent_type = IntentType.REASONING
            confidence = 0.8

        # 3. Check for System State (Authoritative reality only)
        elif any(kw in text_lower for kw in ["battery percentage", "browser tabs", "running applications", "applications are running", "apps are running", "running apps", "show running", "ram usage", "cpu usage", "memory usage", "what tabs are open", "which tabs are open"]):
            intent_type = IntentType.SYSTEM_STATE
            confidence = 0.9

        # 4. Check for Memory
        elif any(kw in text_lower for kw in ["what did i say", "what was my first", "summarize this session", "what have we talked about"]):
            intent_type = IntentType.MEMORY
            confidence = 0.9

        # 5. Identity detection — REMOVED: the pipeline's _check_identity
        # (using identity_dataset.py) is the canonical identity owner.
        # This secondary classifier should not independently route identity
        # queries, as it duplicates the pipeline's authoritative routing.

        # Deterministic media command patterns — high confidence, skip confirmation
        from mini_kio.core.phrases import MEDIA_TRANSPORT as _PHRASE_MEDIA_TRANSPORT
        _DETERMINISTIC_MEDIA_ACTIONS = {"play", "watch"} | _PHRASE_MEDIA_TRANSPORT

        if intent_type == IntentType.CONVERSATIONAL:
            # Check for executable patterns
            for pattern in self.exec_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    intent_type = IntentType.EXECUTABLE
                    # Simple action extraction from pattern
                    if "open" in pattern or "launch" in pattern: action = "open"
                    elif "search" in pattern or "find" in pattern: action = "search"
                    elif "play" in pattern: action = "play"
                    elif "watch" in pattern: action = "watch"
                    elif "type" in pattern or "write" in pattern: action = "type"
                    elif "click" in pattern or "press" in pattern: action = "click"
                    elif "close" in pattern or "kill" in pattern: action = "close"
                    
                    target = match.group(1).strip()
                    if action in _DETERMINISTIC_MEDIA_ACTIONS:
                        confidence = 0.85
                    else:
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
