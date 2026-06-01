"""
response_governor.py — Gate 5E Finalization Unified Response Authority Pipeline

Pipeline:
1. Identity guard (canonical truth enforcement)
2. Tone normalization (cringe/emotion clamping)
3. Conversational Coherence Validation
4. Provider unavailable → check educational first, else offline fallback
5. Low-information input → micro-response
6. Semantic quality scoring
7. Knowledge fallback (if quality rejected + educational topic)
8. Anti-generic filter
9. Repetition suppression (fallback only)
10. Record + diagnostics

Applied ONLY to conversational output — execution paths untouched.
"""

import logging
from typing import Optional
from mini_kio.llm.identity_guard import IdentityGuard
from mini_kio.llm.tone_normalizer import ToneNormalizer
from mini_kio.llm.fallback_manager import FallbackManager
from mini_kio.llm.semantic_quality import SemanticQualityScorer, ResponseSemanticQuality
from mini_kio.llm.knowledge_fallback import KnowledgeFallback

logger = logging.getLogger(__name__)


class ResponseGovernor:
    """Unified response authority pipeline for conversational output.

    No bypass paths — ALL conversational responses pass through.
    """

    def __init__(self):
        self._identity_guard = IdentityGuard()
        self._tone_normalizer = ToneNormalizer()
        self._fallback_manager = FallbackManager()
        self._quality_scorer = SemanticQualityScorer()
        self._knowledge_fallback = KnowledgeFallback()
        self._diag: dict[str, int] = {
            "semantic_quality_rejected": 0,
            "low_information_blocked": 0,
            "educational_fallback_used": 0,
            "coherence_rewrite": 0,
            "repeated_response_blocked": 0,
            "semantic_normalization_applied": 0,
            "semantic_fallback_used": 0,
        }

    def is_idle_response(self, text: str) -> bool:
        lower = text.lower().strip().strip(".,!?;:")
        idle_phrases = {
            "i'm here", "what do you need", "got it", "what's up",
            "alright. let me know", "sounds good", "fair enough",
            "okay", "ok", "sure", "running smoothly", "ready",
            "standing by", "online", "awaiting input", "go ahead"
        }
        return lower in idle_phrases

    def is_question(self, text: str) -> bool:
        lower = text.lower().strip()
        return lower.endswith("?") or any(w in lower for w in ["what", "how", "why", "who", "where", "when", "which"])

    def check_coherence_mismatch(self, response: str, user_text: str) -> bool:
        user_lower = user_text.lower().strip()
        resp_lower = response.lower().strip()
        
        # 1. Educational prompt -> idle response
        if self._knowledge_fallback.is_educational_request(user_text) and self.is_idle_response(response):
            return True
            
        # 2. Question -> unrelated response (idle / dead end response)
        if self.is_question(user_text) and self.is_idle_response(response):
            return True
            
        # 3. Continuity request -> topic reset (non-educational response or generic filler response)
        if self._knowledge_fallback.is_continuation_request(user_text) and self.is_idle_response(response):
            return True
            
        # 4. Obvious semantic mismatch: educational request but response has no relevance
        if self._knowledge_fallback.is_educational_request(user_text):
            topic = self._knowledge_fallback.detect_topic(user_text)
            if topic and topic != "kio" and topic not in resp_lower:
                return True
                
        return False

    def govern(
        self,
        response: str,
        user_text: str,
        is_fallback: bool = False,
        provider_unavailable: bool = False,
    ) -> str:
        if not response or not response.strip():
            return response

        is_knowledge_request = self._knowledge_fallback.is_knowledge_request(user_text)
        is_educational_request = self._knowledge_fallback.is_educational_request(user_text)

        def _educational_failure() -> str:
            failure = self._knowledge_fallback.get_knowledge_failure(user_text)
            self._fallback_manager.record(failure)
            self._diag["semantic_fallback_used"] += 1
            return failure

        # Step 1: Identity enforcement (highest priority)
        governed, violations = self._identity_guard.check_and_rewrite(
            response, user_text
        )
        if violations:
            self._fallback_manager.record(governed)
            return governed

        # Step 2: Tone normalization
        governed = self._tone_normalizer.normalize(response)

        # Step 2.5: Conversational Coherence Validation
        if self.check_coherence_mismatch(governed, user_text):
            edu = None
            if is_educational_request:
                edu = self._knowledge_fallback.get_fallback(user_text)
            elif self._knowledge_fallback.is_continuation_request(user_text):
                edu = self._knowledge_fallback.get_continuation(user_text)
            
            if edu:
                self._fallback_manager.record(edu)
                self._diag["coherence_rewrite"] += 1
                self._diag["semantic_fallback_used"] += 1
                return edu
            if is_knowledge_request:
                failure = self._knowledge_fallback.get_knowledge_failure(user_text)
                self._fallback_manager.record(failure)
                self._diag["coherence_rewrite"] += 1
                self._diag["semantic_fallback_used"] += 1
                return failure
            if is_educational_request:
                self._diag["coherence_rewrite"] += 1
                return _educational_failure()

        # Step 3: Provider unavailable → check educational first, else offline fallback
        if provider_unavailable and not is_fallback:
            if is_educational_request:
                edu = self._knowledge_fallback.get_fallback(user_text)
                if edu:
                    self._fallback_manager.record(edu)
                    self._diag["educational_fallback_used"] += 1
                    self._diag["semantic_fallback_used"] += 1
                    return edu
            if is_educational_request:
                return _educational_failure()
            if is_knowledge_request:
                failure = self._knowledge_fallback.get_knowledge_failure(user_text)
                self._fallback_manager.record(failure)
                self._diag["semantic_fallback_used"] += 1
                return failure
            offline = self._fallback_manager.get_offline_fallback()
            self._fallback_manager.record(offline)
            self._diag["semantic_fallback_used"] += 1
            return offline

        # Step 4: Low-information input → micro-response
        if self._fallback_manager.is_low_information(user_text):
            micro = self._fallback_manager.get_micro_response()
            self._fallback_manager.record(micro)
            self._diag["low_information_blocked"] += 1
            self._diag["semantic_fallback_used"] += 1
            return micro

        # Step 5: Semantic quality scoring
        quality = self._quality_scorer.score(governed, user_text)

        # Step 6: Knowledge fallback (if quality rejected + educational topic)
        if quality in (ResponseSemanticQuality.GENERIC, ResponseSemanticQuality.WEAK,
                       ResponseSemanticQuality.EMPTY):
            if is_educational_request:
                edu = self._knowledge_fallback.get_fallback(user_text)
                if edu:
                    self._fallback_manager.record(edu)
                    self._diag["educational_fallback_used"] += 1
                    self._diag["semantic_fallback_used"] += 1
                    return edu
            if is_educational_request:
                return _educational_failure()
            if is_knowledge_request:
                failure = self._knowledge_fallback.get_knowledge_failure(user_text)
                self._fallback_manager.record(failure)
                self._diag["semantic_fallback_used"] += 1
                return failure
            self._diag["semantic_quality_rejected"] += 1

        # Step 7: Anti-generic filter (last chance before outbound)
        if self._quality_scorer.is_generic(governed) or self._quality_scorer.is_filler(governed):
            if is_educational_request:
                edu = self._knowledge_fallback.get_fallback(user_text)
                if edu:
                    self._fallback_manager.record(edu)
                    self._diag["repeated_response_blocked"] += 1
                    self._diag["semantic_fallback_used"] += 1
                    return edu
            if is_educational_request:
                self._diag["repeated_response_blocked"] += 1
                return _educational_failure()
            if is_knowledge_request:
                failure = self._knowledge_fallback.get_knowledge_failure(user_text)
                self._fallback_manager.record(failure)
                self._diag["repeated_response_blocked"] += 1
                self._diag["semantic_fallback_used"] += 1
                return failure
            diversified = self._fallback_manager.get_fallback()
            self._fallback_manager.record(diversified)
            self._diag["repeated_response_blocked"] += 1
            self._diag["semantic_fallback_used"] += 1
            return diversified

        # Step 8: Repetition suppression (fallback only)
        if is_fallback and self._fallback_manager.is_repetitive(governed):
            diversified = self._fallback_manager.get_fallback()
            self._fallback_manager.record(diversified)
            self._diag["repeated_response_blocked"] += 1
            self._diag["semantic_fallback_used"] += 1
            return diversified

        if is_fallback:
            self._diag["semantic_fallback_used"] += 1

        self._fallback_manager.record(governed)
        return governed

    def get_continuation(self, user_text: str) -> Optional[str]:
        return self._knowledge_fallback.get_continuation(user_text)

    def is_continuation_request(self, user_text: str) -> bool:
        return self._knowledge_fallback.is_continuation_request(user_text)

    def get_diagnostics(self) -> dict:
        d = dict(self._diag)
        d["recent_responses"] = self._fallback_manager.recent_count()
        return d
