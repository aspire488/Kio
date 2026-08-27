"""reference.py — ONE general reference resolver (FINAL architecture).

Resolves arbitrary references to Nodes (and, through them, to attributed
Links) using semantic compatibility + grammatical/structural constraints +
computed activation + attribution — never a giant phrase/regex table and
never a per-domain handler.

Grammar classes (pronoun person/case, possessives, demonstratives) are the
only fixed vocabulary; resolution itself is structural:

- he/him/his  -> a recent MALE participant node
- she/her/hers-> a recent FEMALE participant node
- they/them   -> a recent GROUP participant node (or, when no group exists,
                 the strongest non-user participant — 'they' commonly refers
                 to a just-introduced person, e.g. 'Alex said... what did
                 THEY say')
- it/this/that/these/those -> the strongest non-participant node
- "the/my/your/that <noun>", "the other one", "the first one", "the newer
  one", "its <noun>" -> kind/name/relation/order matching against candidates
- "what (you|I|he|she|they) said/believes/...", "your recommendation" ->
  attribution query over Links (resolved to the attributing participant AND
  the retrieved statements)

Near-tied candidates are left UNRESOLVED — the Planner decides whether to
ask/hedge; an unresolved target NEVER reaches consequential execution.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .activation import top_referents
from .graph import KIO_KEY, USER_KEY, SemanticGraph, SemanticLink, SemanticNode

# Grammatical classes (grammar, not a phrase table — resolution is structural).
_MALE = {"he", "him", "his", "himself"}
_FEMALE = {"she", "her", "hers", "herself"}
_GROUP = {"they", "them", "their", "theirs", "themselves"}
_NEUTER = {"it", "its", "this", "that", "these", "those", "which", "there"}
_PERSONAL = _MALE | _FEMALE | _GROUP | _NEUTER
_POSS_MY = {"my", "mine"}
_POSS_YOUR = {"your", "yours"}

_SAY_VERBS = re.compile(
    r"\b(said|says|say|told|believes|believed|thinks|thought|prefers|preferred|"
    r"recommended|recommends|wants|wanted|decided|decides|suggested|suggests|"
    r"mentioned|mentioned|claimed|claims|agreed|disagreed)\b"
)

_TITLE_WORDS = re.compile(
    r"^(the|my|your|our|their|his|her|its|that|this|those|these|a|an)\s+(.+)$"
)

_RANK_ORDER = re.compile(r"\b(the\s+)?(first|second|third|last|other|newer|older|previous|next)\s+(one|person|thing|item)?\b")


class Resolution:
    """Outcome of one reference-resolution pass."""

    __slots__ = ("referents", "statements", "unresolved", "person_map")

    def __init__(self):
        self.referents: Dict[str, SemanticNode] = {}   # pronoun/surface -> node
        self.statements: List[SemanticLink] = []       # attributed statements retrieved
        self.unresolved: List[str] = []                # surfaces with no confident target
        self.person_map: Dict[str, SemanticNode] = {}  # resolved personal pronouns -> node

    def node_for(self, surface: str) -> Optional[SemanticNode]:
        return self.referents.get(surface)


def _participant_nodes(graph: SemanticGraph) -> List[SemanticNode]:
    return [n for n in graph.all_active_nodes() if n.kind == "participant"]


def _by_gender(nodes: Sequence[SemanticNode], gender: str) -> List[SemanticNode]:
    return [n for n in nodes if (n.meta.get("gender") or "") == gender]


def _desc_match(node: SemanticNode, noun_tokens: set) -> bool:
    """Does this node match a 'the X / my X / that X' description?"""
    if not noun_tokens:
        return False
    name_tokens = set(re.findall(r"[a-z0-9]+", (node.name or "").lower()))
    for t in noun_tokens:
        if len(t) >= 3 and (t in name_tokens or t in {a.lower() for a in (node.meta.get("aliases") or [])}):
            return True
    # kind match: "that person" -> participant; "that video" -> media/resource
    kind_low = (node.kind or "").lower()
    if noun_tokens & {"person", "guy", "dude", "friend", "developer", "colleague", "client"} and kind_low == "participant":
        return True
    if noun_tokens & {"video", "movie", "film", "song", "article", "document", "page", "website", "show", "game"} and kind_low in ("resource", "media", "topic", "situation"):
        return True
    return False


def resolve(graph: SemanticGraph, text: str) -> Resolution:
    """Resolve references in `text` against the graph. Never throws."""
    res = Resolution()
    low = (text or "").lower()
    if not low.strip():
        return res

    participants = _participant_nodes(graph)
    # user + KIO are always present (created on first use) but are not
    # third-party referents for he/she/they.
    third_party = [p for p in participants if p.key not in (USER_KEY, KIO_KEY)]
    others = top_referents(graph, text, k=10)
    non_participants = [n for n in others if n.kind != "participant"]
    # Recent claim targets are legitimate neuter referents ('it/this' pointing
    # at the thing just discussed) — claims stay out of top activation but are
    # reachable here through their most recent statement links.
    for l in graph.recent_links(limit=8, active_only=True):
        if l.relation == "said" and l.target_kind == "claim":
            tgt = graph.get_node(l.target_id)
            if tgt and tgt not in non_participants:
                non_participants.append(tgt)
    # Last-mention recency (by link id) is the tie-break for pronoun resolution:
    # the most recently MENTIONED participant wins — node creation order alone
    # can tie Alex and Sarah created one turn apart.
    last_mention = {}
    for l in graph.recent_links(limit=120, active_only=True):
        for nid in (l.source_id, l.target_id):
            last_mention[nid] = max(last_mention.get(nid, 0), l.id)

    words = set(re.findall(r"[a-z]+", low))

    # 1) Personal pronouns.
    for w in sorted(words):
        if w in _PERSONAL:
            if w in res.referents or w in _NEUTER and w in ("this", "that") and "this is" in low:
                pass
            target = None
            if w in _MALE:
                target = _pick(_by_gender(third_party, "male") or third_party, last_mention)
            elif w in _FEMALE:
                target = _pick(_by_gender(third_party, "female") or third_party, last_mention)
            elif w in _GROUP:
                # 'they' with multiple parties is genuinely ambiguous — only a
                # declared group or a SINGLE third party resolves it.
                group_g = [p for p in third_party if (p.meta.get("gender") or "") == "group"]
                if group_g:
                    target = _pick(group_g, last_mention)
                elif len(third_party) == 1:
                    target = third_party[0]
                else:
                    target = None
            else:  # neuter
                target = _pick(non_participants, last_mention)
            if target is not None:
                res.referents[w] = target
                res.person_map[w] = target
                # 'it/its' also resolves to the neuter target for 'its founder'
                if w in _NEUTER:
                    res.referents.setdefault("its", target)
            else:
                res.unresolved.append(w)

    # 2) Attribution queries: "what did (he|she|they|you|I) say / believe / recommend"
    for m in re.finditer(r"(?:(what|that)\s+)?(?:did|does|do|would|can)\s+(he|she|they|you|i)\s+(\w+)\b", low):
        who, verb = m.group(2), m.group(3)
        if verb not in _SAY_PATTERN_WORDS:
            continue
        node = res.person_map.get(who)
        if node is None:
            node = _participant_for_who(graph, who)
            if node is None:
                res.unresolved.append(who)
                continue
        key = node.key
        relation = _relation_for_verb(verb)
        stance = _stance_for_verb(verb)
        stmts = graph.attributed_statements(key, relation=relation, stance=stance) if stance else \
                graph.attributed_statements(key, relation=relation)
        if not stmts and relation == "said":
            stmts = graph.attributed_statements(key)  # fall back to any statement
        if stmts:
            res.referents[f"{who}-said"] = node
            res.statements.extend(stmts[:5])
        else:
            res.unresolved.append(f"{who} said")

    # 2b) NAMED attribution queries: "what did Dana say / what does Sarah
    # think / what has Bao recommended" — a capitalized name followed by a
    # reporting verb. Symmetric with pronoun attribution: the name resolves
    # to the graph participant (or a role-alias), and their attributed
    # statements are retrieved. Live failure: "What did Dana say?" returned
    # unrelated research because the resolver only handled pronouns; the
    # name path now retrieves Dana's actual statement from the graph.
    _src = text or ""  # case-preserved: names are capitalized in the source
    for m in re.finditer(
        r"(?:what|that|which)\s+(?:did|does|has|have)\s+([A-Z][A-Za-z]{2,20})\s+"
        r"(said|says|say|told|tells|think|thinks|thought|believe|believes|believed|"
        r"recommend|recommends|recommended|suggest|suggests|suggested|decide|decides|"
        r"decided|prefer|prefers|preferred|want|wants|wanted|claim|claims|claimed|"
        r"mentioned|meant|asked|ask|asking)\b",
        _src,
        re.IGNORECASE,
    ):
        name, verb = m.group(1), m.group(2)
        node = _participant_by_name(graph, name)
        if node is None:
            res.unresolved.append(name)
            continue
        relation = _relation_for_verb(verb)
        stmts = graph.attributed_statements(node.key, relation=relation, active_only=True, limit=5)
        if not stmts and relation == "said":
            stmts = graph.attributed_statements(node.key, active_only=True, limit=5)
        if stmts:
            res.referents[f"{name.lower()}-said"] = node
            res.statements.extend(stmts[:5])
        else:
            res.unresolved.append(f"{name} said")

    # 3) "your recommendation / what you said" style.
    m = re.search(r"\b(your|my)\s+(recommendation|suggestion|opinion|choice|advice|decision|pick)\b", low)
    if m:
        who = "participant:kio" if m.group(1) == "your" else "participant:user"
        stmts = graph.attributed_statements(who, relation="said", stance="assertion")
        if stmts:
            res.statements.extend(stmts[:4])
        else:
            res.unresolved.append(m.group(0))

    # 4) Descriptive references: "the X / my X / that X", "the other one".
    for m in re.finditer(r"(?:the|my|your|our|their|his|her|its|that|this|these|those)\s+([a-z][a-z0-9\- ]{1,24})", low):
        noun = m.group(1).strip()
        # the greedy noun class swallows a trailing reporting verb
        # ('the quibble-bot say') — strip it so the noun is the entity only.
        noun = re.sub(r"\s+(said|says|say|told|believes|believed|thinks|thought|think|prefers|preferred|recommend|recommends|recommended|wants|wanted|decide|decides|decided|suggest|suggested|claims|claimed|is|are|was|were)\b$", "", noun).strip()
        if not noun or re.fullmatch(r"(one|thing|person|time|way|reason|point)", noun):
            continue
        tokens = set(re.findall(r"[a-z0-9]+", noun))
        cands = [n for n in (others + third_party) if _desc_match(n, tokens)]
        target = _pick(cands, last_mention)
        if target is not None:
            res.referents[m.group(0)] = target
            res.referents.setdefault(noun, target)
        elif len(tokens) >= 2 and not any(t in low for t in (" how ", " why ", " what is ", " what's ")):
            # A description that names nothing in the graph is an unresolved
            # referent (Planner may ask rather than guess).
            res.unresolved.append(m.group(0).strip())
        # Attribution via a resolved description: "what did the quibble-bot
        # say" — the reporting verb directly follows the (stripped) noun.
        if target is not None and target.kind == "participant" and not res.statements:
            vm = re.search(re.escape(noun) + r"\s+(said|says|say|told|believes|believed|thinks|thought|think|prefers|preferred|recommend|recommends|recommended|wants|wanted|decide|decides|decided|suggest|suggested)\b", low)
            if vm:
                stmts = graph.attributed_statements(target.key, relation=_relation_for_verb(vm.group(1)))
                if not stmts:
                    stmts = graph.attributed_statements(target.key)
                if stmts:
                    res.statements.extend(stmts[:5])

    # 5) "the first/second/other one" — order by activation.
    for m in re.finditer(r"(?:the\s+)?(first|second|third|last|other|newer|older|previous|next)\s+(one|person|thing|item)?\b", low):
        rank = m.group(1)
        pool = others or (third_party + non_participants)
        if rank in ("first", "last", "newer", "older", "previous", "next"):
            if pool:
                res.referents[m.group(0)] = pool[0] if rank in ("first", "newer", "previous") else pool[-1]

    # 6) "its <noun>" — noun of an anchor node (founder of the company).
    m = re.search(r"\bits\s+([a-z][a-z0-9\- ]{1,20})", low)
    if m and "its" in res.referents:
        anchor = res.referents["its"]
        noun_tokens = set(re.findall(r"[a-z0-9]+", m.group(1)))
        linked = []
        for l in graph.links_for(anchor.id):
            other_id = l.target_id if l.source_id == anchor.id else l.source_id
            other = graph.get_node(other_id)
            if other and _desc_match(other, noun_tokens):
                linked.append(other)
        t = _pick(linked)
        if t is not None:
            res.referents[m.group(0)] = t

    return res


_SAY_PATTERN_WORDS = frozenset(
    "said says say told tells believe believes believed thinks thought think "
    "prefer prefers preferred recommend recommends recommended suggest suggests "
    "suggested want wants wanted decide decides decided claim claims claimed "
    "mentioned agreed disagreed meant means know knows knew "
    "ask asked asks asking discuss discussed talking talked chatting chatted ".split()
)


def _relation_for_verb(verb: str) -> Optional[str]:
    if verb in ("prefers", "preferred"):
        return "prefers"
    if verb in ("recommended", "recommends"):
        return "recommends"
    if verb in ("decided", "decides"):
        return "decides"
    return "said"


def _stance_for_verb(verb: str) -> Optional[str]:
    if verb in ("wants", "wanted"):
        return "desire"
    if verb in ("believes", "believed", "thinks", "thought"):
        return "assertion"
    return None


def _participant_for_who(graph: SemanticGraph, who: str) -> Optional[SemanticNode]:
    key = KIO_KEY if who == "you" else USER_KEY if who == "i" else None
    if key:
        return graph.get_node_by_key(key)
    return None


def _participant_by_name(graph: SemanticGraph, name: str) -> Optional[SemanticNode]:
    """Resolve a capitalized name to a graph participant (exact key, then
    case-insensitive name/alias match, then token overlap). None when the
    name is not a known conversational participant."""
    try:
        import re as _re
        norm = _re.sub(r"[^a-z0-9]+", "", (name or "").lower())
        if len(norm) < 2:
            return None
        node = graph.get_node_by_key(f"participant:{norm}")
        if node is not None and node.status != "forgotten":
            return node
        low = (name or "").lower()
        for n in graph.all_active_nodes():
            if n.kind != "participant":
                continue
            if (n.name or "").lower() == low:
                return n
            for a in (n.meta.get("aliases") or []):
                if a.lower() == low:
                    return n
        # Token overlap for multi-word names ("Zorbion Dynamics").
        tokens = set(_re.findall(r"[a-z0-9]+", low))
        if len(tokens) >= 2:
            for n in graph.all_active_nodes():
                if n.kind != "participant":
                    continue
                nt = set(_re.findall(r"[a-z0-9]+", (n.name or "").lower()))
                if nt and tokens and (nt & tokens):
                    return n
    except Exception:
        pass
    return None


def _pick(cands: Sequence[SemanticNode], last_mention=None) -> Optional[SemanticNode]:
    """Pick the single best candidate; ambiguous ties stay unresolved.

    Tie-break is last-MENTION recency (link id), not node creation order:
    the participant/entity mentioned most recently wins; a genuine same-turn
    tie (identical last-mention) stays unresolved. Candidates are deduped by
    node id (the same node can reach the pool through several paths)."""
    uniq = []
    seen = set()
    for n in cands:
        if n.id not in seen:
            seen.add(n.id)
            uniq.append(n)
    if not uniq:
        return None
    if len(uniq) == 1:
        return uniq[0]
    lm = last_mention or {}
    ranked = sorted(uniq, key=lambda n: lm.get(n.id, 0))
    best = ranked[-1]
    second = ranked[-2]
    if lm.get(best.id, 0) == lm.get(second.id, 0):
        return None
    return best


_ROLE_ONLY = re.compile(r"^(friend|colleague|client|teammate|teacher|parent|brother|sister|developer|coworker|boss|partner|roommate|neighbor|manager|mentor|guy|dude|someone|somebody)$", re.I)


def render_references(res: Resolution) -> str:
    """Render resolved references + retrieved statements into a prompt block."""
    lines = []
    if res.referents:
        items = []
        role_only = []
        for surf, node in res.referents.items():
            if surf in ("its",) or surf.endswith("-said"):
                continue
            items.append(f"{surf!r} -> {node.name} ({node.kind})")
            # Guardrail: a participant known only by role ("my friend", "a
            # colleague") has no established identity — never let the model
            # invent a name, occupation, or personal detail for it.
            if node.kind == "participant" and _ROLE_ONLY.match(node.name or ""):
                role_only.append(node.name)
        if items:
            lines.append("Resolved references in the user's message:\n" + "\n".join(f"- {i}" for i in items))
        if role_only:
            lines.append(
                "Identity guardrail: " + ", ".join(sorted(set(role_only)))
                + " is known ONLY by role — no name, appearance, or personal "
                "details have been established. Never invent a name or identity "
                "for them."
            )
    if res.statements:
        parts = []
        for s in res.statements[:5]:
            who = s.attributed_to.split(":", 1)[-1]
            parts.append(f"{who}: \"{s.target_name}\"")
        lines.append("Retrieved from the graph (attributed statements):\n" + "\n".join(f"- {p}" for p in parts))
    return "\n\n".join(lines)
