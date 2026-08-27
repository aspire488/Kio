"""
companion/observations.py — Observation Extraction.

After every meaningful interaction, extract structured observations that
feed the consolidation engine. Observations are EVIDENCE, not beliefs.

This module does NOT create beliefs. It captures what happened.
The consolidation engine synthesizes beliefs from observations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Observation:
    """A structured observation from an interaction."""
    id: str = ""
    timestamp: str = ""
    source: str = ""            # "user_message", "kio_response", "outcome", "correction"
    category: str = ""          # matches BeliefCategory
    content: str = ""           # what was observed
    context: str = ""           # when/where this happened
    confidence: float = 0.5     # how confident we are in this observation
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:12]


# ── Signal Detection ──────────────────────────────────────────────────────

_CORRECTION_SIGNALS = re.compile(
    r"\b(no|wrong|not what i|actually|wait|hold on|scratch|nvm|"
    r"that'?s not|you misunderstood|don'?t do that|not like that|"
    r"stop (?:doing|giving|making|saying|using|fabricating)|"
    r"change that|fix that|redo|i meant|i wanted|i asked|"
    r"never (?:do|say|give|use) that|don'?t (?:ever |always )?|"
    r"that was (?:wrong|incorrect|bad|terrible)|"
    r"can you (?:just|simply) give me|"
    r"i (?:don'?t |no longer )(?:want|need|like) (?:that|this|those)|"
    r"stop)\b",
    re.I,
)

_APPROVAL_SIGNALS = re.compile(
    r"\b(nice|perfect|exactly|that'?s ?right|good ?job|well ?done|"
    r"you ?got ?it|nailed ?it|there ?you ?go|it ?works|"
    r"exactly ?what i ?needed|saved ?me|thanks|thank you|"
    r"love ?it|respect|props|kudos|finally|works now|"
    r"that (?:works|helped|solved|fixed|was right))\b",
    re.I,
)

_FRUSTRATION_SIGNALS = re.compile(
    r"\b(frustrat|annoy|piss|mad|angry|irritat|ugh|god ?damn|"
    r"this ?is ?broken|not ?working|doesn'?t ?work|ridiculous|stupid|"
    r"sucks|trash|garbage|stuck|keeps ?happening|every ?time|still ?not|"
    r"what ?the|how ?is ?this|why does|can'?t ?believe|"
    r"stop (?:giving|doing|saying|making)|i (?:don'?t |no longer )(?:want|need|like))\b",
    re.I,
)

_PREFERENCE_SIGNALS = re.compile(
    r"\b(i (?:really |definitely |honestly )?(?:prefer|like|love|enjoy|"
    r"hate|dislike|don'?t like)|"
    r"(?:my (?:favorite|fav)|i (?:usually|always|normally|tend to|typically))|"
    r"(?:can you (?:always|never|please|stop))|"
    r"(?:remember (?:that )?i (?:like|want|need|prefer))|"
    r"(?:don'?t (?:ever |always )?(?:give|do|send|use|make)))\b",
    re.I,
)

_VALUE_SIGNALS = re.compile(
    r"\b(i (?:value|care about|believe in|think (?:it'?s|that'?s) important)|"
    r"(?:what matters (?:to me|most)|my (?:priority|priorities|principle|principles))|"
    r"(?:i (?:always|never) (?:try|aim|strive|work))|"
    r"(?:the (?:right|best|proper) (?:way|approach|thing) (?:is|to)))\b",
    re.I,
)

_GOAL_SIGNALS = re.compile(
    r"\b(i (?:want to|need to|plan to|aim to|going to|trying to|"
    r"hoping to|want (?:to be|to become|a|an|the)|"
    r"need (?:to be|a|an|the))|"
    r"(?:my (?:goal|plan|objective|dream|target))|"
    r"(?:i (?:'m|am) (?:building|working on|creating|making|developing))|"
    r"(?:let'?s (?:build|create|make|do|start))\b)",
    re.I,
)

_PROJECT_SIGNALS = re.compile(
    r"\b(i (?:'m|am) (?:building|working on|developing|creating|"
    r"making|prototyping|designing|implementing|coding)|"
    r"(?:the (?:project|app|website|tool|system|prototype|build))|"
    r"(?:i (?:need|want) to (?:build|create|make|develop|code|implement))|"
    r"(?:let'?s (?:build|create|make|start) (?:a|an|the|my|our))\b)",
    re.I,
)

_COMMUNICATION_STYLE_SIGNALS = re.compile(
    r"\b(can you (?:just|simply|briefly|quickly|shortly)|"
    r"(?:too (?:long|verbose|much|detailed|complicated))|"
    r"(?:stop (?:explaining|writing essays|giving (?:me )?(?:long|detailed)))|"
    r"(?:give me (?:just |only )?(?:the |a )?(?:code|commands|steps|answer))|"
    r"(?:i don'?t (?:need|want) (?:a |an )?(?:long|full|detailed|explanation))|"
    r"(?:tl;?dr|too long)|"
    r"(?:shorter|more concise|keep it brief|be brief))\b",
    re.I,
)

_KIO_FAILURE_SIGNALS = re.compile(
    r"\b(that (?:was|is) (?:wrong|incorrect|bad|terrible|fabricated|made up|"
    r"not (?:what|true|right)|a (?:lie|hallucination|invention))|"
    r"you (?:fabricated|invented|made up|hallucinated|confused|gave me a (?:fake|wrong))|"
    r"(?:stop (?:fabricating|inventing|making up|hallucinating))|"
    r"(?:that (?:URL|link|source|reference) (?:was|is) (?:fake|fabricated|not real|wrong))|"
    r"(?:you (?:got|were) (?:wrong|confused|mixed up))|"
    r"(?:fabricated|invented|made.up|hallucinated)|"
    r"(?:that was (?:a )?(?:fake|wrong|incorrect))\b)",
    re.I,
)


# ── Observation Extraction ────────────────────────────────────────────────

def extract_observations(
    user_text: str,
    kio_reply: str,
    session_id: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> List[Observation]:
    """Extract structured observations from a user-KIO exchange.
    
    Returns observations that feed the consolidation engine.
    Does NOT create beliefs — observations are evidence.
    """
    observations = []
    low = (user_text or "").lower()
    ctx = context or {}
    
    # ── Correction Detection ──
    if _CORRECTION_SIGNALS.search(low):
        observations.append(Observation(
            source="correction",
            category="self_failure",
            content=f"Joel corrected KIO: {user_text[:300]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.85,
            metadata={"kio_reply": kio_reply[:300], "correction_type": "behavioral"},
        ))
        # Also record what KIO should learn
        observations.append(Observation(
            source="learning",
            category="self_learning",
            content=f"KIO should adjust behavior: {user_text[:200]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.7,
            metadata={"trigger": "correction"},
        ))
    
    # ── Approval Detection ──
    if _APPROVAL_SIGNALS.search(low) and len(low) < 200:
        observations.append(Observation(
            source="approval",
            category="self_capability",
            content=f"Joel approved KIO response: {kio_reply[:200]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.7,
            metadata={"positive_feedback": True},
        ))
    
    # ── Frustration Detection ──
    if _FRUSTRATION_SIGNALS.search(low):
        observations.append(Observation(
            source="frustration",
            category="emotional",
            content=f"Joel expressed frustration: {user_text[:300]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.75,
            metadata={"intensity": "high" if len(_FRUSTRATION_SIGNALS.findall(low)) >= 3 else "medium"},
        ))
    
    # ── Preference Detection ──
    if _PREFERENCE_SIGNALS.search(low):
        observations.append(Observation(
            source="user_statement",
            category="preference",
            content=user_text[:300],
            context=ctx.get("conversation_topic", ""),
            confidence=0.8,
            metadata={"explicit": True},
        ))
    
    # ── Value Detection ──
    if _VALUE_SIGNALS.search(low):
        observations.append(Observation(
            source="user_statement",
            category="value",
            content=user_text[:300],
            context=ctx.get("conversation_topic", ""),
            confidence=0.75,
            metadata={"explicit": True},
        ))
    
    # ── Goal Detection ──
    if _GOAL_SIGNALS.search(low):
        observations.append(Observation(
            source="user_statement",
            category="goal",
            content=user_text[:300],
            context=ctx.get("conversation_topic", ""),
            confidence=0.8,
            metadata={"explicit": True},
        ))
    
    # ── Project Detection ──
    if _PROJECT_SIGNALS.search(low):
        observations.append(Observation(
            source="user_statement",
            category="project",
            content=user_text[:300],
            context=ctx.get("conversation_topic", ""),
            confidence=0.75,
            metadata={"explicit": True},
        ))
    
    # ── Communication Style Detection ──
    if _COMMUNICATION_STYLE_SIGNALS.search(low):
        observations.append(Observation(
            source="user_statement",
            category="communication",
            content=user_text[:300],
            context=ctx.get("conversation_topic", ""),
            confidence=0.8,
            metadata={"explicit": True},
        ))
    
    # ── KIO Failure Detection ──
    if _KIO_FAILURE_SIGNALS.search(low):
        observations.append(Observation(
            source="kio_failure",
            category="self_failure",
            content=f"KIO failure detected: {user_text[:300]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.9,
            metadata={"kio_reply": kio_reply[:300]},
        ))
    
    # ── Behavioral Pattern (message characteristics) ──
    # NOTE: Routine behavioral observations (message length, question detection)
    # are NOT extracted as standalone observations. They create noise beliefs
    # that pollute the model. Only extract behavioral patterns when they
    # contribute to a meaningful signal (e.g., repeated brevity under pressure).
    
    # ── KIO Response Quality (only flag genuinely problematic responses) ──
    if kio_reply:
        reply_len = len(kio_reply)
        if reply_len > 800 and len(user_text) < 80:
            # User asked a short question, KIO gave a very long response
            # This is a meaningful signal for verbosity training
            observations.append(Observation(
                source="kio_response",
                category="self_capability",
                content=f"KIO gave a verbose response ({reply_len} chars) to a short query ({len(user_text)} chars) about {ctx.get('conversation_topic', 'unknown')}",
                context=ctx.get("conversation_topic", ""),
                confidence=0.5,
                metadata={"response_length": reply_len, "signal": "verbose_response"},
            ))
    
    return observations


def observations_to_json(observations: List[Observation]) -> str:
    """Serialize observations for persistence."""
    import json
    return json.dumps([{
        "id": o.id,
        "timestamp": o.timestamp,
        "source": o.source,
        "category": o.category,
        "content": o.content,
        "context": o.context,
        "confidence": o.confidence,
        "metadata": o.metadata,
    } for o in observations], ensure_ascii=False)
