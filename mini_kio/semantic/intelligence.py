"""intelligence.py — public entry point to the FINAL semantic substrate.

The runtime (pipeline._chat_converse) calls exactly four functions:

    ingest_turn          decompose the utterance + apply graph ops + resolve
                         references (write side, before generation)
    semantic_state_block render the graph state that grounds generation
                         (read side, injected into the prompt)
    planner_decision     the Planner's decision for this turn
    record_kio_reply     persist KIO's own reply as an attributed statement
                         (KIO self-continuity: 'what did you say' resolves)

Everything is defensive: a failure in any step must never break the
conversation path it augments.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from .activation import activation_block
from .decomposer import Decomposition, apply_ops, decompose
from .graph import KIO_KEY, USER_KEY, SemanticGraph
from .planner import PlannerDecision, decide as _planner_decide, render_decision
from .reference import Resolution, render_references, resolve as _resolve

logger = logging.getLogger(__name__)

_MAX_KIO_STATEMENTS = 8


def get_graph(session_id: str) -> SemanticGraph:
    return SemanticGraph(session_id)


def _ensure_self(graph: SemanticGraph) -> None:
    graph.ensure_participant("user")
    graph.ensure_participant("kio")


def ingest_turn(session_id: str, text: str, raw_text: str = "") -> dict:
    """Decompose + apply graph ops + resolve references for one turn.

    Returns {'graph', 'decomposition', 'resolution'} or a safe empty result.
    """
    try:
        graph = get_graph(session_id)
        _ensure_self(graph)
        dec = decompose(graph, text or "", raw_text or "")
        apply_ops(graph, dec)
        res = _resolve(graph, text or "")
        return {"graph": graph, "decomposition": dec, "resolution": res}
    except Exception as exc:  # never break the conversation
        logger.debug("[SEMANTIC] ingest failed: %s", exc)
        return {"graph": None, "decomposition": None, "resolution": None}


def resolve_references(session_id: str, text: str) -> Resolution:
    try:
        graph = get_graph(session_id)
        _ensure_self(graph)
        return _resolve(graph, text or "")
    except Exception:
        return Resolution()


def planner_decision(session_id: str, text: str,
                     decomposition=None, resolution=None) -> PlannerDecision:
    try:
        graph = get_graph(session_id)
        return _planner_decide(graph, text or "", decomposition, resolution)
    except Exception:
        return PlannerDecision("answer", "conversation", "")


def record_kio_reply(session_id: str, reply: str) -> None:
    """Persist KIO's own reply as a KIO-attributed statement (self-continuity).
    Bounded: only substantive replies (>= 12 chars) are recorded, and the
    graph prunes to keep growth bounded."""
    try:
        reply = (reply or "").strip()
        if len(reply) < 12:
            return
        graph = get_graph(session_id)
        graph.record_statement(KIO_KEY, reply, stance="assertion",
                               supersede_prior=False, provenance="kio-reply")
        graph.prune(keep=600)
    except Exception:
        pass


def semantic_state_block(session_id: str, text: str, resolution: Optional[Resolution] = None) -> str:
    """Render the graph state that grounds generation this turn."""
    try:
        graph = get_graph(session_id)
        _ensure_self(graph)
        blocks = []
        low = (text or "").lower()

        # Participant + attribution summary (user / KIO / third parties).
        parts = []
        for who in (USER_KEY, KIO_KEY):
            stmts = graph.attributed_statements(who, active_only=True, limit=6)
            for s in stmts:
                parts.append(f"{who.split(':')[-1]}: \"{s.target_name}\"")
        third = [n for n in graph.all_active_nodes()
                 if n.kind == "participant" and n.key not in (USER_KEY, KIO_KEY)]
        for p in third[:6]:
            stmts = graph.attributed_statements(p.key, active_only=True, limit=4)
            for s in stmts:
                parts.append(f"{p.name}: \"{s.target_name}\"")
        if parts:
            blocks.append("SEMANTIC GRAPH — attributed statements (who said what):\n"
                          + "\n".join(f"- {p}" for p in parts[:20]))

        # Durable memory concepts.
        durable = [n.name for n in graph.all_active_nodes()
                   if n.kind == "concept" and n.meta.get("durable")]
        if durable:
            blocks.append("Durable memory (from the graph):\n"
                          + "\n".join(f"- {d}" for d in durable[-8:]))

        # Research intents (user-attributed): "I'm researching X" — so
        # "what did I just ask about?" / "back to that company" resolves
        # from the graph, never from raw history.
        _research = [s.target_name for s in graph.attributed_statements(
            USER_KEY, active_only=True, limit=20)
            if str(getattr(s, "target_name", "") or "").startswith("researching:")]
        if _research:
            blocks.append("Your current research subjects (from the graph):\n"
                          + "\n".join(f"- {r.split(':', 1)[-1].strip()}" for r in _research[-4:]))

        # Computed activation (no topic pointer — computed every turn).
        act = activation_block(graph, text or "")
        if act:
            blocks.append(act)

        # Resolved references + retrieved statements.
        if resolution is not None:
            ref_block = render_references(resolution)
            if ref_block:
                blocks.append(ref_block)

        # Attribution queries: the retrieved statements ARE the answer.
        if resolution is not None and getattr(resolution, "statements", None):
            blocks.append(
                "DIRECT ANSWER (attribution recall): the user asked who said "
                "what. Answer STRICTLY from the retrieved statements above — "
                "quote them; never invent or substitute a web answer. If the "
                "retrieved statements do not cover what was asked, say plainly "
                "that you have no record of it."
            )

        # Unknown-entity anti-fabrication: when the user's message names an
        # entity ("I'm researching Zorbion", "What about Zorbion?") and the
        # graph holds NO PROPOSITION about it, the answer must preserve
        # uncertainty — never invent a description (live: KIO fabricated
        # "Zorbion Dynamics is a private aerospace company" on the research-
        # intent turn itself, then that fabricated reply was recorded as a KIO
        # statement, compounding).
        #
        # "Known" here means the entity has an ACTUAL PROPOSITION: it is a
        # participant with attributed statements, OR a claim node is linked
        # ABOUT it, OR a research-intent statement names it (the user owns the
        # research goal — the entity is a research subject, never a described
        # fact). A bare topic node created from a mention is NOT knowledge:
        # it must not silence the guard.
        # The FIRST capitalized token is often a sentence-initial question
        # word ("What about Zorbion?") — scan for a LATER capitalized word so
        # the probe is the entity, not 'what'.
        _named = None
        for _m in re.finditer(r"\b[A-Z][A-Za-z]{2,20}\b", text or ""):
            if _m.group(0).lower() in ("what", "which", "where", "when", "why", "how", "who", "hey"):
                continue
            _named = _m
            break
        _has_resolved = resolution is not None and bool(getattr(resolution, "statements", None))
        if _named and not _has_resolved:
            _probe = _named.group(0).lower()
            _probe_tokens = set(re.findall(r"[a-z0-9]+", _probe))
            _known = set()
            # (a) participants with attributed statements;
            for n in graph.all_active_nodes():
                if n.kind == "participant":
                    if graph.attributed_statements(n.key, active_only=True, limit=1):
                        _known.add((n.name or "").lower())
                        _known.update((a or "").lower() for a in (n.meta.get("aliases") or []))
            # (b) claim nodes linked 'about' an entity (a real proposition).
            for n in graph.all_active_nodes():
                if n.kind != "topic":
                    continue
                if graph.links_for(n.id, active_only=True):
                    _known.add((n.name or "").lower())
            # (c) the user's own research-intent statements name the subject —
            # a research subject is KNOWN TO THE USER, so the model may say
            # "you were researching X" but must NOT describe X's facts.
            # Deliberately NOT added to `_known` (which gates the UNKNOWN
            # guard): a research subject has no proposition describing what
            # it IS, so the research-subject guard below must fire.
            _research_subjects = set()
            for s in graph.attributed_statements(USER_KEY, active_only=True, limit=20):
                t = str(getattr(s, "target_name", "") or "").strip()
                if t.lower().startswith("researching:"):
                    _research_subjects.add(t.split(":", 1)[-1].strip().lower())

            def _overlap(known_entry: str) -> bool:
                return (_probe == known_entry or _probe in known_entry
                        or known_entry in _probe
                        or (_probe_tokens and set(re.findall(r"[a-z0-9]+", known_entry)) & _probe_tokens))

            _is_research_subject = any(_overlap(r) for r in _research_subjects)
            _has_proposition = any(_overlap(k) for k in _known)
            if not _has_proposition and len(_probe) >= 3:
                if _is_research_subject:
                    blocks.append(
                        "RESEARCH SUBJECT GUARD: the named entity is something "
                        "the USER is researching — it is a research target, not "
                        "an established fact. You may acknowledge they are "
                        "researching it, but you must NOT describe the entity's "
                        "attributes, industry, history, or capabilities unless "
                        "the graph holds a real proposition about it. If you "
                        "have no evidence, say so and offer to research it."
                    )
                else:
                    blocks.append(
                        "UNKNOWN ENTITY GUARD: the named entity in the user's "
                        "message has NO proposition in the graph and NO "
                        "retrieved evidence describing what it is. Do NOT "
                        "describe it, do NOT invent facts about it, do NOT "
                        "guess what it is. Say plainly you don't have reliable "
                        "information about it (or offer to research it if the "
                        "user wants). Inventing a description would be "
                        "fabrication."
                    )
        elif re.search(r"\b(what did|what does|what has|what have)\s+(i|you|he|she|they|we)\b", low) \
                or re.search(r"\b(what did|what does)\s+[A-Z][a-z]+\b", text or ""):
            blocks.append(
                "RECALL QUESTION: the user asks about prior conversation. If "
                "the SEMANTIC GRAPH above contains the relevant statement, "
                "answer from it verbatim. If it does NOT contain it, say "
                "honestly you don't have a record of it — never invent, never "
                "substitute web research, never answer from the raw transcript "
                "above if the graph disagrees with it."
            )

        # KIO self-opinion recall (F5, holdout): "do you still think X is
        # good? / do you still believe that? / do you still agree?" asks about
        # KIO's OWN prior stance. KIO must answer from RECORDED KIO-attributed
        # statements only — never invent "I still think..." for an opinion KIO
        # never expressed (live holdout: "Do you still think the theremin is a
        # good idea?" and "Do you still think the script is undeciphered?"
        # both fabricated a prior KIO stance from nothing). General mechanism:
        # KIO self-continuity is a graph query on attributed_to=KIO.
        _kio_self = re.search(
            r"\bdo\s+you\s+(?:still\s+)?(?:think|believe|feel|agree|recommend|prefer|maintain|stand\s+by)\b",
            low,
        )
        if _kio_self:
            _has_kio_stmt = bool(graph.attributed_statements(KIO_KEY, active_only=True, limit=8))
            if not _has_kio_stmt:
                blocks.append(
                    "KIO SELF-OPINION GUARD: the user asks whether you still "
                    "hold an opinion. The graph records NO KIO-attributed "
                    "statements for this session — you never expressed a prior "
                    "stance on this. Do NOT claim 'I still think / I always "
                    "believed' for anything you never said. You may give a "
                    "fresh current opinion (clearly as your current view), but "
                    "never imply a prior position existed."
                )
            else:
                blocks.append(
                    "KIO SELF-OPINION GUARD: answer 'do you still think/agree' "
                    "STRICTLY from your recorded statements in the SEMANTIC "
                    "GRAPH block above. If none of them matches the subject of "
                    "the question, say you don't recall stating a position on "
                    "it — never invent a prior stance."
                )

        return "\n\n".join(blocks)
    except Exception as exc:
        logger.debug("[SEMANTIC] state block failed: %s", exc)
        return ""


def render_planner(decision: PlannerDecision) -> str:
    return render_decision(decision)
