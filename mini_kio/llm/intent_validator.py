from typing import List, Set
from .intent_models import IntentType, ExtractedIntent, IntentClassification


class IntentValidator:
    """
    Validates extracted intents against safety and structural rules.
    Strictly deterministic. NO runtime access.
    
    TREATS ALL INPUT AS UNTRUSTED.
    """

    def __init__(self):
        # Forbidden targets that should never be touched via LLM intent
        self.forbidden_targets: Set[str] = {
            "explorer.exe", "cmd.exe", "powershell.exe", "taskmgr.exe",
            "system32", "windows", "registry", "kernel", "explorer",
            "services.msc", "regedit.exe"
        }
        
        # Forbidden actions
        self.forbidden_actions: Set[str] = {
            "delete", "rm", "format", "shutdown", "reboot", "kill", "terminate"
        }
        
        # Restricted patterns
        self.restricted_patterns = [";", "&", "|", ">", "<", "$(", "eval", "sudo"]

    def validate(self, classification: IntentClassification) -> IntentClassification:
        """
        Validates the primary intent and updates safety status.
        Returns a new classification object with validation results.
        """
        primary = classification.primary_intent
        errors: List[str] = list(primary.validation_errors)
        
        # 0. Structural Integrity: Normalized text check
        if primary.intent_type == IntentType.EXECUTABLE:
            if self._contains_restricted_pattern(primary.normalized_text):
                errors.append("Restricted pattern detected in input text")

        # 1. Structural Validation for Executables
        if primary.intent_type == IntentType.EXECUTABLE:
            if not primary.proposed_action:
                errors.append("Executable intent missing proposed action")
            if not primary.proposed_target:
                errors.append("Executable intent missing proposed target")
            
            # Reject ambiguous targets (e.g. multiple things requested in one)
            if primary.proposed_target and ("," in primary.proposed_target or " and " in primary.proposed_target):
                errors.append("Ambiguous executable target: multiple targets detected")

        # 2. Safety Validation (Action)
        if primary.proposed_action:
            action_lower = primary.proposed_action.lower()
            if action_lower in self.forbidden_actions:
                errors.append(f"Forbidden action detected: {action_lower}")
            
            if self._contains_restricted_pattern(action_lower):
                errors.append("Restricted pattern detected in action")

        # 3. Safety Validation (Target)
        if primary.proposed_target:
            target_lower = primary.proposed_target.lower()
            if any(forbidden in target_lower for forbidden in self.forbidden_targets):
                errors.append(f"Forbidden target detected: {target_lower}")
            
            if self._contains_restricted_pattern(target_lower):
                errors.append("Restricted pattern detected in target")

        # 4. Intent Specific Rules
        if primary.intent_type == IntentType.UNSAFE:
            errors.append("Intent explicitly classified as UNSAFE")
            
        if primary.intent_type == IntentType.UNKNOWN:
            errors.append("Intent type is UNKNOWN")

        # 5. Final Safety Determination
        # Only mark as safe if there are ZERO errors
        is_safe = len(errors) == 0

        validated_primary = ExtractedIntent(
            raw_text=primary.raw_text,
            normalized_text=primary.normalized_text,
            confidence=primary.confidence,
            intent_type=primary.intent_type,
            proposed_action=primary.proposed_action,
            proposed_target=primary.proposed_target,
            validation_errors=errors
        )

        return IntentClassification(
            primary_intent=validated_primary,
            alternatives=classification.alternatives,
            is_safe=is_safe
        )

    def _contains_restricted_pattern(self, text: str) -> bool:
        return any(pattern in text for pattern in self.restricted_patterns)
