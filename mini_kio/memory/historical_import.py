"""
historical_import.py — canonical import of the ChatGPT history export into
the semantic graph (provenance-aware, temporal, confidence-ranked).

The export is a SOURCE, never the personality database and never a giant
prompt. Every extracted item becomes a USER-ATTRIBUTED claim in the canonical
Node/Link graph carrying:

  - provenance:  "chatgpt_export:<conversation_id>:<message_id>"
  - event_time:  the original message timestamp (temporal metadata)
  - confidence:  recency + repetition + explicitness, capped
  - status:      active (a later live statement supersedes by recency at
                 query time; the historical truth is never destroyed)

The evidence categories reuse the SAME relation vocabulary as the live
semantic decomposer (prefers / decides / wants / said) — no user-specific
rules, no domain routers, no new stored types. The raw conversations remain
available as historical provenance in the export directory and in the import
index.

Idempotent: re-running skips conversations already imported (marked in the
index). The import targets the stable per-user session (`tg_<user_id>`) so
historical and live statements share ONE graph and ONE recall path.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from mini_kio.semantic.graph import SemanticGraph, USER_KEY

logger = logging.getLogger(__name__)

EXPORT_DIR = os.path.join("data", "historical", "chatgpt_export_2026-06-12")
INDEX_PATH = os.path.join("data", "historical", "import_index.json")

# ── general evidence patterns (relation vocabulary shared with decomposer) ─
# User messages only. No entity names, no domains, no phrase tables — these
# are morphological families over first-person statements.
_PREFER_RE = re.compile(
    r"\bi\s+(?:really\s+|definitely\s+|honestly\s+)?"
    r"(?:do\s+)?(?:not\s+)?(prefer|like|love|enjoy|hate|dislike|dont\s+like|don['\u2019]t\s+like)\s+",
    re.I,
)
_DECIDE_RE = re.compile(
    r"\bi\s+(?:'ve\s+|have\s+|just\s+)?(?:decided|chose|chosen|picked|settled\s+on)\s+",
    re.I,
)
_WANT_RE = re.compile(
    r"\bi\s+(?:'m\s+|am\s+|really\s+|definitely\s+|just\s+)?"
    r"(want|wanted|need|needed|plan|planned|planning|intend|intended|hoping|aiming)\s+",
    re.I,
)
_REJECT_RE = re.compile(
    r"\bi\s+(?:no\s+longer\s+|don['\u2019]?t\s+|dont\s+|really\s+)?"
    r"(rejected|abandoned|gave\s+up\s+on|dropped|quit|scrapped|hate|dislike)\s+",
    re.I,
)
# Durable-fact family (mirrors the legacy memory extractor's general
# "my favorite X is Y" / "my X is Y" patterns, minus the per-user framing).
_FAVORITE_RE = re.compile(r"\bmy\s+favorite\s+(.+?)\s+is\s+(.+?)\s*$", re.I)
_CALLME_RE = re.compile(r"\bcall\s+me\s+(.+?)\s*$", re.I)

# Messages that are almost certainly pasted technical content, not personal
# evidence: code fences, very long single lines, JSON blobs.
_CODE_FENCE_RE = re.compile(r"```|(?:\w{40,})|(?:\{[^{}]{80,}\})")
_MAX_EVIDENCE_LEN = 260


def _norm_claim(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).strip(" .,!?;:")


def _message_date(ts: Optional[float]) -> Optional[str]:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
    except Exception:
        return None


def parse_export(directory: str = EXPORT_DIR) -> List[Dict[str, Any]]:
    """Parse every conversations-*.json into ordered conversations.

    Each conversation: {conversation_id, title, create_time, messages:
    [(timestamp, role, text), ...] chronological}. Returns [] when the
    directory is missing/unreadable (caller decides how to proceed).
    """
    out: List[Dict[str, Any]] = []
    files = sorted(glob.glob(os.path.join(directory, "conversations-*.json")))
    if not files:
        logger.warning("[HIST_IMPORT] no conversations-*.json under %s", directory)
        return out
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                convs = json.load(f)
        except Exception as exc:
            logger.warning("[HIST_IMPORT] unreadable %s: %s", path, exc)
            continue
        for c in convs:
            mapping = c.get("mapping") or {}
            messages: List[Tuple[float, str, str]] = []
            for m in mapping.values():
                msg = m.get("message") or {}
                role = ((msg.get("author") or {}).get("role") or "").lower()
                if role not in ("user", "assistant"):
                    continue
                content = msg.get("content") or {}
                if content.get("content_type") != "text":
                    continue
                parts = content.get("parts") or []
                text = ""
                for p in parts:
                    if isinstance(p, str):
                        text += p
                text = (text or "").strip()
                if not text:
                    continue
                ts = msg.get("create_time") or 0
                try:
                    ts = float(ts)
                except (TypeError, ValueError):
                    ts = 0.0
                messages.append((ts, role, text))
            if not messages:
                continue
            messages.sort(key=lambda x: x[0])
            out.append({
                "conversation_id": c.get("conversation_id") or c.get("id") or "",
                "title": (c.get("title") or "").strip(),
                "create_time": c.get("create_time"),
                "messages": messages,
            })
    return out


def _claim_for(text: str, role: str) -> Optional[Tuple[str, str, str]]:
    """(relation, claim_text, category) for a user message, or None.

    Conservative, general: only first-person evidence families. Returns the
    claim WITHOUT the leading verb scaffolding where possible.
    """
    low = text.lower()
    if _CODE_FENCE_RE.search(text):
        return None
    if len(text) > 1200:
        return None

    # explicit rejection is a first-class family (never re-recommend)
    m = _REJECT_RE.search(text)
    if m and len(text) < _MAX_EVIDENCE_LEN:
        claim = _norm_claim(text)
        if 6 <= len(claim) <= _MAX_EVIDENCE_LEN:
            return "said", claim, "rejection"

    m = _DECIDE_RE.search(text)
    if m:
        claim = _norm_claim(text[m.end():] or text)
        if 4 <= len(claim) <= _MAX_EVIDENCE_LEN and not _PRONOUN_NOISE.search(claim) and not _is_junk(claim):
            return "decides", "decided: " + claim, "decision"

    m = _WANT_RE.search(text)
    if m and re.search(r"\bto\b|\bthat\b|\ba\b|\ban\b", text[m.end():]):
        claim = _norm_claim(text[m.end():] or text)
        if 4 <= len(claim) <= _MAX_EVIDENCE_LEN and not _PRONOUN_NOISE.search(claim) and not _is_junk(claim):
            return "wants", "wants: " + claim, "goal"

    m = _PREFER_RE.search(text)
    if m:
        claim = _norm_claim(text[m.end():] or text)
        if 4 <= len(claim) <= _MAX_EVIDENCE_LEN and " " in claim and not _PRONOUN_NOISE.search(claim) and not _is_junk(claim):
            return "prefers", "prefers: " + claim, "preference"

    m = _FAVORITE_RE.search(text)
    if m:
        claim = _norm_claim(f"favorite {m.group(1)}: {m.group(2)}")
        if 4 <= len(claim) <= _MAX_EVIDENCE_LEN:
            return "prefers", claim, "preference"

    m = _CALLME_RE.search(text)
    if m:
        name = _norm_claim(m.group(1))
        if 2 <= len(name) <= 40:
            return "said", f"user's name is {name}", "identity"
    return None


def _confidence(claim: str, year_month: Optional[str], repetition: int) -> float:
    conf = 0.5
    if year_month and year_month >= "2026-01":
        conf += 0.2  # recency: closer to the current state
    if repetition >= 2:
        conf += 0.15  # repetition: repeated statements are more stable
    conf += 0.05
    return min(0.95, conf)


def import_history(session_id: str, directory: str = EXPORT_DIR,
                   *, limit_convs: Optional[int] = None) -> Dict[str, int]:
    """Import the export into the canonical graph for `session_id`.

    Returns {conversations, extracted, imported, skipped} — imported is the
    number of NEW claims written. Idempotent via the import index.
    """
    index: Dict[str, Any] = {}
    if os.path.isfile(INDEX_PATH):
        try:
            with open(INDEX_PATH, encoding="utf-8") as f:
                index = json.load(f)
        except Exception:
            index = {}

    graph = SemanticGraph(session_id)
    convs = parse_export(directory)
    if limit_convs:
        convs = convs[:limit_convs]

    extracted = 0
    imported = 0
    imported_convs = 0
    # Repetition gate for the durable-instruction family: a one-off
    # directive is task-scoped, a repeated one ("no live testing", seen
    # dozens of times) is a stable interaction preference. Count first,
    # then import only instructions seen >= 2 times.
    instr_counts: Dict[str, int] = {}
    for _c in convs:
        if (index.get(_c.get('conversation_id') or '') or {}).get('imported'):
            continue
        for _ts, _role, _text in _c.get('messages', []):
            if _role != 'user':
                continue
            _hit = _claim_for_v2(_text, _role)
            if _hit and _hit[2] == 'instruction':
                _k = _hit[1].lower().strip(' .')
                instr_counts[_k] = instr_counts.get(_k, 0) + 1
    seen_claims: Dict[str, int] = {}
    for conv in convs:
        cid = conv.get("conversation_id") or ""
        if not cid:
            continue
        meta = index.get(cid) or {}
        if meta.get("imported"):
            continue
        claims_for_conv = 0
        for ts, role, text in conv.get("messages", []):
            if role != "user":
                continue
            hit = _claim_for_v2(text, role)
            if not hit:
                continue
            if hit[2] == 'instruction' and instr_counts.get(hit[1].lower().strip(' .'), 0) < 2:
                continue
            relation, claim, category = hit
            extracted += 1
            year_month = _message_date(ts)
            key = claim.lower().strip(" .")
            seen_claims[key] = seen_claims.get(key, 0) + 1
            repetition = seen_claims[key]
            conf = _confidence(claim, year_month, repetition)
            provenance = f"chatgpt_export:{cid}"
            if ts:
                provenance += f":{int(ts)}"
            # Distinct historical facts: supersede_prior=False keeps every
            # dated statement alive; recency ordering at query time decides
            # which one is current (newer live statements supersede by
            # event_time, not by destructive overwrite).
            link = graph.record_statement(
                USER_KEY, claim, relation=relation,
                stance="assertion", confidence=conf,
                event_time=datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds") if ts else None,
                supersede_prior=False,
                provenance=provenance,
            )
            if link:
                imported += 1
                claims_for_conv += 1
        if claims_for_conv > 0:
            index[cid] = {
                "imported": True,
                "title": conv.get("title", ""),
                "create_time": conv.get("create_time"),
                "extracted": claims_for_conv,
                "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            imported_convs += 1

    try:
        os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=1, ensure_ascii=False)
    except Exception as exc:
        logger.warning("[HIST_IMPORT] index write failed: %s", exc)

    logger.info(
        "[HIST_IMPORT] session=%s conversations=%d extracted=%d imported=%d (%d conversations)",
        session_id, len(convs), extracted, imported, imported_convs,
    )
    return {
        "conversations": len(convs),
        "extracted": extracted,
        "imported": imported,
        "imported_conversations": imported_convs,
    }


# ── v2 evidence families (calibrated to real user voice, still general) ─────
_WILL_RE = re.compile(
    r"\bi(?:'ll|\s+will|\s+'m\s+going\s+to|\s+am\s+going\s+to|\s+gonna|\s+plan\s+to)\s+([^,.!?;]{4,90})",
    re.I,
)
_INSTRUCTION_RE = re.compile(
    r"\b(?:no|dont|don['\u2019]t|never|always|remember\s+to|make\s+sure\s+to)\s+([^,.!?;]{4,90})$",
    re.I,
)
# conversational scaffolding after a want/plan verb ("i want to ASK you ...",
# "i plan to TELL you ...") is a request, not durable evidence.
_SCAFFOLD_RE = re.compile(
    r"\b(ask|tell|check|know|say|mention|see|hear|discuss|talk|show|give|write|type)\s+(?:you|u|me|us|him|her|them)?\b",
    re.I,
)
_INSTRUCTION_NOISE = frozenset({
    "problem", "issues", "worries", "doubt", "idea", "clue", "way", "need",
    "worries", "issue", "prob", "stress", "pressure",
})

_PRONOUN_NOISE = re.compile(
    r"\b(she|her|hers|he|him|his|u|ur|yours|me|my|mine|we|us|our|gf|bf|crush|ex|insta|whatsapp)\b",
    re.I,
)
_QUESTION_END = re.compile(r"\?\s*$")

# Conversational openers that precede a real claim ("wait i need a black
# screen" -> "i need a black screen") are scaffolding, not part of it.
_FILLER_LEAD = re.compile(
    r"^(?:wait|okay|ok|so|well|oh|nah|yeah|yep|anyway|actually|honestly|tbh|bro|bruh|man|dude|like)\b[,:]?\s+",
    re.I,
)

# Generic filler-only claims ("do it later", "do that") carry no evidence.
_GENERIC_WORDS = frozenset(
    "do it that this later now tmrw tomorrow today soon then here there again "
    "on in at to of for with about up down out off back go going make sure "
    "some something nothing everything anything all them those these".split()
)


def _is_junk(claim: str) -> bool:
    words = [w for w in claim.lower().split() if re.search(r"[a-z0-9]", w)]
    if not words:
        return True
    if len(words) <= 3 and all(w in _GENERIC_WORDS for w in words):
        return True
    if len(claim) < 4:
        return True
    return False


def _claim_for_v2(text: str, role: str) -> Optional[Tuple[str, str, str]]:
    """v2: adds the will/plan family and the durable-instruction family
    (both general morphological classes), and filters conversational
    scaffolding and question-shaped messages."""
    if _CODE_FENCE_RE.search(text) or len(text) > 1200:
        return None
    if _QUESTION_END.search(text):
        return None
    low = text.lower()

    m = _REJECT_RE.search(text)
    if m and len(text) < _MAX_EVIDENCE_LEN:
        claim = _norm_claim(text)
        if 6 <= len(claim) <= _MAX_EVIDENCE_LEN:
            return "said", claim, "rejection"

    m = _WILL_RE.search(text)
    if m and not _SCAFFOLD_RE.search(m.group(1)):
        claim = _norm_claim(m.group(1))
        if 4 <= len(claim) <= _MAX_EVIDENCE_LEN and not _PRONOUN_NOISE.search(claim) and not _is_junk(claim):
            return "wants", "plans to: " + claim, "goal"

    m = _DECIDE_RE.search(text)
    if m:
        claim = _norm_claim(text[m.end():] or text)
        if 4 <= len(claim) <= _MAX_EVIDENCE_LEN:
            return "decides", "decided: " + claim, "decision"

    m = _WANT_RE.search(text)
    if m and re.search(r"\bto\b|\bthat\b|\ba\b|\ban\b", text[m.end():]) \
            and not _SCAFFOLD_RE.search(text[m.end():]):
        claim = _norm_claim(text[m.end():] or text)
        if 4 <= len(claim) <= _MAX_EVIDENCE_LEN:
            return "wants", "wants: " + claim, "goal"

    m = _PREFER_RE.search(text)
    if m:
        claim = _norm_claim(text[m.end():] or text)
        # "like" in this register is often a discourse filler ("i like tried
        # creating X", "i like just want") — a past-tense/discourse word right
        # after it means it is NOT a preference verb.
        _v = m.group(1).lower().strip()
        _next = (claim.split()[0].lower() if claim.split() else "")
        _filler_like = (
            _v == "like"
            and _next
            in ("tried", "just", "was", "were", "have", "had", "has", "will",
                "would", "can", "could", "also", "even", "actually", "honestly",
                "really", "want", "wanted", "went", "got", "made", "did", "do")
        )
        if (4 <= len(claim) <= _MAX_EVIDENCE_LEN and " " in claim
                and not _PRONOUN_NOISE.search(claim) and not _is_junk(claim)
                and not _filler_like):
            return "prefers", "prefers: " + claim, "preference"

    m = _INSTRUCTION_RE.search(text)
    if m:
        claim = _norm_claim(m.group(1))
        if (4 <= len(claim) <= 90 and claim.lower() not in _INSTRUCTION_NOISE
                and " " in claim and not _PRONOUN_NOISE.search(claim) and not _is_junk(claim)):
            return "said", "rule: " + claim, "instruction"

    m = _FAVORITE_RE.search(text)
    if m:
        claim = _norm_claim(f"favorite {m.group(1)}: {m.group(2)}")
        if 4 <= len(claim) <= _MAX_EVIDENCE_LEN:
            return "prefers", claim, "preference"

    m = _CALLME_RE.search(text)
    if m:
        name = _norm_claim(m.group(1))
        if 2 <= len(name) <= 40:
            return "said", f"user's name is {name}", "identity"
    return None
