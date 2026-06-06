from typing import Optional, Set
from .intent_models import IntentType, IntentClassification
from .conversation_models import OrchestrationState, OrchestrationResponse, PendingAction


class ConversationOrchestrator:
    """
    Manages controlled conversational flow and execution gating.
    Ensures that LLM intents remain advisory until validated and confirmed.

    INTEGRATION ASSERTIONS:
    1. Conversation layer is advisory only.
    2. Conversational ambiguity never implies execution authority.
    3. Explicit confirmation is mandatory for all high-risk actions.
    """

    DESTRUCTIVE_ACTIONS: Set[str] = {"close", "kill", "terminate", "delete", "shutdown", "restart"}
    
    # Positive confirmation triggers (only valid when in AWAITING_CONFIRMATION state)
    CONFIRMATION_TRIGGERS: Set[str] = {"yes", "confirm", "proceed", "go ahead", "do it", "y"}

    def __init__(self):
        self._state = OrchestrationState.CONVERSATIONAL
        self._pending_action: Optional[PendingAction] = None

    def orchestrate(self, classification: IntentClassification) -> OrchestrationResponse:
        """
        Main entry point for orchestration logic.
        Transforms validated intent into a controlled conversational state.
        """
        primary = classification.primary_intent
        
        # Gate 5: Reset state if a new conversational/educational topic is detected
        # even if we were awaiting confirmation. This prevents confirmation leakage.
        if self._state == OrchestrationState.AWAITING_CONFIRMATION:
            # If the new intent is clearly not a confirmation attempt for the pending action
            if primary.intent_type in (IntentType.CONVERSATIONAL, IntentType.EDUCATIONAL, IntentType.INFORMATIONAL):
                text_lower = primary.normalized_text.strip(".,!?;: ")
                is_confirmation = any(trigger == text_lower for trigger in self.CONFIRMATION_TRIGGERS)
                # If it's not a confirmation, and it's a high-confidence non-executable intent, reset.
                if not is_confirmation and primary.confidence > 0.5:
                    logger.info(f"Topic change detected during confirmation: {primary.intent_type}. Resetting state.")
                    self._reset_state()

        # 1. Handle AWAITING_CONFIRMATION state first
        if self._state == OrchestrationState.AWAITING_CONFIRMATION:
            return self._handle_confirmation_attempt(primary.normalized_text)

        # 2. Refusal path for unsafe intents
        if not classification.is_safe:
            self._reset_state()
            return OrchestrationResponse(
                state=OrchestrationState.REFUSED,
                response_text="I cannot perform that action for safety reasons.",
                intent_type=primary.intent_type,
                errors=primary.validation_errors
            )

        # Gate 5: Preserve educational state and prevent downgrade
        intent_type = primary.intent_type
        if classification.educational_state_preserved and intent_type == IntentType.CONVERSATIONAL:
            # This is a potential downgrade. In Gate 5, we keep it as educational
            # if we are in an active lesson and the input is conversational.
            # However, IntentClassifier already did its job.
            # We just ensure the response layer knows about it.
            pass

        # 3. Routing based on intent type
        if intent_type == IntentType.CONVERSATIONAL or intent_type == IntentType.INFORMATIONAL or intent_type == IntentType.EDUCATIONAL:
            self._reset_state()
            return OrchestrationResponse(
                state=OrchestrationState.CONVERSATIONAL,
                response_text=primary.raw_text, # In real impl, this would be the LLM's conversational output
                intent_type=intent_type,
                metadata={
                    "educational_state_preserved": classification.educational_state_preserved,
                    "continuity_resume_used": classification.continuity_resume_used,
                    "authority_override_used": classification.authority_override_used,
                    "sanitize_applied": classification.sanitize_applied,
                    "emoji_sanitize_applied": classification.emoji_sanitize_applied,
                    "typo_normalization_applied": classification.typo_normalization_applied,
                    "intent_downgrade_blocked": classification.intent_downgrade_blocked,
                    "browser_canonicalization_used": classification.browser_canonicalization_used
                }
            )

        if primary.intent_type == IntentType.EXECUTABLE:
            return self._handle_executable_intent(classification)

        # Default fallback
        self._reset_state()
        return OrchestrationResponse(
            state=OrchestrationState.CONVERSATIONAL,
            response_text="I'm not sure how to help with that. Could you clarify?",
            intent_type=primary.intent_type
        )

    def _handle_executable_intent(self, classification: IntentClassification) -> OrchestrationResponse:
        primary = classification.primary_intent
        action = primary.proposed_action or ""
        target = primary.proposed_target or ""
        
        # Check confirmation requirements
        requires_conf, reason = self._check_confirmation_required(action, target, primary.confidence)
        
        pending = PendingAction(
            action=action,
            target=target,
            classification=classification,
            requires_confirmation=requires_conf,
            reason=reason
        )

        if requires_conf:
            self._state = OrchestrationState.AWAITING_CONFIRMATION
            self._pending_action = pending
            return OrchestrationResponse(
                state=OrchestrationState.AWAITING_CONFIRMATION,
                response_text=f"I'm ready to {action} {target}. Shall I proceed?",
                intent_type=IntentType.EXECUTABLE,
                pending_action=pending,
                metadata={"confirmation_reason": reason}
            )
        
        # Ready for immediate handoff (though Gate 3F will handle actual wiring)
        self._state = OrchestrationState.EXECUTABLE_READY
        self._pending_action = pending
        return OrchestrationResponse(
            state=OrchestrationState.EXECUTABLE_READY,
            response_text=f"Executing {action} {target}...",
            intent_type=IntentType.EXECUTABLE,
            pending_action=pending
        )

    def _handle_confirmation_attempt(self, text: str) -> OrchestrationResponse:
        # Strict confirmation check
        if any(trigger == text.lower().strip() for trigger in self.CONFIRMATION_TRIGGERS):
            pending = self._pending_action
            self._state = OrchestrationState.EXECUTABLE_READY
            return OrchestrationResponse(
                state=OrchestrationState.EXECUTABLE_READY,
                response_text=f"Confirmed. Proceeding with {pending.action} {pending.target}.",
                intent_type=IntentType.EXECUTABLE,
                pending_action=pending
            )
        
        # Anything else is a rejection or non-confirmation
        action_name = self._pending_action.action if self._pending_action else "action"
        self._reset_state()
        return OrchestrationResponse(
            state=OrchestrationState.REFUSED,
            response_text=f"Action '{action_name}' cancelled or not confirmed.",
            intent_type=IntentType.EXECUTABLE if self._pending_action else IntentType.CONVERSATIONAL
        )

    def _check_confirmation_required(self, action: str, target: str, confidence: float) -> tuple[bool, str | None]:
        # Rule 1: Low confidence
        if confidence < 0.8:
            return True, "Low intent confidence"
        
        # Rule 2: Destructive actions
        if action.lower() in self.DESTRUCTIVE_ACTIONS:
            return True, "Potentially destructive action"
        
        # Rule 3: Multi-step/Ambiguous (Handled by validator usually, but double checked here)
        if " and " in target or "," in target:
            return True, "Complex or multi-target action"

        return False, None

    def _reset_state(self):
        self._state = OrchestrationState.CONVERSATIONAL
        self._pending_action = None
        
    def get_state(self) -> OrchestrationState:
        return self._state
