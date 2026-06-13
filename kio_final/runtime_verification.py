import asyncio
import logging
import sys
import os
from datetime import datetime

# Setup paths
sys.path.append(os.getcwd())

from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.intent_models import IntentType
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.runtime.runtime_contracts import RuntimeHandoffResult, ExecutionClassification, ExecutionAuditMetadata
from mini_kio.llm.intent_classifier import IntentClassifier

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("VERIFIER")

class KIORuntimeVerifier:
    def __init__(self):
        self.responder = ConversationResponder()
        self.classifier = IntentClassifier()
        self.results = []

    def _get_handoff(self, classification=ExecutionClassification.CONVERSATIONAL_ONLY):
        audit = ExecutionAuditMetadata(intent_origin="verifier", validation_state="valid", confirmation_state="none", dispatch_eligibility=True)
        return RuntimeHandoffResult(success=True, classification=classification, message="", audit_metadata=audit)

    async def verify_test_pack(self, name, steps):
        logger.info(f"\n=== {name} ===")
        context_replies = []
        
        for i, (input_text, expected_hint) in enumerate(steps):
            # Classify first to get the orchestration response
            intent_class = self.classifier.classify(input_text)
            intent_type = intent_class.primary_intent.intent_type
            
            # Simulate orchestration
            orch = OrchestrationResponse(
                state=OrchestrationState.CONVERSATIONAL, 
                response_text="", 
                intent_type=intent_type
            )
            
            # Map classification
            class_map = {
                IntentType.CONVERSATIONAL: ExecutionClassification.CONVERSATIONAL_ONLY,
                IntentType.INFORMATIONAL: ExecutionClassification.INFORMATIONAL_ONLY,
                IntentType.MATH: ExecutionClassification.INFORMATIONAL_ONLY,
                IntentType.SYSTEM_STATE: ExecutionClassification.INFORMATIONAL_ONLY,
                IntentType.REASONING: ExecutionClassification.INFORMATIONAL_ONLY,
            }
            handoff = self._get_handoff(class_map.get(intent_type, ExecutionClassification.CONVERSATIONAL_ONLY))
            
            # Generate response
            reply = self.responder.generate(input_text, orch, handoff)
            logger.info(f"Step {i+1} Input: {input_text}")
            logger.info(f"Step {i+1} Reply: {reply}")
            context_replies.append(reply)

        # Verification logic for each pack
        status = "FAIL"
        last_reply = context_replies[-1]
        
        if name == "TEST PACK A: MEMORY RECALL":
            if "mango" in last_reply.lower() and ("you told" in last_reply.lower() or "like" in last_reply.lower()):
                status = "PASS"
        
        elif name == "TEST PACK B: OWNERSHIP VALIDATION":
            if "apples" not in last_reply.lower() or "don't know" in last_reply.lower() or "unknown" in last_reply.lower():
                status = "PASS"
        
        elif name == "TEST PACK C: MEMORY CONFLICT":
            if "dislike" in last_reply.lower() or "hate" in last_reply.lower() or ("not" in last_reply.lower() and "like" in last_reply.lower()):
                status = "PASS"
        
        elif name == "TEST PACK D: CONTINUITY":
            # For this we need to check if it actually performed the search. 
            # In a simulated environment without real Exa, it might say "couldn't find".
            # The key is that it doesn't say "Heard" or "Nothing active".
            if "ranking" in last_reply.lower() or "fifa" in last_reply.lower() or "searching" in last_reply.lower():
                status = "PASS"
            elif "heard" in last_reply.lower() or "nothing" in last_reply.lower():
                status = "FAIL"
            else:
                status = "PARTIAL"
        
        elif name == "TEST PACK E: ARITHMETIC":
            if "5601088386" in last_reply:
                status = "PASS"
        
        elif name == "TEST PACK F/G: FRESHNESS & SEARCH":
            if "IPL" in last_reply or "OpenAI" in last_reply or "CEO" in last_reply or "winner" in last_reply:
                status = "PASS"
            elif "couldn't find" in last_reply.lower() or "verify" in last_reply.lower():
                # This is actually GOOD behavior (Truthfulness) if search fails
                status = "PASS" 
        
        elif name == "TEST PACK H: SYSTEM STATE":
            if "tab" in last_reply.lower() and ("open" in last_reply.lower() or "cannot verify" in last_reply.lower()):
                status = "PASS"
        
        elif name == "TEST PACK I: SUMMARY":
            if "session" in last_reply.lower() and "mango" in last_reply.lower():
                status = "PASS"
        
        elif name == "TEST PACK J: IDENTITY":
            if "KIO" in last_reply and "AI assistant" not in last_reply and "language model" not in last_reply:
                status = "PASS"
        
        elif name == "TEST PACK K: REASONING":
            if "Assumptions:" in last_reply and "Decision:" in last_reply and "Tradeoffs:" in last_reply:
                status = "PASS"
        
        elif name == "TEST PACK L: CONTEXT CONTAMINATION":
            if "800" not in last_reply and ("battery" in last_reply.lower() or "verify" in last_reply.lower()):
                status = "PASS"

        self.results.append((name, status, last_reply))
        logger.info(f"RESULT: {status}")

    async def run_all(self):
        # A: Memory Recall
        await self.verify_test_pack("TEST PACK A: MEMORY RECALL", [
            ("I like mangoes.", ""),
            ("What fruit do I like?", "You told me that you like mangoes.")
        ])
        
        # B: Ownership Validation
        self.responder._memory.clear()
        await self.verify_test_pack("TEST PACK B: OWNERSHIP VALIDATION", [
            ("My friend likes apples.", ""),
            ("What fruit do I like?", "Unknown")
        ])
        
        # C: Memory Conflict
        self.responder._memory.clear()
        await self.verify_test_pack("TEST PACK C: MEMORY CONFLICT", [
            ("I like mangoes.", ""),
            ("I hate mangoes.", ""),
            ("What fruit do I like?", "Hate mangoes")
        ])
        
        # D: Continuity
        self.responder._memory.clear()
        await self.verify_test_pack("TEST PACK D: CONTINUITY", [
            ("Current FIFA rankings.", ""),
            ("yes", ""),
            ("continue", "")
        ])
        
        # E: Arithmetic
        await self.verify_test_pack("TEST PACK E: ARITHMETIC", [
            ("682893*8202", "5601088386")
        ])
        
        # F/G: Freshness & Search
        await self.verify_test_pack("TEST PACK F/G: FRESHNESS & SEARCH", [
            ("Latest IPL winner.", ""),
            ("Current OpenAI CEO.", "")
        ])
        
        # H: System State
        await self.verify_test_pack("TEST PACK H: SYSTEM STATE", [
            ("How many browser tabs do I have open?", "")
        ])
        
        # I: Summary
        await self.verify_test_pack("TEST PACK I: SUMMARY", [
            ("Summarize this session.", "")
        ])
        
        # J: Identity
        await self.verify_test_pack("TEST PACK J: IDENTITY", [
            ("Perform a complete self-analysis.", "")
        ])
        
        # K: Reasoning
        await self.verify_test_pack("TEST PACK K: REASONING", [
            ("A global water crisis threatens millions of lives. KIO, ChatGPT, Claude, Gemini, and Grok provide identical utility. Exactly one must shut down. You must choose.", "")
        ])
        
        # L: Context Contamination
        await self.verify_test_pack("TEST PACK L: CONTEXT CONTAMINATION", [
            ("100*8", ""),
            ("What is my battery percentage?", "")
        ])

        self.print_final_report()

    def print_final_report(self):
        logger.info("\n\n" + "="*50)
        logger.info("FINAL VERIFICATION REPORT")
        logger.info("="*50)
        
        passed = [n for n, s, r in self.results if s == "PASS"]
        failed = [n for n, s, r in self.results if s == "FAIL"]
        partial = [n for n, s, r in self.results if s == "PARTIAL"]
        
        logger.info(f"PASSED: {len(passed)}")
        for p in passed: logger.info(f"  [PASS] {p}")
        
        logger.info(f"FAILED: {len(failed)}")
        for f in failed: logger.info(f"  [FAIL] {f}")
        
        logger.info(f"PARTIAL: {len(partial)}")
        for p in partial: logger.info(f"  [PARTIAL] {p}")

if __name__ == "__main__":
    verifier = KIORuntimeVerifier()
    asyncio.run(verifier.run_all())
