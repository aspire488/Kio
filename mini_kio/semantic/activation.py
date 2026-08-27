"""activation.py — COMPUTED relevance over the graph (FINAL architecture).

There is deliberately NO current-topic pointer, no thread stack, no
ACTIVE/SUSPENDED/DORMANT state machine. Relevance is recomputed from graph
state every turn:

    score(node) = recency_decay * (1 + 2*mention_count)
                  + explicit_reactivation + graph_distance_component

- recency: exponential decay over link id (later link = fresher mention).
- mention_count: number of active links touching the node.
- explicit reactivation: the user's current text names the node -> strong bump
  ("back to the mentorship thing" revives an old situation without any state).
- graph_distance: nodes linked to the currently-resolved anchors gain a boost,
  so "what does its founder think" finds the founder OF the active company.

Topic switching (A->B->C->A) falls out of these signals: A stays retrievable
because its nodes keep their mention history and reactivation is explicit.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Sequence, Tuple

from .graph import SemanticGraph, SemanticNode

# Decay: link ~6 turns back retains ~37% weight, ~12 turns back ~13%.
_RECENCY_DECAY_TURNS = 6.0
_MENTION_MULTIPLIER = 2.0
_EXPLICIT_BONUS = 3.0
_ANCHOR_BONUS = 1.2

_WORD_RE = re.compile(r"[a-z0-9]+")

# Stopwords never participate in semantic compatibility — a node named
# "holiday in japan" must match on (holiday, japan), never on 'in'.
_STOP = frozenset(
    "a an the and or but if so then than to of for with about on at in from by "
    "i you me my your we our he him his she her they them their it its this that "
    "these those is are was were be been being do does did have has had what why "
    "how who when where which there here now just really very like want would will "
    "can could should shall may might am not no yes ok okay please tell say said "
    "says think thinks thought believe believes know knows something anything "
    "everything nothing someone anybody else also still already today tomorrow "
    "yesterday".split()
)


def _tokens(text: str) -> set:
    return {t for t in _WORD_RE.findall((text or "").lower()) if t not in _STOP and len(t) >= 3}


def _name_matches(text_lower: str, node: SemanticNode) -> bool:
    if not node.name:
        return False
    name_tokens = _tokens(node.name)
    if not name_tokens:
        return False
    for t in name_tokens:
        if len(t) >= 3 and t in text_lower:
            return True
    for alias in (node.meta.get("aliases") or []):
        a = str(alias).strip().lower()
        if len(a) >= 3 and a in text_lower:
            return True
    return False


def compute_activation(graph: SemanticGraph, text: str,
                       anchors: Sequence[SemanticNode] = (),
                       limit: int = 30) -> List[Tuple[SemanticNode, float]]:
    """Rank active nodes by computed relevance. `anchors` = nodes already
    resolved this turn (for the graph-distance component)."""
    links = graph.recent_links(limit=200, active_only=True)
    text_lower = (text or "").lower()
    max_link_id = max((l.id for l in links), default=0)

    mention: Dict[int, int] = {}
    last_id: Dict[int, int] = {}
    for l in links:
        for nid in (l.source_id, l.target_id):
            mention[nid] = mention.get(nid, 0) + 1
            last_id[nid] = max(last_id.get(nid, 0), l.id)

    anchor_ids = {n.id for n in anchors}
    scores: Dict[int, float] = {}
    for nid, count in mention.items():
        recency = math.exp(-(max_link_id - last_id[nid]) / _RECENCY_DECAY_TURNS)
        score = recency * (1.0 + _MENTION_MULTIPLIER * count)
        scores[nid] = score

    # Semantic compatibility: a topic/concept/resource whose name appears in a
    # recent CLAIM text shares the claim's relevance (statements reference
    # their subjects, so the subjects must inherit activation).
    if links:
        claim_tokens_bag = []
        for l in links:
            if l.target_kind == "claim" and l.target_name:
                claim_tokens_bag.append(set(_tokens(l.target_name)))
        for node in graph.all_active_nodes():
            if node.kind == "claim":
                continue
            nt = _tokens(node.name)
            if not nt:
                continue
            for ct in claim_tokens_bag:
                if nt & ct:
                    scores[node.id] = scores.get(node.id, 0.0) + 0.6
                    break

    # Graph-distance boost: nodes co-mentioned with an anchor get a bump.
    if anchor_ids:
        for l in links:
            bump = False
            other = None
            if l.source_id in anchor_ids:
                bump, other = True, l.target_id
            elif l.target_id in anchor_ids:
                bump, other = True, l.source_id
            if bump and other is not None:
                scores[other] = scores.get(other, 0.0) + _ANCHOR_BONUS

    nodes = {n.id: n for n in graph.all_active_nodes()}
    ranked = []
    for nid, score in scores.items():
        node = nodes.get(nid)
        if node is None:
            continue
        if node.kind in ("claim",):
            continue  # claims are reached through their attributor, never top-level
        if _name_matches(text_lower, node):
            score += _EXPLICIT_BONUS
        ranked.append((node, score))

    ranked.sort(key=lambda pair: (-pair[1], -pair[0].id))
    return ranked[:limit]


def top_referents(graph: SemanticGraph, text: str,
                  anchors: Sequence[SemanticNode] = (),
                  k: int = 8) -> List[SemanticNode]:
    return [n for n, _ in compute_activation(graph, text, anchors=anchors, limit=k)]


def activation_block(graph: SemanticGraph, text: str,
                     anchors: Sequence[SemanticNode] = ()) -> str:
    """Render the current semantic focus as a prompt block (no pointer)."""
    ranked = compute_activation(graph, text, anchors=anchors, limit=8)
    if not ranked:
        return ""
    lines = ["Current semantic focus (computed activation, strongest first):"]
    for node, score in ranked:
        lines.append(f"- {node.name} ({node.kind}) — activation {score:.2f}")
    return "\n".join(lines)
