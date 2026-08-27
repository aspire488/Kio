"""decomposer.py — utterance -> semantic graph ops (FINAL architecture).

One message can simultaneously ask, inform, correct, reject, commit,
delegate, compare, plan and change an existing goal. We therefore never
force ONE intent label: we produce a SET of graph ops (upserts + links with
universal metadata) and a set of intent flags, then let the Planner decide.

Rules:
- Attribution is conservative. If no clear attributor exists, NO link is
  created (the Planner may ask instead of guessing).
- User, KIO and third parties are symmetric participant nodes.
- Corrections SUPERSEDE (via graph.record_statement supersede_prior) —
  never reset the conversation.
- No domain knowledge anywhere: extraction is grammar/structural only.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .graph import KIO_KEY, USER_KEY, SemanticGraph

# Third-party reporting verbs (grammar, not domain routing).
_REPORT_VERB = re.compile(
    r"\b(said|says|told|believes|believed|thinks|thought|prefers|preferred|"
    r"recommended|recommends|wants|wanted|decided|decides|suggested|suggests|"
    r"mentioned|claimed|claims|agreed|disagreed|meant|knows|knew)\b"
)

_PRONOUN_VERB = re.compile(
    r"\b(he|she|they)\s+(said|says|believes|believed|thinks|thought|prefers|"
    r"preferred|recommended|recommends|wants|wanted|decided|decides|suggested|"
    r"claimed|claims|agreed|disagreed|meant)\b"
)

_INTRO = re.compile(
    r"\b(?:my|our)\s+(?:friend|colleague|client|teammate|teacher|parent|brother|"
    r"sister|developer|coworker|boss|partner|roommate|neighbor|manager|mentor)\b"
)

# "my friend Alex said" — the role noun followed by a capitalized name.
_INTRO_ROLE_NAME = re.compile(
    r"\b(?:my|our)\s+(friend|colleague|client|teammate|teacher|parent|brother|"
    r"sister|developer|coworker|boss|partner|roommate|neighbor|manager|mentor)\s+"
    r"([A-Z][a-zA-Z]{2,20})\b",
    re.I,
)

# "the quibble-bot said / claims ..." — lowercase or invented entities.
_THE_ENTITY_VERB = re.compile(
    r"\bthe\s+([a-z][a-z0-9\-]{1,24})\s+(said|says|told|believes|believed|thinks|thought|"
    r"claims|claimed|wants|wanted|prefers|preferred|recommended|recommends|decided|decides|suggested)\b"
)

# Proper-name attribution: "<Name> said/ thinks/ wants ..." (capitalized word
# before a reporting verb). An optional SINGLE lowercase adverb slot is
# allowed between the name and the verb ("Raj ALSO believes") — adverbs are
# an open grammar class, not a phrase list, and missing them silently drops
# whole third-party attributions in any domain (live holdout: "My supervisor
# Raj also believes the fossils..." lost Raj entirely across geology/cooking/
# agriculture). Sentence-initial interrogatives (What/Who/When/...) are
# capitalized by writing convention, never proper names — excluded so "What
# believes X" can never mint a participant named "What".
_QUESTION_WORDS = {"what", "who", "when", "where", "why", "how", "which", "hey", "ok", "okay", "wait"}
_NAME_VERB = re.compile(r"\b([A-Z][a-zA-Z]{2,20})\s+(?:[a-z]{2,12}\s+)?(said|says|told|believes|believed|thinks|thought|wants|wanted|preferred|prefers|recommended|recommends|decided|decides|claimed|claims|suggested|suggests|mentioned)\b")

_CORRECTION = re.compile(
    r"^\s*(no|nope|wait|actually|hold on|correction|scratch that|never mind|"
    r"nevermind|forget (that|it|what i said)|i changed my mind|on second thought|"
    r"don't send that|dont send that|not that|wrong)\b"
)

_PREFERENCE = re.compile(
    r"\bi\s+(prefer|like|love|dislike|hate|enjoy|favor|favour)\s+(.+?)\s*(?:\.|!|\?|$)"
)
# "I'm leaning toward X" / "I'm leaning towards Y" — a tentative directional
# preference (not yet a decision, but user state that must be recorded so
# "what did I say about the planner?" resolves). Same relation family.
_LEANING = re.compile(
    r"\bi(?:'m|\s+am)\s+leaning\s+toward(?:s)?\s+(.+?)\s*[.!?]*$",
    re.I,
)
_DECISION = re.compile(
    r"\bi\s+(decided|chose|choose|pick|picked|selected|select|settled on)\s+(.+?)\s*(?:\.|!|\?|$)"
)
_INTENTION = re.compile(
    r"\bi(?:'m|'ll|m| am| will| will| would)?\s+(?:am\s+)?"
    r"(?:want|need|intend|plan|planning|going|would like|will|'ll|just)\s+(?:to\s+)?(.+?)\s*(?:\.|!|\?|$)",
    re.I,
)
# Research-intent statements: "I'm researching a company called X", "I'm
# looking into Y", "I'm investigating Z". The user's OWN research goal must
# become a user-attributed statement so "what did I just ask about?" / "what
# was I researching?" resolves from the graph (live failure: the Zorbion
# research intent was never recorded, so recall fell back to raw history and
# fabricated). General grammar, never a domain list.
_RESEARCH = re.compile(
    r"\bi['\u2019]?m?\s+(?:researching|looking\s+into|investigating|checking\s+out|studying|"
    r"reading\s+up\s+on|exploring)\s+(.+?)\s*(?:\.|!|\?|$)"
)
# "a company called X / an app called Y / an excavation site called Z" — the
# entity named by 'called' is the research subject. The noun before 'called'
# is an OPEN class (company, app, site, dig, formation, oven, ...) — a closed
# list silently misses novel subjects (live holdout: "an excavation site
# called the Maluti Basin dig" kept the WHOLE phrase as subject because
# 'site' was not in the list). General grammar: "a/an <noun-phrase> called
# <Name>".
_CALLED = re.compile(
    r"\b(?:a|an)\s+([a-z][a-z0-9\- ]{1,30}?)\s+called\s+([A-Za-z][A-Za-z0-9\- ]{2,40}?)\s*(?:\.|!|\?|,|$)",
    re.I,
)
_GOAL = re.compile(r"\b(?:my\s+)?(?:goal|plan|objective)\s+is\s+(?:to\s+)?(.+?)\s*(?:\.|!|\?|$)")

# User factual assertions: "The Zephyr-7 draws 42 amps", "The Ferroline oven
# reaches 320 degrees" — a definite subject (the/my/our + noun phrase) with a
# fact-predicate verb. These are USER-ATTRIBUTED observations (FINAL arch:
# user state is anything attributed to the user participant-node), so
# "what did I say about the oven?" resolves from the graph instead of an
# empty store (live holdout: user claims about Zephyr-7 / Ferroline oven /
# Iblis wheat were never recorded, and recall said "I don't have a record").
# Grammar-structural: definite subject + present-tense fact verb + complement.
# NOT a domain list — the verb set is the open fact-predicate class and any
# subject noun qualifies. Questions/commands do not match (no question mark,
# no initial verb).
_USER_FACT_VERBS = re.compile(
    r"\b(draws?|reach(?:es)?|reached|has|have|need|needs|costs?|weighs?|measures?|"
    r"produces?|contains?|runs?|works?|germinates?|grows?|operates?|uses?|takes?|"
    r"holds?|supports?|carries?|peaks?|lasts?|starts?|ends?|opens?|closes?|is|are|was|were)\b"
)
_USER_FACT = re.compile(
    r"^\s*(?:the|my|our)\s+([A-Za-z][A-Za-z0-9\- ]{1,40}?)\s+"
    r"(draws?|reaches?|reached|has|have|need|needs|costs?|weighs?|measures?|produces?|"
    r"contains?|runs?|works?|germinates?|grows?|operates?|uses?|takes?|holds?|supports?|"
    r"carries?|peaks?|lasts?|starts?|ends?|opens?|closes?|is|are|was|were)\s+(.+?)\s*[.!?]*$",
    re.I,
)

# First-person WAIT states ("i'm waiting for X" / "waiting on Y") are user
# state: recorded so "what am I waiting for?" answers from the graph (F-R1)
# and the proactive evaluator DEFERS on them. Grammar-structural, never a
# domain list.
_WAIT_STATE = re.compile(
    r"\bi(?:'m|\s+am)?\s+waiting\s+(?:for|on)\s+(.+?)\s*[.!?]*$",
    re.I,
)

_REMEMBER = re.compile(r"^\s*(remember|note|make a note that|keep in mind)\s+(.+)$", re.I)
# Forget commands tolerate a conversational lead-in ("actually forget X",
# "ok forget it") — the connective is noise, the intent is the same.
_FORGET = re.compile(
    r"^\s*(?:actually|well|so|anyway|okay?|wait|hold\s+on|no|alright|right)?[,!\s]*"
    r"(forget|erase|remove)\s+(.+)$", re.I
)

_QUESTION = re.compile(
    r"(^|\s)(what|why|how|who|when|where|which|is it|does|do you|can you|should i|"
    r"should we|are you|did you|will you|would you)\b|(\?\s*$)"
)
_CURRENT = re.compile(r"\b(latest|now|today|recently|current|what changed|what's new|is this true|did that happen|still)\b")


class Decomposition:
    """Result of decomposing one utterance."""

    __slots__ = ("ops", "intents", "participants", "topics", "note", "project_ops")

    def __init__(self):
        self.ops: List[Dict] = []       # graph ops, applied in order
        self.intents = set()            # ask | inform | correct | commit | reject | delegate | meta
        self.participants: List[str] = []
        self.topics: List[str] = []
        self.note: str = ""
        self.project_ops: List[Dict] = []  # lifecycle transitions {name, status, ...}

    def add(self, op: dict):
        self.ops.append(op)


# ── general PROJECT LIFECYCLE family (lifecycle is metadata, not a router) ──
# First-person active-work statements transition a project's lifecycle:
#   "i'm building X" -> building | "i'm not working on X anymore" -> abandoned
#   "i'm back on X" -> active | "i was thinking about X" -> mentioned (NEVER
#   auto-promoted). Third-party statements, questions, and code dumps never
#   create projects. Status history is preserved by the graph.
_PROJ_BUILD_RE = re.compile(
    r"\bi(?:'m|\s+am)\s+(?:also\s+|still\s+|again\s+|finally\s+)?"
    r"(?:building|working\s+on|developing|making|coding|prototyping|"
    r"rebuilding|refactoring|running|setting\s+up|starting|launching|"
    r"kicking\s+off)\s+(.+)$",
    re.I,
)
_PROJ_RESUME_RE = re.compile(
    r"\bi(?:'m|\s+am)\s+(?:back\s+on|resuming|getting\s+back\s+to)\s+(.+)$",
    re.I,
)
_PROJ_STOP_RE = re.compile(
    r"\bi(?:'m|\s+am)\s+(?:no\s+longer|not)\s+(?:working\s+on|building|developing)\s+(.+)$",
    re.I,
)
_PROJ_DROP_RE = re.compile(
    r"\bi\s+(?:stopped|abandoned|killed|dropped|gave\s+up\s+on|done\s+with|"
    r"scrapped)\s+(?:working\s+on\s+)?(?:the\s+|my\s+|our\s+)?(.+)$",
    re.I,
)
_PROJ_PAUSE_RE = re.compile(
    r"\bi(?:'m|\s+am)?\s+(?:"
    r"(?:paused|pausing|setting\s+aside|put\s+on\s+hold)\s+(?P<a>.+?)|\s*"
    r"(?:put|putting)\s+(?:(?:the|my|our|that|this)\s+)?(?P<b>.+?)\s+on\s+hold"
    r"|(?:put|putting)\s+it\s+on\s+hold\s*"
    r")$",
    re.I,
)
_PROJ_PLAN_RE = re.compile(
    r"\bi(?:'m|\s+am)\s+(?:still\s+)?planning\s+(.+)$",
    re.I,
)
_PROJ_INTEREST_RE = re.compile(
    r"\bi(?:'m|\s+am)\s+interested\s+in\s+(.+)$",
    re.I,
)
_PROJ_MENTION_RE = re.compile(
    r"\bi\s+(?:was|were)\s+thinking\s+about\s+(.+)$",
    re.I,
)
_PROJ_RESEARCH_RE = re.compile(
    r"\bi(?:'m|\s+am)\s+researching\s+(.+)$",
    re.I,
)
_PROJ_FILLER_END = re.compile(
    r"\s*(?:right\s+now|now|again|lately|these\s+days|for\s+(?:real|now)|"
    r"from\s+scratch|as\s+a\s+hobby|on\s+the\s+side|in\s+my\s+free\s+time|"
    r"eventually|soon|seriously|for\s+real)\s*$",
    re.I,
)


def _project_name(phrase: str) -> str:
    name = re.sub(r"^\s*(?:a|an|the|my|our|this|that)\s+", "", phrase.strip(), flags=re.I)
    name = _PROJ_FILLER_END.sub("", name)
    name = re.sub(r"\s+", " ", name).strip(" .,!?;:")
    return name[:90]


_PROJ_CODE_FENCE = re.compile(r"```|(?:\w{40,})|(?:\{[^{}]{80,}\})")

# pure function words only — content nouns (rig, study, build, app) carry
# project identity and must never be stripped from token overlap.
_PROJ_STOP = frozenset(
    "the my our that this these those a an of for with on in at to from by "
    "and or but is are was were be been it its their his her me now today "
    "tomorrow later about around over under new old next last first again "
    "back still also so just very really".split()
)


def _extract_project_ops(low: str) -> List[Dict]:
    """Return lifecycle transitions for first-person active-work statements."""
    if not low or "?" in low:
        return []
    if _PROJ_CODE_FENCE.search(low) or len(low) > 300:
        return []
    out: List[Dict] = []
    m = _PROJ_BUILD_RE.search(low)
    if m:
        name = _project_name(m.group(1))
        if len(name) >= 3:
            out.append({"op": "project_status", "name": name, "status": "building",
                        "confidence": 0.85})
    m = _PROJ_RESUME_RE.search(low)
    if m:
        name = _project_name(m.group(1))
        if len(name) >= 3:
            out.append({"op": "project_status", "name": name, "status": "active",
                        "confidence": 0.85})
    m = _PROJ_STOP_RE.search(low)
    if m:
        name = _project_name(m.group(1))
        if len(name) >= 3:
            out.append({"op": "project_status", "name": name, "status": "abandoned",
                        "confidence": 0.8})
    m = _PROJ_DROP_RE.search(low)
    if m:
        name = _project_name(m.group(1))
        if len(name) >= 3:
            out.append({"op": "project_status", "name": name, "status": "abandoned",
                        "confidence": 0.8})
    m = _PROJ_PAUSE_RE.search(low)
    if m:
        _obj = m.group("a") or m.group("b") or ""
        name = _project_name(_obj)
        if len(name) >= 3:
            out.append({"op": "project_status", "name": name, "status": "paused",
                        "confidence": 0.8})
    m = _PROJ_PLAN_RE.search(low)
    if m:
        name = _project_name(m.group(1))
        if len(name) >= 3:
            out.append({"op": "project_status", "name": name, "status": "planning",
                        "confidence": 0.7})
    m = _PROJ_INTEREST_RE.search(low)
    if m:
        name = _project_name(m.group(1))
        if len(name) >= 3:
            out.append({"op": "project_status", "name": name, "status": "interested",
                        "confidence": 0.6})
    m = _PROJ_MENTION_RE.search(low)
    if m:
        name = _project_name(m.group(1))
        if len(name) >= 3:
            # a casual mention is never auto-promoted to an active project
            out.append({"op": "project_status", "name": name, "status": "mentioned",
                        "confidence": 0.4})
    m = _PROJ_RESEARCH_RE.search(low)
    if m:
        name = _project_name(m.group(1))
        if len(name) >= 3:
            out.append({"op": "project_status", "name": name, "status": "researching",
                        "confidence": 0.7})
    # dedupe: keep the strongest status per name
    best: Dict[str, Dict] = {}
    for op in out:
        n = op["name"].lower()
        if n not in best or op["status"] in ("building", "active", "abandoned"):
            best[n] = op
    return list(best.values())


# Third-person project-status declarations ("that project is dead now",
# "the lunar greenhouse is done", "X is on hold") — the target is resolved
# against the graph's project nodes (named match, else the MOST RECENTLY
# active project — activation, not a phrase list). Questions and code dumps
# never transition projects.
_PROJ_DECL_RE = re.compile(
    r"\b(?:that|this|the|my|our)\s+(?:whole\s+|entire\s+|old\s+|new\s+)?"
    r"(?:project|prototype|build|thing|app|idea|concept)\s+"
    r"(?:is|'s|has\s+gone|is\s+going|turned\s+out)\s+"
    r"(dead|over|done|finished|abandoned|cancelled|canceled|shelved|kaput|"
    r"on\s+hold|paused|on\s+pause|in\s+the\s+bin|history)\b",
    re.I,
)
_PROJ_NAMED_DEAD_RE = re.compile(
    r"\b(?:(?:the|my|our)\s+)?([A-Za-z][A-Za-z0-9 ._-]{3,60}?)\s+"
    r"(?:is|'s|has\s+gone|is\s+going)\s+"
    r"(dead|over|done|finished|abandoned|cancelled|canceled|shelved|kaput|"
    r"on\s+hold|paused|history)\b",
    re.I,
)

# a bare declaration can CREATE the project when the name is a genuine proper
# name ("MediMind is on hold" -> project MediMind paused) — capitalized token
# or >=2 content words — mirroring the first-person creation path. Generic
# single lowercase heads ("the build is on hold") never create.
_PROJ_PROPER_RE = re.compile(r"[A-Z][A-Za-z0-9]{2,}")


def _looks_proper(name: str) -> bool:
    if _PROJ_PROPER_RE.search(name):
        return True
    toks = [t for t in re.findall(r"[a-z0-9]+", name.lower())
            if len(t) >= 3 and t not in _PROJ_STOP]
    return len(toks) >= 2


def _extract_project_decl_ops(graph: Optional[SemanticGraph], low: str,
                              text: str = "") -> List[Dict]:
    """Third-person status transitions resolved against the graph's projects.
    Returns [] when the reference cannot be resolved (never invents a target).

    `text` (original case) is used ONLY to judge whether a bare declaration's
    name is a proper name ("MediMind") — the lowercase copy cannot.
    """
    if not low or "?" in low or not graph:
        return []
    if _PROJ_CODE_FENCE.search(low) or len(low) > 200:
        return []
    status = None
    name = None
    m = _PROJ_DECL_RE.search(low)
    if m:
        st = m.group(1).lower()
        status = "paused" if st in ("on hold", "on pause", "paused") else "abandoned"
        # "that/the project" -> the most recently ACTIVE project (activation)
        try:
            active = graph.active_projects()
        except Exception:
            active = []
        if active:
            name = active[0].name
        if not name:
            return []
    else:
        m = _PROJ_NAMED_DEAD_RE.search(text or low)
        if not m:
            return []
        cand = m.group(1).strip()
        st = m.group(2).lower()
        status = "paused" if st in ("on hold", "on pause", "paused") else "abandoned"
        # named target: identity-unify against existing projects. Substring
        # containment alone misses interleaved tokens ("nexus rig" vs "nexus
        # kitesurfing rig for foiling"); use significant-token overlap — the
        # same general identity rule as the graph itself.
        try:
            cand_toks = {t for t in re.findall(r"[a-z0-9]+", cand.lower())
                         if len(t) >= 3 and t not in _PROJ_STOP}
            best, best_score = None, 0
            for pr in graph.all_projects():
                norm = re.sub(r"[^a-z0-9]+", "", cand.lower())
                pnorm = re.sub(r"[^a-z0-9]+", "", pr.name.lower())
                score = 0
                if norm and (norm in pnorm or pnorm in norm):
                    score = max(len(norm), len(pnorm))
                else:
                    ptoks = {t for t in re.findall(r"[a-z0-9]+", pr.name.lower())
                             if len(t) >= 3 and t not in _PROJ_STOP}
                    shared = len(cand_toks & ptoks)
                    if cand_toks and shared >= 2 and shared * 2 >= max(len(cand_toks), 2):
                        score = 100 + shared
                if score > best_score:
                    best_score = score
                    best = pr
            if best is not None:
                name = best.name
        except Exception:
            name = None
        if not name and _looks_proper(cand):
            # a genuine proper name declared with a status creates the
            # project at that status ("MediMind is on hold" -> MediMind
            # paused), mirroring the first-person creation path. Generic
            # single-word lowercase heads never create.
            name = cand
        if not name:
            return []
    return [{"op": "project_status", "name": name, "status": status,
             "confidence": 0.8}]


def decompose(graph: SemanticGraph, text: str, raw_text: str = "") -> Decomposition:
    """Decompose `text` into graph ops + intent flags. Never throws."""
    d = Decomposition()
    low = (text or "").strip().lower()
    if not low:
        return d

    user_node = graph.ensure_participant("user")
    kio_node = graph.ensure_participant("kio")

    # ── corrections (must run first: they reshape prior state) ────────────
    _corr_m = _CORRECTION.search(low)
    if _corr_m:
        d.intents.add("correct")
        d.note = "correction"
        # Supersede the SINGLE most recent active statement by ANY participant
        # (the thing being corrected — Alex's claim, KIO's claim, or the user's
        # own prior claim). History is preserved via status, never deleted.
        prior = graph.recent_links(limit=1, active_only=True)
        if prior and prior[0].attributed_to:
            d.add({"op": "supersede", "link_id": prior[0].id})
        d.add({"op": "correction_seen"})
        # The correction usually carries the corrected claim itself
        # ("Actually it is on Thursday now"). When it reports what a THIRD
        # party said ("Actually I think he said Thursday"), the corrected
        # claim belongs to that participant, not the user — participant-
        # symmetric correction. A single unambiguous third party is required;
        # otherwise the user owns the claim.
        rest = low[_corr_m.end():].strip().lstrip(",:-).").strip()
        if rest and len(rest) >= 4:
            _corr_target = None
            # Participant-symmetric correction: the correction reports what a
            # THIRD party said/believes, using the reporting-verb class OR a
            # self-correction frame ("she corrected herself", "he changed his
            # mind", "they now think"). A single unambiguous third party is
            # required; otherwise the user owns the claim. The optional adverb
            # slot covers "she NOW thinks" (same open grammar class as name
            # attribution above). Live holdout: "Actually she corrected
            # herself — she now thinks they're Triassic." was recorded as the
            # USER's claim because 'corrected herself' was not a recognized
            # reporting frame.
            _cref = re.search(
                r"\b(?:i\s+think\s+)?(?:he|she|they)\s+(?:[a-z]{2,12}\s+)?"
                r"(?:said|says|told|claimed|claims|corrected\s+(?:himself|herself|themselves)|"
                r"changed\s+(?:his|her|their)\s+mind|now\s+(?:thinks|believes)|thinks|believes|"
                r"realized|realised|decided|reconsiders?)\s+(.+)$",
                rest,
            )
            if _cref:
                third = [n for n in graph.all_active_nodes()
                         if n.kind == "participant" and n.key not in (USER_KEY, KIO_KEY)]
                if len(third) == 1:
                    _corr_target = third[0].key
                    rest = _cref.group(1).strip()
                    # Strip a trailing reporting frame from the captured claim
                    # ("she corrected herself — she now thinks they're
                    # triassic" -> "they're triassic"). The actual content is
                    # what follows the last reporting verb, not the frame.
                    _tail = re.search(
                        r"(?:\s*(?:—|-|,)\s*(?:he|she|they)\s+(?:now\s+)?(?:thinks?|believes?|realized|realised)\s+)?(.+)$",
                        rest,
                    )
                    if _tail and _tail.group(1).strip():
                        rest = _tail.group(1).strip()
            d.add({"op": "statement",
                   "attributor": _corr_target or USER_KEY,
                   "claim": rest[:200], "stance": "assertion", "verb": "said",
                   "supersede_prior": bool(_corr_target)})

    # ── participants ──────────────────────────────────────────────────────
    # "my friend Alex said X": ONE participant (Alex) with alias 'friend' —
    # the role is data on the node, never a second participant that would
    # make 'he' ambiguous between the role and the name.
    _named_roles = {}
    for m in _INTRO_ROLE_NAME.finditer(text or ""):
        _named_roles[m.group(2).lower()] = m.group(1)
    # "the <entity> said/claims ..." — invented or lowercase entities are
    # ordinary participants too (zero architecture change for new domains).
    for m in _THE_ENTITY_VERB.finditer(low):
        entity = m.group(1)
        if entity in {"ai", "bot"} or len(entity) < 2:
            continue
        node = graph.ensure_participant(entity, aliases=[entity])
        if entity not in {p.lower() for p in d.participants}:
            d.participants.append(entity)
        claim = _claim_after_verb(low, m.end())
        if claim:
            d.add({"op": "statement", "attributor": node.key, "claim": claim,
                   "stance": "assertion", "verb": m.group(2)})
        d.add({"op": "ensure_participant", "name": entity, "node": node})
    _named_role_values = set(_named_roles.values())
    for m in _INTRO.finditer(low):
        role = m.group(0).split(None, 1)[-1]
        if role in _named_role_values:
            continue  # merged into the named participant below
        node = graph.ensure_participant(role, aliases=[role])
        d.participants.append(node.name)
        d.add({"op": "ensure_participant", "name": role, "node": node})
    # Named third parties: "<Name> said/ thinks ..." — proper-noun before verb.
    for m in _NAME_VERB.finditer(text or ""):
        name, verb = m.group(1), m.group(2)
        if name.lower() in _QUESTION_WORDS:
            continue
        role_alias = _named_roles.get(name.lower())
        aliases = [name.lower()] + ([role_alias] if role_alias else [])
        node = graph.ensure_participant(name, aliases=aliases)
        if name.lower() not in {p.lower() for p in d.participants}:
            d.participants.append(name)
        claim = _claim_after_verb(text or "", m.end())
        if claim:
            stance = _stance(verb)
            d.add({"op": "statement", "attributor": node.key, "claim": claim,
                   "stance": stance, "verb": verb})
        d.add({"op": "ensure_participant", "name": name, "node": node})

    # Pronoun third-party statements: "he said X" / "she thinks Y"
    # (skipped when a correction already re-attributed the same claim above).
    if d.note != "correction":
        for m in _PRONOUN_VERB.finditer(low):
            who, verb = m.group(1), m.group(2)
            # Resolver owns pronoun targets; if a single third party exists, use it.
            third = [n for n in graph.all_active_nodes()
                     if n.kind == "participant" and n.key not in (USER_KEY, KIO_KEY)]
            if len(third) == 1:
                claim = _claim_after_verb(low, m.end())
                if claim:
                    d.add({"op": "statement", "attributor": third[0].key,
                           "claim": claim, "stance": _stance(verb), "verb": verb})

    # ── user commitments / preferences / decisions (user-attributed) ──────
    for pat, stance, rel in (
        (_PREFERENCE, "assertion", "prefers"),
        (_DECISION, "commitment", "decides"),
        (_INTENTION, "desire", "wants"),
        (_GOAL, "intention", "wants"),
        (_LEANING, "assertion", "prefers"),
    ):
        m = pat.search(low)
        if m:
            content = m.group(1) if m.lastindex == 1 else m.group(m.lastindex)
            d.intents.add("commit" if stance in ("commitment", "intention") else "inform")
            d.add({"op": "statement", "attributor": USER_KEY,
                   "claim": f"{rel.split('.')[0]}: {content.strip()[:160]}",
                   "stance": stance, "verb": rel})

    # ── research intents (user-attributed, symmetric with commitments) ────
    # "I'm researching a company called Zorbion Dynamics" -> the user's own
    # research goal is a user-attributed statement + the entity is a topic
    # node. Recall ("what did I just ask about?") then resolves from the
    # graph instead of raw history. Never a domain list — any noun-ish
    # subject qualifies.
    _research_subject = None
    m = _RESEARCH.search(low)
    if m:
        _research_subject = m.group(1).strip()
        # Refine with the 'called X' name ONLY inside a genuine research
        # sentence ("I'm researching a company called X" -> "X"). A bare
        # 'called' in a NON-research sentence ("I'm planning to record an EP
        # called Static Bloom") is a goal's object — never a research intent
        # (live holdout contamination: 'an EP called Static Bloom' became a
        # fake 'researching: Static Bloom' statement alongside the real goal).
        cm = _CALLED.search(text or "")
        if cm and cm.group(2).lower() in _research_subject.lower():
            _research_subject = cm.group(2).strip()
    if _research_subject and len(_research_subject) >= 3:
        d.add({"op": "statement", "attributor": USER_KEY,
               "claim": f"researching: {_research_subject[:160]}",
               "stance": "intention", "verb": "wants"})
        d.intents.add("inform")
        # The entity becomes a topic node ("back to Zorbion" / "What about
        # Zorbion?" resolves). Use the FULL 'called X' name when present, else
        # the whole research subject — never just the last word ("Zorbion
        # Dynamics" -> "Dynamics" would be wrong).
        _cm = _CALLED.search(text or "")
        _ent = (_cm.group(2) if _cm else _research_subject)
        _ent = _ent.strip(" .,;!?")
        if len(_ent) >= 3:
            d.add({"op": "ensure_topic", "name": _ent, "node": None})

    # ── user factual assertions (definite subject + fact verb) ────────────
    # "The Zephyr-7 draws 42 amps" -> user-attributed observation + topic
    # node, so later "what did I say about the Zephyr-7?" resolves from the
    # graph. Bounded: question marks / imperative-first forms never match.
    # SKIPPED when the turn already carries a THIRD-PARTY attribution — "My
    # supervisor Raj also believes the fossils are old" is Raj's claim, not
    # the user asserting "the fossils are old" (the subject capture would
    # greedily swallow the reporting verb and double-record). A sentence
    # reporting someone else's statement is not the user's own factual claim.
    _has_third_party_attr = any(
        op.get("attributor") and op.get("attributor") != USER_KEY
        for op in d.ops
    )
    mf = _USER_FACT.search(low)
    if mf and "?" not in (text or "") and not _CORRECTION.match(low) and not _has_third_party_attr:
        _subject = mf.group(1).strip()
        _pred = mf.group(3).strip()
        if len(_subject) >= 3 and len(_pred) >= 2:
            d.add({"op": "statement", "attributor": USER_KEY,
                   "claim": f"{_subject}: {_pred[:140]}",
                   "stance": "observation", "verb": "said"})
            d.intents.add("inform")
            d.add({"op": "ensure_topic", "name": _subject[:60], "node": None})

    # ── wait states (first-person, user-attributed) ──────────────────────
    m = _WAIT_STATE.search(low)
    if m:
        _subject = m.group(1).strip()
        if len(_subject) >= 3:
            d.add({"op": "statement", "attributor": USER_KEY,
                   "claim": f"waiting on: {_subject[:140]}",
                   "stance": "observation", "verb": "said"})
            d.intents.add("inform")

    # ── durable memory ────────────────────────────────────────────────────
    m = _REMEMBER.search(text or "")
    if m:
        d.add({"op": "remember", "text": m.group(2).strip()[:200], "durable": True})
        d.intents.add("inform")
    m = _FORGET.search(text or "")
    if m:
        target = m.group(2).strip()
        d.add({"op": "forget", "target": target[:120]})
        d.intents.add("reject")

    # ── topics (open class: any notable noun-ish head, capped) ────────────
    for t in _extract_topics(low):
        node = graph.ensure_node("topic", t)
        d.topics.append(node.name)
        d.add({"op": "ensure_topic", "name": t, "node": node})

    # ── intent flags ──────────────────────────────────────────────────────
    if _QUESTION.search(low):
        d.intents.add("ask")
    if _CURRENT.search(low):
        d.intents.add("current")
    if _REMEMBER.search(text or "") or _FORGET.search(text or ""):
        pass  # handled above
    if not d.intents and not d.ops:
        d.intents.add("chat")
    if not d.intents and d.ops:
        d.intents.add("inform")
    if re.search(r"\b(send|reply|draft|email|message|tell)\b", low):
        d.intents.add("delegate")
    # ── project lifecycle (general, first-person active-work statements) ──
    # Never from third-party statements or questions. Guards: a turn that
    # reports what SOMEONE ELSE said is not the user's active work.
    if not d.participants:
        for _pop in _extract_project_ops(low):
            d.project_ops.append(_pop)
        # third-person status declarations ("that project is dead now",
        # "the lunar greenhouse is on hold") resolve against graph projects
        for _pop in _extract_project_decl_ops(graph, low, text=text or raw_text):
            d.project_ops.append(_pop)
    return d


def _claim_after_verb(text: str, pos: int) -> Optional[str]:
    rest = (text or "")[pos:].strip().lstrip(":,.-").strip()
    if not rest:
        return None
    # bound the c
    m = re.match(r"(.+?)(?:[.!?]\s|$)", rest)
    claim = (m.group(1) if m else rest).strip()
    if len(claim) < 2:
        return None
    return claim[:200]


def _stance(verb: str) -> str:
    if verb in ("wants", "wanted", "prefers", "preferred"):
        return "desire"
    return "assertion"


# Pronouns / pure-discourse words must never become topic nodes (live:
# "...about you" created a degenerate topic node named "you" that polluted
# activation and reference resolution). Topic extraction is open-class but
# must reject function words.
_TOPIC_STOP = frozenset(
    "a an the it this that these those you me him her them us we i my your our his "
    "its their what which who whom when where why how is are was were be been being "
    "to for with from by at on in of and or but so if then there here it's that's".split()
)


def _extract_topics(low: str) -> List[str]:
    """Conservative open-class topic extraction: multi-word heads after
    discourse markers and question words. Never a domain vocabulary — any
    noun-ish phrase qualifies. Function words (pronouns, prepositions) are
    rejected so 'about you' never becomes a topic node."""
    out = []
    for m in re.finditer(r"\b(?:about|regarding|concerning|back to|discuss|discussing|topic of)\s+([a-z0-9][a-z0-9\-' ]{1,40})", low):
        phrase = m.group(1).strip()
        phrase = re.split(r"\b(?:and|then|please|with)\b", phrase)[0].strip(" .,!?")
        _words = [w for w in re.findall(r"[a-z0-9]+", phrase) if w not in _TOPIC_STOP]
        if _words and 2 <= len(phrase) <= 40 and phrase not in out:
            out.append(phrase)
    for m in re.finditer(r"\bwhat about\s+([a-z0-9][a-z0-9\-' ]{1,40})", low):
        phrase = m.group(1).strip(" .,!?")
        _words = [w for w in re.findall(r"[a-z0-9]+", phrase) if w not in _TOPIC_STOP]
        if _words and 2 <= len(phrase) <= 40 and phrase not in out:
            out.append(phrase)
    return out[:6]


def apply_ops(graph: SemanticGraph, d: Decomposition) -> None:
    """Apply a decomposition's ops to the graph. Idempotent + safe."""
    for op in d.ops:
        kind = op.get("op")
        try:
            if kind == "ensure_participant":
                graph.ensure_participant(op["name"])
            elif kind == "ensure_topic":
                graph.ensure_node("topic", op["name"])
            elif kind == "statement":
                graph.record_statement(
                    op["attributor"], op["claim"], stance=op.get("stance", "assertion"),
                    relation=_relation_for(op.get("verb", "said")),
                    supersede_prior=bool(op.get("supersede_prior", False)),
                    provenance="decomposer",
                )
            elif kind == "supersede":
                graph.supersede(op["link_id"])
            elif kind == "remember":
                graph.ensure_node("concept", op["text"], meta={"durable": True})
            elif kind == "forget":
                key = f"participant:{_norm_forget(op['target'])}"
                if not graph.forget(key):
                    for k in (f"topic:{_norm_forget(op['target'])}",
                              f"concept:{_norm_forget(op['target'])}"):
                        if graph.forget(k):
                            break
            elif kind == "correction_seen":
                pass
            elif kind == "project_status":
                graph.set_project_status(
                    op["name"], op["status"],
                    confidence=float(op.get("confidence", 0.7)),
                    provenance="decomposer",
                )
        except Exception:
            continue
    # project lifecycle ops ride along after regular ops
    for _pop in d.project_ops:
        try:
            graph.set_project_status(
                _pop["name"], _pop["status"],
                confidence=float(_pop.get("confidence", 0.7)),
                provenance="decomposer",
            )
        except Exception:
            continue


def _norm_forget(t: str) -> str:
    t = re.sub(r"^(the|my|our|a|an)\s+", "", t.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def _relation_for(verb: str) -> str:
    if verb in ("prefers", "preferred", "like", "love", "dislike"):
        return "prefers"
    if verb in ("decided", "decides", "chose", "choose", "pick", "picked"):
        return "decides"
    if verb in ("wants", "wanted", "need", "intend", "plan"):
        return "wants"
    if verb in ("recommended", "recommends", "suggested", "suggests"):
        return "recommends"
    return "said"
