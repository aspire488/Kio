import time
import logging
from typing import Optional, Dict, Any
from mini_kio.llm.intent_models import IntentType, IntentClassification
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.core.execution_boundary import execute_action
from mini_kio.core.runtime import get_runtime, SafetyState
from .runtime_contracts import ExecutionClassification, ExecutionAuditMetadata, RuntimeHandoffResult

logger = logging.getLogger(__name__)

class RuntimeHandoff:
    """
    Safe wiring between AI orchestration and deterministic runtime execution.
    Enforces "LLM proposes. Runtime decides." doctrine.

    INTEGRATION ASSERTIONS:
    1. Unvalidated orchestration payloads must never reach runtime dispatch.
    2. Provider degradation blocks executable handoff.
    3. Runtime authority remains absolute via global safety state veto.
    """

    def handle_handoff(self, orchestration: OrchestrationResponse) -> RuntimeHandoffResult:
        """
        Processes an orchestration response and determines if execution is permitted.
        Never executes direct LLM output without validation and gating.
        """
        rt = get_runtime()
        timestamp = time.time()
        
        # 1. Extract intent metadata for audit
        intent_type = orchestration.intent_type
        is_safe = False
        if orchestration.pending_action:
            is_safe = orchestration.pending_action.classification.is_safe
        elif orchestration.state in (OrchestrationState.CONVERSATIONAL, OrchestrationState.CLARIFYING):
            is_safe = True # Implicitly safe for audit if it reached this state without refusal
        
        # Initial Audit Metadata (incomplete until classification)
        audit = ExecutionAuditMetadata(
            intent_origin=str(intent_type),
            validation_state="SAFE" if is_safe else "UNSAFE",
            confirmation_state=str(orchestration.state),
            dispatch_eligibility=False,
            timestamp=timestamp
        )

        # 2. Rejection Rules
        
        # Rule: Malformed payload check
        if orchestration.state == OrchestrationState.DEGRADED:
             return self._reject(ExecutionClassification.DEGRADED_BLOCK, "Provider in degraded state", audit)

        # Rule: Only EXECUTABLE_READY or CONVERSATIONAL/INFORMATIONAL are allowed here
        if orchestration.state == OrchestrationState.AWAITING_CONFIRMATION:
            return self._info(ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION, 
                             "Action requires user confirmation", audit)

        if orchestration.state == OrchestrationState.REFUSED:
            return self._reject(ExecutionClassification.EXECUTABLE_BLOCKED, 
                               orchestration.response_text or "Action refused by orchestrator", audit)

        # Rule: Runtime Veto (Global Safety State)
        if rt and rt.safety_state in (SafetyState.LOCKDOWN, SafetyState.EMERGENCY):
            if orchestration.state == OrchestrationState.EXECUTABLE_READY:
                return self._reject(ExecutionClassification.EXECUTABLE_BLOCKED, 
                                   f"Runtime Veto: System in {rt.safety_state} mode", audit)

        # 3. Execution Dispatch Gating
        
        # Path: Conversational Only
        if orchestration.state == OrchestrationState.CONVERSATIONAL:
            return self._info(ExecutionClassification.CONVERSATIONAL_ONLY, orchestration.response_text, audit)

        # Path: Informational Only
        if orchestration.state == OrchestrationState.CLARIFYING:
            return self._info(ExecutionClassification.INFORMATIONAL_ONLY, orchestration.response_text, audit)

        # Path: Validated Execution
        if orchestration.state == OrchestrationState.EXECUTABLE_READY:
            if not orchestration.pending_action:
                 return self._reject(ExecutionClassification.MALFORMED_PAYLOAD, "Missing pending action", audit)
            
            # THE CRITICAL HANDOFF POINT
            # Only validated structured intents reach here.
            pending = orchestration.pending_action
            
            # Double check safety at the last millisecond
            if not pending.classification.is_safe:
                return self._reject(ExecutionClassification.EXECUTABLE_BLOCKED, "Intent validation failure at handoff", audit)

            # Audit dispatch eligibility
            final_audit = self._update_audit(audit, ExecutionClassification.EXECUTABLE_VALIDATED, True)
            
            # Dispatch to Authoritative Runtime Execution
            try:
                # LLM proposes. Runtime decides.
                result = execute_action(pending.action, pending.target)
                
                return RuntimeHandoffResult(
                    success=result.get("success", False),
                    classification=ExecutionClassification.EXECUTABLE_VALIDATED,
                    message=result.get("message", "Execution complete"),
                    audit_metadata=final_audit,
                    execution_result=result
                )
            except Exception as e:
                return self._reject(ExecutionClassification.EXECUTABLE_BLOCKED, f"Runtime dispatch error: {str(e)}", final_audit)

        return self._reject(ExecutionClassification.MALFORMED_PAYLOAD, "Unknown orchestration state", audit)

    def _reject(self, classification: ExecutionClassification, reason: str, audit: ExecutionAuditMetadata) -> RuntimeHandoffResult:
        final_audit = self._update_audit(audit, classification, False, reason)
        return RuntimeHandoffResult(
            success=False,
            classification=classification,
            message=reason,
            audit_metadata=final_audit
        )

    def _info(self, classification: ExecutionClassification, message: str, audit: ExecutionAuditMetadata) -> RuntimeHandoffResult:
        final_audit = self._update_audit(audit, classification, True)
        return RuntimeHandoffResult(
            success=True,
            classification=classification,
            message=message,
            audit_metadata=final_audit
        )

    def _update_audit(self, audit: ExecutionAuditMetadata, classification: ExecutionClassification, eligible: bool, reason: str = None) -> ExecutionAuditMetadata:
        return ExecutionAuditMetadata(
            intent_origin=audit.intent_origin,
            validation_state=audit.validation_state,
            confirmation_state=audit.confirmation_state,
            dispatch_eligibility=eligible,
            rejection_reason=reason,
            execution_classification=classification,
            timestamp=audit.timestamp
        )

