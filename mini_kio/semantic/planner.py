"""planner.py — the Planner (FINAL architecture).

The Planner operates over the DECOMPOSED semantic updates and the graph — it
is NOT a domain router and NOT a message classifier. It decides what KIO
should do this turn:

    answer | ask | research | act | defer | explain | refuse

Key guarantees:
- An UNRESOLVED reference on a CONSEQUENTIAL action never executes: the
  planner answers with a clarifying question instead.
- Current-information intents ('latest', 'what changed', 'is this true')
  route to research unless the graph already holds fresh attributed evidence.
- Everything else is ordinary conversation; the LLM answers with the graph
  state in context.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .graph import SemanticGraph, SemanticNode

# Consequential action verbs — a reference feeding one of these MUST be
# resolved before execution; unresolved => ask, never act.
_ACTION_VERBS = re.compile(
    r"\b(send|reply|draft|email|message|tell|open|close|play|delete|remove|"
    r"execute|run|do|set|create|post|upload|download|pay|cancel|schedule|"
    r"book|order|start|stop|launch|install|uninstall|write|save|print|"
    r"forward|share|invite|remind)\b"
)

_CURRENT_INTENT = re.compile(r"\b(latest|now|today|recently|current|what changed|what's new|is this true|did that happen|still|update)\b")


class PlannerDecision:
    __slots__ = ("mode", "reason", "block")

    def __init__(self, mode: str, reason: str = "", block: str = ""):
        self.mode = mode          # answer | ask | research | act | defer | explain | refuse
        self.reason = reason
        self.block = block        # optional prompt block describing the decision

    def __repr__(self):  # pragma: no cover
        return f"<Planner {self.mode}: {self.reason}>"


# Content-creation frames: the user asks for CONTENT (a draft, a message,
# a reply, something to send) — recipient identity is NOT required to
# produce content. Delivery ("send it to X") is a SEPARATE consequential
# intention requiring recipient resolution + authorization. Live bug:
# "Give me something I can send him" asked "who is the him you'd like to
# send something to?" — the user wanted a DRAFT, not delivery.
_DRAFT_FRAME = re.compile(
    r"\b(give me something|something i can send|something to send|a draft|draft a|write a reply|"
    r"write a message|compose a reply|compose a message|a reply to|a response to|a message to|"
    r"something to say|what should i say|what do i say|can you write|could you write|draft me|"
    r"give (him|her|them|himself|herself|him or her|someone|somebody|the team) a (reply|response|message|answer|draft))\b"
)


def decide(graph: SemanticGraph, text: str, decomposition, resolution=None) -> PlannerDecision:
    """Produce the Planner decision for this turn. Never throws."""
    low = (text or "").lower()
    intents = getattr(decomposition, "intents", set())

    # 0) DRAFT frames are content creation: produce the content WITHOUT
    #    resolving the recipient. Delivery is a later, separate intention.
    if _DRAFT_FRAME.search(low):
        return PlannerDecision(
            "answer",
            "content-creation request (draft) — recipient not required",
            "Planner decision: the user asked for CONTENT (a draft/message/reply "
            "to give someone). Produce the draft naturally in KIO's voice. The "
            "recipient's identity is NOT needed to write content — do not ask who "
            "the recipient is. If the user later says 'send it to X', that is a "
            "separate delivery step requiring the recipient and authorization.",
        )

    # 1) Consequential action + unresolved reference -> ASK (never act).
    if _ACTION_VERBS.search(low):
        unresolved = list(getattr(resolution, "unresolved", []) or [])
        if unresolved:
            pronoun = next((u for u in unresolved if u in _PRONOUN_WORDS), None)
            if pronoun is not None:
                return PlannerDecision(
                    "ask",
                    f"unresolved pronoun '{pronoun}' on a consequential action",
                    f"Planner decision: the user's message asks for an action but the "
                    f"target of '{pronoun}' is ambiguous in the graph. Do NOT act and do "
                    f"NOT guess. Ask ONE short question naming the ambiguity (e.g. who "
                    f"'{pronoun}' refers to) so the user can resolve it.",
                )
            return PlannerDecision(
                "ask",
                "unresolved reference on a consequential action",
                "Planner decision: this message requests an action whose target could "
                "not be resolved confidently. Ask a short clarifying question; never "
                "guess a target and never execute.",
            )

    # 2) Current-information intent with no fresh graph evidence -> research.
    if "current" in intents and _CURRENT_INTENT.search(low):
        return PlannerDecision(
            "research",
            "currentness requested",
            "Planner decision: the user asks for current/latest information. If the "
            "needed fact is not already in the graph or is time-sensitive, say so "
            "honestly and offer to look it up rather than answering from stale model "
            "memory.",
        )

    # 3) Correction -> acknowledge the supersession naturally.
    if "correct" in intents:
        return PlannerDecision(
            "answer",
            "correction superseded prior state",
            "Planner decision: the user corrected an earlier statement. Acknowledge "
            "the correction naturally and continue — do not apologize at length or "
            "reset the conversation.",
        )

    # 3b) Forget/retract -> acknowledge; the graph already excluded the target
    # from recall. Never re-introduce the forgotten subject.
    if "reject" in intents:
        return PlannerDecision(
            "answer",
            "forget request recorded",
            "Planner decision: the user asked to forget something. Acknowledge "
            "briefly and naturally. Do NOT bring the forgotten subject back up, "
            "do NOT re-summarize it, and do NOT claim you cannot forget.",
        )

    # 4) Commitments / preferences -> confirm + note.
    if "commit" in intents:
        return PlannerDecision(
            "answer",
            "user commitment recorded",
            "Planner decision: the user expressed an intention/decision. It has been "
            "recorded in the graph. Confirm briefly and naturally; do not lecture.",
        )

    # 5) Attribution queries already resolved by the resolver -> answer from graph.
    if resolution is not None and getattr(resolution, "statements", None):
        return PlannerDecision(
            "answer",
            "attributed statements retrieved from the graph",
            "Planner decision: the user asked about what someone said. Answer "
            "STRICTLY from the 'Retrieved from the graph' block above — quote the "
            "attributed statement, never invent one.",
        )

    # 6) Generic question -> answer (LLM with graph state).
    if "ask" in intents:
        return PlannerDecision("answer", "question", "")

    # 7) Anything else -> ordinary conversation.
    return PlannerDecision("answer", "conversation", "")


_PRONOUN_WORDS = frozenset(
    "he him his she her hers they them their it this that these those".split()
)


def render_decision(decision: PlannerDecision) -> str:
    if not decision.block:
        return ""
    return f"[Planner: {decision.mode} — {decision.reason}]\n{decision.block}"
