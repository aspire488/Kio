"""
personal_resolver.py — Intelligent personal query resolver.

Handles 'what do you know about me?', 'what am I good at?',
'what are my strengths?', 'what are my goals?', etc.

Synthesizes from the living model rather than dumping raw data.
The LLM composes naturally from structured evidence; this resolver
provides the evidence and prompts natural composition.
"""

import re
from typing import Optional
from mini_kio.resolvers.base import BaseResolver
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext


# Pattern definitions: each maps a regex to a query dimension.
_PERSONAL_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # "what do you know about me" / "what do you remember about me"
    (re.compile(r"what\s+(?:do\s+you\s+)?(?:know|remember|recall)\s+about\s+me", re.I),
     "synthesize", "About me"),
    # "tell me about myself" / "what's my profile"
    (re.compile(r"(?:tell\s+me\s+about\s+myself|what(?:'s|s)\s+(?:my|the)\s+(?:profile|summary))", re.I),
     "synthesize", "My profile"),
    # "what am I studying" / "what's my major" / "my education"
    (re.compile(r"(?:what\s+am\s+I\s+studying|what(?:'s|s)\s+my\s+(?:major|field|course|education|semester|cgpa))", re.I),
     "education", "Education"),
    # "what am I working on" / "my projects" / "what projects"
    (re.compile(r"(?:what\s+(?:am\s+I\s+)?(?:working\s+on|building|doing)|my\s+projects?|what\s+projects?)", re.I),
     "projects", "Projects"),
    # "what are my goals" / "what do I want"
    (re.compile(r"(?:what\s+(?:are|do)\s+my\s+(?:goals?|plans?|priorities?)|what\s+do\s+I\s+want)", re.I),
     "goals", "Goals"),
    # "what am I good at" / "what are my strengths"
    (re.compile(r"(?:what\s+am\s+I\s+(?:good\s+at|great\s+at|strong\s+in)|what\s+are\s+my\s+strengths?|what\s+do\s+I\s+(?:do\s+well|excel\s+at))", re.I),
     "strengths", "Strengths"),
    # "what am I bad at" / "what are my weaknesses"
    (re.compile(r"(?:what\s+am\s+I\s+(?:bad\s+at|weak\s+at|struggling\s+with)|what\s+are\s+my\s+(?:weaknesses?|friction)|what\s+do\s+I\s+(?:keep\s+messing|struggle\s+with))", re.I),
     "weaknesses", "Weaknesses"),
    # "what do I like" / "my preferences"
    (re.compile(r"(?:what\s+do\s+I\s+(?:like|enjoy|prefer)|my\s+(?:preferences?|likes?|taste))", re.I),
     "preferences", "Preferences"),
    # "what are my interests"
    (re.compile(r"(?:what\s+(?:are|do)\s+my\s+interests?|what\s+am\s+I\s+(?:interested\s+in|curious\s+about))", re.I),
     "interests", "Interests"),
    # "what have I been doing lately" / "recent activity"
    (re.compile(r"(?:what\s+have\s+I\s+been\s+(?:doing|up\s+to)|recent\s+(?:activity|changes?))", re.I),
     "recent_changes", "Recent changes"),
    # "what decisions have I made"
    (re.compile(r"(?:what\s+(?:decisions?|choices?)\s+(?:have\s+I|did\s+I)\s+(?:make|decide))", re.I),
     "decisions", "Decisions"),
    # "how have I changed" / "how have I grown"
    (re.compile(r"(?:how\s+have\s+I\s+(?:changed|grown|evolved|developed))", re.I),
     "recent_changes", "Growth"),
    # "what am I waiting for" / "what's pending"
    (re.compile(r"(?:what\s+(?:am\s+I\s+|are\s+we\s+)?(?:waiting\s+(?:for|on)|pending|blocked\s+on))", re.I),
     "waiting", "Waiting-on items"),
    # "what have I been avoiding" / "what am I procrastinating"
    (re.compile(r"(?:what\s+have\s+I\s+been\s+(?:avoiding|putting\s+off|procrastinating)|what\s+am\s+I\s+(?:avoiding|putting\s+off|procrastinating))", re.I),
     "avoiding", "Avoided items"),
    # "what patterns do you notice" / "what do you observe about me"
    (re.compile(r"(?:what\s+(?:patterns?|habits?)\s+(?:do\s+you\s+)?(?:notice|see|observe)|what\s+do\s+you\s+(?:notice|observe|see)\s+about\s+me)", re.I),
     "patterns", "Observed patterns"),
    # "what are my habits" / "how do I work"
    (re.compile(r"(?:what\s+(?:are|do)\s+my\s+habits?|how\s+(?:do\s+I|am\s+I)\s+(?:work|operate|function|approach))", re.I),
     "patterns", "Working patterns"),
    # "what have I been learning" / "what have I learned"
    (re.compile(r"(?:what\s+have\s+I\s+been\s+learning|what\s+have\s+I\s+learned)", re.I),
     "interests", "Learning"),
    # COMPLEMENTARY COMPANION QUERIES — route to LLM with companion projection
    # "how have we gotten better" / "how do we work together"
    (re.compile(r"(?:how\s+(?:have\s+we|do\s+we)\s+(?:\w+\s+){0,2}(?:get|work|collaborate|improve|grow|better))", re.I),
     "patterns", "Collaboration patterns"),
    # "what mistakes have you learned" / "what have you gotten wrong"
    (re.compile(r"(?:what\s+(?:mistakes?|errors?|failures?)\s+(?:have\s+you|did\s+you|do\s+you)|what\s+have\s+you\s+(?:gotten|got)\s+wrong)", re.I),
     "avoiding", "Learned failures"),
    # "what should you avoid" / "what should you not do"
    (re.compile(r"(?:what\s+should\s+you\s+\w*\s*(?:avoid|not\s+do|stop|never)|what\s+do\s+you\s+(?:keep\s+messing|struggle))", re.I),
     "avoiding", "Avoided behaviors"),
    # "what are your strengths" / "what are your weaknesses"
    (re.compile(r"(?:what\s+are\s+your\s+\w*\s*(?:strengths?|weaknesses?|failures?|capabilities|limitations))", re.I),
     "weaknesses", "Self-assessment"),
    # "continue working on KIO" / "what about KIO"
    (re.compile(r"(?:continue\s+(?:working|development|building)|what\s+(?:about|is\s+the\s+status\s+of)\s+KIO)", re.I),
     "projects", "KIO project"),
    # "how have my priorities changed" / "how have I changed"
    (re.compile(r"(?:how\s+have\s+(?:my\s+)?(?:priorities|goals|focus|interests)\s+changed)", re.I),
     "recent_changes", "Priority changes"),
]


class PersonalResolver(BaseResolver):
    """Handles intelligent personal queries by synthesizing from the living model.

    This resolver intercepts 'about me' style queries BEFORE they reach the
    LLM, provides structured evidence from the living model, and lets the
    LLM compose naturally.
    """

    def resolve(self, text: str, state: SessionState, trace: TraceContext) -> Optional[str]:
        text_lower = text.lower().strip()

        for pattern, dimension, label in _PERSONAL_PATTERNS:
            if pattern.search(text_lower):
                trace.add_step(f"PersonalResolver: dimension '{dimension}'")
                return self._resolve_dimension(state.session_id, dimension, label, text_lower)

        return None

    def _resolve_dimension(self, session_id: str, dimension: str, label: str, user_text: str) -> str:
        try:
            from mini_kio.memory.living_model import (
                synthesize_about_user, query_education, query_projects,
                query_strengths, query_preferences, query_goals,
                query_decisions, query_interests, query_recent_changes,
                query_waiting, query_avoiding, query_patterns,
            )
        except ImportError:
            return ""

        query_map = {
            "synthesize": lambda: synthesize_about_user(session_id),
            "education": lambda: self._format_items(query_education(session_id), "education"),
            "projects": lambda: self._format_items(query_projects(session_id), "projects"),
            "goals": lambda: self._format_items(query_goals(session_id), "goals"),
            "strengths": lambda: self._format_items(query_strengths(session_id), "strengths"),
            "preferences": lambda: self._format_items(query_preferences(session_id), "preferences"),
            "interests": lambda: self._format_items(query_interests(session_id), "interests"),
            "recent_changes": lambda: self._format_items(query_recent_changes(session_id), "recent changes"),
            "decisions": lambda: self._format_items(query_decisions(session_id), "decisions"),
            "waiting": lambda: self._format_items(query_waiting(session_id), "waiting-on items"),
            "avoiding": lambda: self._format_items(query_avoiding(session_id), "avoided items"),
            "patterns": lambda: self._format_items(query_patterns(session_id), "observed patterns"),
        }

        if dimension == "weaknesses":
            result = self._synthesize_weaknesses(session_id)
            if result:
                return result
            return "I don't have enough evidence-backed patterns to identify specific friction points yet."

        formatter = query_map.get(dimension)
        if not formatter:
            return ""

        result = formatter()
        if not result:
            return f"I don't have enough information about your {label.lower()} yet."

        return result

    def _format_items(self, items: list[dict], dimension: str) -> str:
        if not items:
            return ""
        lines = [f"Evidence for {dimension}:"]
        for it in items[:8]:
            text = it.get("text", "")
            when = it.get("when", "")
            confidence = it.get("confidence", "")
            state_val = it.get("state", "")
            suffix = ""
            if state_val == "historical":
                suffix = " [historical]"
            if confidence in ("strong_inference", "weak_inference"):
                suffix += f" [{confidence}]"
            when_str = f" ({when})" if when else ""
            lines.append(f"- {text}{when_str}{suffix}")
        return "\n".join(lines)

    def _synthesize_weaknesses(self, session_id: str) -> str:
        """Synthesize friction points from evidence — never fabricated."""
        try:
            from mini_kio.memory.living_model import living_model
            model = living_model(session_id)
            challenges = model.get("challenges", [])
            if challenges:
                lines = ["Evidence-backed friction points:"]
                for ch in challenges[:5]:
                    text = ch.get("text", "")
                    confidence = ch.get("confidence", "")
                    suffix = f" [{confidence}]" if confidence in ("strong_inference", "weak_inference") else ""
                    lines.append(f"- {text}{suffix}")
                return "\n".join(lines)
        except Exception:
            pass
        return ""
