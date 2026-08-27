"""archive_miner.py -- Deep extraction from ChatGPT export conversations.

Parses all conversation JSON files, walks message trees, and extracts
structured findings across six categories: projects, behavioral patterns,
emotional episodes, decision chains, correction chains, and relationship
dynamics.

Usage:
    from mini_kio.memory.archive_miner import extract_all
    findings = extract_all()  # list of Finding dicts
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = __import__("logging").getLogger(__name__)

EXPORT_DIR = (
    Path(__file__).resolve().parents[3]
    / "data" / "historical" / "chatgpt_export_2026-06-12"
)
MAX_TEXT_LEN = 500

LIFECYCLE_STATES = (
    "mentioned", "explored", "building", "active", "paused",
    "abandoned", "completed",
)

# -- Signal regexes --------------------------------------------------------

APPROVAL_SIGNALS = re.compile(
    r"\b(nice|perfect|that works|exactly|great|awesome|love it|brilliant"
    r"|spot on|well done|good job|amazing)\b",
    re.IGNORECASE,
)
IMPATIENCE_SIGNALS = re.compile(
    r"\b(nvm|never mind|forget it|whatever|doesn.t matter|stop|enough"
    r"|this is useless|waste of time|ugh)\b",
    re.IGNORECASE,
)
CORRECTION_PREFIXES = re.compile(
    r"^(no[,. ]|wrong|actually|that.s not|not what I meant|I meant"
    r"|close but|not quite|almost|incorrect)\b",
    re.IGNORECASE,
)
DECISION_SIGNALS = re.compile(
    r"\b(should I|which (?:one|option|way|approach)|decide|choose|go with"
    r"|I.ll (?:go with|use|try|do|pick|choose)|let.s go with)\b",
    re.IGNORECASE,
)
NEGATIVE_TONE = re.compile(
    r"\b(frustrat|annoy|angry|hate|terrible|horrible|awful|worst|useless"
    r"|broken|failed|doesn.t work|won.t work|stupid|dumb|sucks|pain"
    r"|nightmare)\b",
    re.IGNORECASE,
)
CODE_BLOCK = re.compile(r"```(\w+)?\n[\s\S]+?```")

TECH_VOCAB = frozenset({
    "react", "vue", "angular", "svelte", "next", "nuxt", "node", "python",
    "flask", "django", "fastapi", "express", "typescript", "javascript",
    "html", "css", "tailwind", "bootstrap", "postgresql", "sqlite", "redis",
    "mongodb", "aws", "vercel", "netlify", "docker", "git", "github",
    "api", "rest", "graphql", "database", "schema", "migrate", "auth",
    "login", "server", "client", "deploy", "build", "test", "debug",
    "refactor", "component", "endpoint", "webhook", "token", "oauth",
    "jwt", "cors", "middleware", "nginx", "linux", "terminal", "shell",
    "bash", "npm", "pip", "cargo", "rust", "golang", "java", "kotlin",
    "swift", "flutter", "dart", "sass", "webpack", "vite", "prisma",
    "drizzle", "sqlalchemy", "celery", "redis", "supabase", "firebase",
    "openai", "anthropic", "claude", "gpt", "llm", "embedding", "vector",
    "langchain", "kubernetes", "terraform", "ansible", "prometheus",
    "grafana", "elasticsearch", "kafka", "rabbitmq", "vscode", "neovim",
    "tmux", "ssh", "curl", "wget", "powershell", "rollup", "esbuild",
    "typeorm", "pinecone", "weaviate", "llamaindex",
})


class Finding:
    """One extracted insight from the archive."""

    __slots__ = (
        "category", "subcategory", "name", "text", "confidence",
        "provenance", "date_range", "related_conversations",
    )

    def __init__(
        self,
        category: str,
        subcategory: str,
        name: str,
        text: str,
        confidence: float = 0.5,
        provenance: str = "",
        date_range: Tuple[str, str] = ("", ""),
        related_conversations: Optional[List[str]] = None,
    ):
        self.category = category
        self.subcategory = subcategory
        self.name = name
        self.text = text[:MAX_TEXT_LEN]
        self.confidence = min(max(confidence, 0.0), 1.0)
        self.provenance = provenance
        self.date_range = date_range
        self.related_conversations = related_conversations or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "subcategory": self.subcategory,
            "name": self.name,
            "text": self.text,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "date_range": list(self.date_range),
            "related_conversations": self.related_conversations,
        }


# -- Conversation loading & tree walking -----------------------------------

def _load_all_conversations() -> List[Dict]:
    conversations: List[Dict] = []
    for i in range(10):
        path = EXPORT_DIR / f"conversations-{i:03d}.json"
        if not path.exists():
            logger.warning("Missing export file: %s", path)
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                conversations.extend(data)
            else:
                conversations.append(data)
            count = len(data) if isinstance(data, list) else 1
            logger.info("Loaded %d conversations from %s", count, path.name)
        except Exception as exc:
            logger.error("Failed to load %s: %s", path, exc)
    return conversations


def _walk_message_tree(mapping: Dict) -> List[Dict]:
    """Walk the mapping tree to produce ordered messages (oldest first)."""
    if not mapping:
        return []
    children: Dict[Optional[str], List[str]] = defaultdict(list)
    root_id = None
    for node_id, node in mapping.items():
        parent = node.get("parent")
        if parent is None:
            root_id = node_id
        else:
            children[parent].append(node_id)
    ordered: List[Dict] = []
    queue = [root_id] if root_id else []
    visited: set = set()
    while queue:
        nid = queue.pop(0)
        if nid in visited or nid not in mapping:
            continue
        visited.add(nid)
        node = mapping[nid]
        msg = node.get("message")
        if msg and msg.get("content"):
            parts = msg["content"].get("parts", [])
            text = " ".join(str(p) for p in parts if p).strip()
            if text:
                ordered.append({
                    "role": msg.get("author", {}).get("role", "unknown"),
                    "text": text,
                    "time": msg.get("create_time"),
                    "id": nid,
                })
        child_ids = children.get(nid, [])
        child_ids.sort(key=lambda cid: (
            mapping.get(cid, {}).get("message", {}).get("create_time", 0) or 0
        ))
        queue.extend(child_ids)
    ordered.sort(key=lambda m: m.get("time") or 0)
    return ordered


def _ts_to_iso(ts: Optional[float]) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (OSError, ValueError):
        return ""


def _pair_date_range(msgs: List[Dict]) -> Tuple[str, str]:
    times = [m["time"] for m in msgs if m.get("time")]
    if not times:
        return ("", "")
    return (_ts_to_iso(min(times)), _ts_to_iso(max(times)))


# -- Extractor: Projects ---------------------------------------------------

def _extract_projects(conversations: List[Dict]) -> List[Finding]:
    """Identify real projects from conversation content."""
    project_data: Dict[str, Dict] = defaultdict(lambda: {
        "mentions": 0, "user_msgs": 0, "convos": set(),
        "has_code": False, "has_decisions": False,
        "earliest": None, "latest": None,
        "samples": [], "tech_terms": set(),
    })
    for conv in conversations:
        title = conv.get("title", "Untitled")
        msgs = _walk_message_tree(conv.get("mapping", {}))
        for msg in msgs:
            text = msg["text"]
            is_user = msg["role"] == "user"
            has_code = bool(CODE_BLOCK.search(text))
            has_tech = any(
                re.search(rf"\b{t}\b", text, re.IGNORECASE) for t in TECH_VOCAB
            ) if len(text) > 30 else False
            has_decision = bool(DECISION_SIGNALS.search(text))
            if not (has_code or has_tech or (is_user and len(text) > 40)):
                continue
            candidates = _extract_project_candidates(text, title)
            for proj_name in candidates:
                p = project_data[proj_name]
                p["mentions"] += 1
                if is_user:
                    p["user_msgs"] += 1
                p["convos"].add(title)
                p["has_code"] = p["has_code"] or has_code
                p["has_decisions"] = p["has_decisions"] or has_decision
                t = msg.get("time")
                if t:
                    if p["earliest"] is None or t < p["earliest"]:
                        p["earliest"] = t
                    if p["latest"] is None or t > p["latest"]:
                        p["latest"] = t
                if len(p["samples"]) < 3:
                    p["samples"].append(text[:200])
                for word in re.findall(r"[A-Za-z]{4,}", text):
                    if word.lower() in TECH_VOCAB:
                        p["tech_terms"].add(word.lower())
    findings: List[Finding] = []
    for name, data in sorted(
        project_data.items(), key=lambda x: -x[1]["mentions"]
    ):
        if data["mentions"] < 2:
            continue
        lifecycle = _infer_lifecycle(data)
        conf = 0.3
        if data["has_code"]:
            conf += 0.2
        if data["has_decisions"]:
            conf += 0.15
        if data["user_msgs"] >= 3:
            conf += 0.15
        if data["mentions"] >= 5:
            conf += 0.1
        if len(data["tech_terms"]) >= 2:
            conf += 0.1
        text = (
            f"[{lifecycle}] {data['mentions']} mentions across "
            f"{len(data['convos'])} conversations"
        )
        if data["samples"]:
            text += f". Sample: {data['samples'][0][:150]}"
        dr = (_ts_to_iso(data["earliest"]), _ts_to_iso(data["latest"]))
        findings.append(Finding(
            category="project", subcategory=lifecycle, name=name,
            text=text, confidence=conf,
            provenance=f"archive_v3:project:{lifecycle}",
            date_range=dr,
            related_conversations=sorted(data["convos"])[:5],
        ))
    return findings


def _extract_project_candidates(text: str, title: str) -> List[str]:
    candidates: List[str] = []
    if title and title not in ("New Chat", "ChatGPT", "Untitled"):
        candidates.append(title.strip())
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5})\b", text):
        phrase = m.group(1)
        skip = {"The", "This", "That", "What", "How", "When", "Where", "Why"}
        if phrase not in skip:
            candidates.append(phrase)
    for m in re.finditer(r'["\']([^"\']{3,40})["\']', text):
        candidates.append(m.group(1))
    for m in re.finditer(
        r"\b([A-Za-z][A-Za-z0-9_-]{1,30})\s+"
        r"(?:project|app|website|bot|server|tool|library|package|"
        r"extension|plugin|dashboard|admin|panel|interface)\b",
        text, re.IGNORECASE,
    ):
        candidates.append(m.group(1))
    return list(dict.fromkeys(candidates))[:5]


def _infer_lifecycle(data: Dict) -> str:
    if data["has_code"] and data["user_msgs"] >= 3:
        return "active" if data["mentions"] >= 8 else "building"
    if data["has_decisions"]:
        return "building" if data["mentions"] >= 5 else "explored"
    if data["mentions"] >= 5:
        return "explored"
    return "mentioned"


# -- Extractor: Behavioral Patterns ----------------------------------------

def _extract_behaviors(conversations: List[Dict]) -> List[Finding]:
    findings: List[Finding] = []
    all_user_lengths: List[int] = []
    debugging_sessions: List[Dict] = []
    impatience_events: List[Dict] = []
    approval_events: List[Dict] = []
    correction_events: List[Dict] = []

    for conv in conversations:
        title = conv.get("title", "Untitled")
        msgs = _walk_message_tree(conv.get("mapping", {}))
        for m in msgs:
            if m["role"] == "user":
                all_user_lengths.append(len(m["text"]))
            if IMPATIENCE_SIGNALS.search(m["text"]):
                impatience_events.append({"text": m["text"], "role": m["role"], "conv": title, "time": m.get("time")})
            if APPROVAL_SIGNALS.search(m["text"]):
                approval_events.append({"text": m["text"], "role": m["role"], "conv": title, "time": m.get("time")})
        _detect_debugging_pattern(msgs, title, debugging_sessions)
        _detect_correction_sequences(msgs, title, correction_events)

    # 1. Directness
    if all_user_lengths:
        short = sum(1 for l in all_user_lengths if l < 50)
        medium = sum(1 for l in all_user_lengths if 50 <= l < 200)
        long_ = sum(1 for l in all_user_lengths if l >= 200)
        dominant = (
            "short" if short > medium and short > long_
            else "long" if long_ > short and long_ > medium
            else "mixed"
        )
        findings.append(Finding(
            category="behavior", subcategory="directness",
            name="message_length_profile",
            text=(
                f"User message distribution: {short} short (<50c), "
                f"{medium} medium (50-200c), {long_} long (>200c). "
                f"Dominant style: {dominant}"
            ),
            confidence=0.7,
            provenance="archive_v3:behavior:directness",
        ))

    # 2. Debugging style
    if debugging_sessions:
        careful = sum(1 for s in debugging_sessions if s.get("reads_error"))
        blind = len(debugging_sessions) - careful
        style = (
            "careful" if careful > blind
            else "retry-oriented" if blind > careful
            else "mixed"
        )
        findings.append(Finding(
            category="behavior", subcategory="debugging_style",
            name="debugging_approach",
            text=(
                f"Across {len(debugging_sessions)} error-recovery sequences: "
                f"{careful} careful, {blind} retry-oriented. Style: {style}"
            ),
            confidence=0.6,
            provenance="archive_v3:behavior:debugging_style",
        ))

    # 3. Impatience
    if impatience_events:
        samples = [e["text"][:100] for e in impatience_events[:3]]
        findings.append(Finding(
            category="behavior", subcategory="impatience",
            name="impatience_episodes",
            text=f"{len(impatience_events)} signals. Examples: {' | '.join(samples)}",
            confidence=0.65,
            provenance="archive_v3:behavior:impatience",
        ))

    # 4. Approval
    if approval_events:
        samples = [e["text"][:100] for e in approval_events[:3]]
        findings.append(Finding(
            category="behavior", subcategory="approval",
            name="approval_episodes",
            text=f"{len(approval_events)} signals. Examples: {' | '.join(samples)}",
            confidence=0.65,
            provenance="archive_v3:behavior:approval",
        ))

    # 5. Correction style
    if correction_events:
        gentle = sum(1 for e in correction_events if e["style"] == "gentle")
        direct = sum(1 for e in correction_events if e["style"] == "direct")
        silent = sum(1 for e in correction_events if e["style"] == "silent")
        dominant_style = max(
            [("gentle", gentle), ("direct", direct), ("silent", silent)],
            key=lambda x: x[1],
        )[0]
        samples = [e["text"][:100] for e in correction_events[:3]]
        findings.append(Finding(
            category="behavior", subcategory="correction_style",
            name="correction_approach",
            text=(
                f"{len(correction_events)} corrections: {gentle} gentle, "
                f"{direct} direct, {silent} silent. Dominant: {dominant_style}. "
                f"Examples: {' | '.join(samples)}"
            ),
            confidence=0.6,
            provenance="archive_v3:behavior:correction_style",
        ))

    return findings


def _detect_debugging_pattern(messages: List[Dict], title: str, out: List[Dict]) -> None:
    for i in range(len(messages) - 1):
        curr, nxt = messages[i], messages[i + 1]
        if curr["role"] != "assistant":
            continue
        if not re.search(
            r"(?:error|exception|traceback|failed|bug|issue|problem|wrong"
            r"|doesn.t work|not working|undefined|null)",
            curr["text"], re.IGNORECASE,
        ):
            continue
        if nxt["role"] != "user":
            continue
        reads_error = bool(re.search(
            r"(?:here.s (?:the )?(?:error|traceback|output|log)"
            r"|(?:error|exception|traceback|bug|issue)\s*[:=]"
            r"|```.+(?:error|exception|traceback)"
            r"|got this|seeing this|the output)",
            nxt["text"], re.IGNORECASE,
        ))
        out.append({
            "conv": title,
            "reads_error": reads_error,
            "user_text": nxt["text"][:200],
        })


def _detect_correction_sequences(messages: List[Dict], title: str, out: List[Dict]) -> None:
    for i in range(len(messages) - 1):
        curr, nxt = messages[i], messages[i + 1]
        if curr["role"] != "assistant" or nxt["role"] != "user":
            continue
        user_text = nxt["text"].strip()
        if not CORRECTION_PREFIXES.search(user_text):
            continue
        style = "silent"
        lower = user_text.lower()
        if any(w in lower for w in ("actually", "i meant", "not what i meant")):
            style = "gentle"
        elif any(w in lower for w in ("wrong", "no,", "no.", "incorrect")):
            style = "direct"
        out.append({
            "conv": title,
            "style": style,
            "text": user_text[:200],
            "time": nxt.get("time"),
        })


# -- Extractor: Emotional Episodes -----------------------------------------

def _extract_emotions(conversations: List[Dict]) -> List[Finding]:
    findings: List[Finding] = []
    episodes: List[Dict] = []

    for conv in conversations:
        title = conv.get("title", "Untitled")
        msgs = _walk_message_tree(conv.get("mapping", {}))
        for i, msg in enumerate(msgs):
            if msg["role"] != "user":
                continue
            text = msg["text"]
            if not NEGATIVE_TONE.search(text):
                continue
            trigger = ""
            if i > 0:
                trigger = msgs[i - 1]["text"][:150]
            target = _infer_emotion_target(text, title)
            resolution = "unresolved"
            if i < len(msgs) - 1:
                next_user = None
                for j in range(i + 1, min(i + 5, len(msgs))):
                    if msgs[j]["role"] == "user":
                        next_user = msgs[j]
                        break
                if next_user:
                    nt = next_user["text"].lower()
                    if any(s in nt for s in ("thanks", "perfect", "that works", "got it", "ok")):
                        resolution = "resolved"
                    elif IMPATIENCE_SIGNALS.search(next_user["text"]):
                        resolution = "escalated"
                    else:
                        resolution = "moved_on"
            episodes.append({
                "text": text[:300],
                "trigger": trigger,
                "target": target,
                "resolution": resolution,
                "conv": title,
                "time": msg.get("time"),
            })

    if episodes:
        by_target: Dict[str, List[Dict]] = defaultdict(list)
        for ep in episodes:
            by_target[ep["target"]].append(ep)
        for target, eps in sorted(by_target.items(), key=lambda x: -len(x[1])):
            samples = [e["text"][:100] for e in eps[:2]]
            resolutions = defaultdict(int)
            for e in eps:
                resolutions[e["resolution"]] += 1
            findings.append(Finding(
                category="emotion", subcategory="frustration",
                name=f"frustration_{target}",
                text=(
                    f"{len(eps)} frustration episodes targeting {target}. "
                    f"Resolutions: {dict(resolutions)}. "
                    f"Examples: {' | '.join(samples)}"
                ),
                confidence=0.6,
                provenance=f"archive_v3:emotion:frustration:{target}",
                date_range=_pair_date_range([{"time": e["time"]} for e in eps]),
                related_conversations=list({e["conv"] for e in eps})[:5],
            ))

    # Excitement episodes
    excitement: List[Dict] = []
    for conv in conversations:
        title = conv.get("title", "Untitled")
        msgs = _walk_message_tree(conv.get("mapping", {}))
        for i, msg in enumerate(msgs):
            if msg["role"] != "user":
                continue
            if not APPROVAL_SIGNALS.search(msg["text"]):
                continue
            trigger = ""
            if i > 0:
                trigger = msgs[i - 1]["text"][:150]
            excitement.append({
                "text": msg["text"][:300],
                "trigger": trigger,
                "conv": title,
                "time": msg.get("time"),
            })

    if excitement:
        samples = [e["text"][:100] for e in excitement[:3]]
        findings.append(Finding(
            category="emotion", subcategory="excitement",
            name="positive_responses",
            text=(
                f"{len(excitement)} positive/excitement episodes. "
                f"Examples: {' | '.join(samples)}"
            ),
            confidence=0.65,
            provenance="archive_v3:emotion:excitement",
            date_range=_pair_date_range([{"time": e["time"]} for e in excitement]),
            related_conversations=list({e["conv"] for e in excitement})[:5],
        ))

    return findings


def _infer_emotion_target(text: str, conv_title: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ("kio", "you keep", "you always", "you don")):
        return "kio"
    if any(w in lower for w in ("my code", "my app", "my project", "this thing")):
        return "own_project"
    if any(w in lower for w in ("chatgpt", "gpt", "openai", "the ai", "it keeps")):
        return "external_tool"
    if any(w in lower for w in ("i can't", "i'm stuck", "i don't understand")):
        return "self"
    return "situation"


# -- Extractor: Decision Chains --------------------------------------------

def _extract_decisions(conversations: List[Dict]) -> List[Finding]:
    findings: List[Finding] = []
    chains: List[Dict] = []

    for conv in conversations:
        title = conv.get("title", "Untitled")
        msgs = _walk_message_tree(conv.get("mapping", {}))
        for i, msg in enumerate(msgs):
            if msg["role"] != "user":
                continue
            if not DECISION_SIGNALS.search(msg["text"]):
                continue
            options_shown = ""
            chosen = ""
            reversal = False
            final_state = "pending"
            for j in range(i + 1, min(i + 6, len(msgs))):
                resp = msgs[j]
                if resp["role"] == "assistant":
                    options_shown = resp["text"][:200]
                elif resp["role"] == "user":
                    rt = resp["text"]
                    lower = rt.lower()
                    if any(w in lower for w in ("go with", "use that", "let's", "yes", "do it", "sounds good")):
                        chosen = rt[:150]
                        final_state = "decided"
                        break
                    if any(w in lower for w in ("actually", "wait", "no", "changed my mind", "on second")):
                        reversal = True
                        final_state = "reversed"
                    break
            chains.append({
                "question": msg["text"][:300],
                "options": options_shown,
                "chosen": chosen,
                "reversal": reversal,
                "final_state": final_state,
                "conv": title,
                "time": msg.get("time"),
            })

    if chains:
        decided = sum(1 for c in chains if c["final_state"] == "decided")
        reversed_ = sum(1 for c in chains if c["final_state"] == "reversed")
        pending = sum(1 for c in chains if c["final_state"] == "pending")
        samples = [c["question"][:100] for c in chains[:3]]
        findings.append(Finding(
            category="decision", subcategory="decision_chains",
            name="decision_pattern",
            text=(
                f"{len(chains)} decision episodes: {decided} resolved, "
                f"{reversed_} reversed, {pending} pending. "
                f"Examples: {' | '.join(samples)}"
            ),
            confidence=0.55,
            provenance="archive_v3:decision:chains",
            date_range=_pair_date_range([{"time": c["time"]} for c in chains]),
            related_conversations=list({c["conv"] for c in chains})[:5],
        ))
        for c in chains:
            if c["final_state"] == "decided" and c["chosen"]:
                findings.append(Finding(
                    category="decision", subcategory="choice",
                    name=c["question"][:50],
                    text=(
                        f"Q: {c['question'][:150]}. "
                        f"Chose: {c['chosen'][:150]}"
                    ),
                    confidence=0.6,
                    provenance="archive_v3:decision:choice",
                    date_range=(_ts_to_iso(c["time"]), _ts_to_iso(c["time"])),
                    related_conversations=[c["conv"]],
                ))

    return findings


# -- Extractor: Correction Chains ------------------------------------------

def _extract_corrections(conversations: List[Dict]) -> List[Finding]:
    findings: List[Finding] = []
    chains: List[Dict] = []

    for conv in conversations:
        title = conv.get("title", "Untitled")
        msgs = _walk_message_tree(conv.get("mapping", {}))
        for i in range(len(msgs) - 1):
            curr, nxt = msgs[i], msgs[i + 1]
            if curr["role"] != "assistant" or nxt["role"] != "user":
                continue
            user_text = nxt["text"].strip()
            if not CORRECTION_PREFIXES.search(user_text):
                continue
            kio_said = curr["text"][:200]
            corrected_to = user_text[:200]
            right_answer = ""
            for j in range(i + 2, min(i + 6, len(msgs))):
                if msgs[j]["role"] == "assistant":
                    right_answer = msgs[j]["text"][:200]
                    break
            chains.append({
                "kio_said": kio_said,
                "corrected_to": corrected_to,
                "right_answer": right_answer,
                "conv": title,
                "time": nxt.get("time"),
            })

    if chains:
        samples = [c["corrected_to"][:100] for c in chains[:3]]
        findings.append(Finding(
            category="correction", subcategory="correction_chains",
            name="corrections_to_kio",
            text=(
                f"{len(chains)} correction chains. "
                f"Examples: {' | '.join(samples)}"
            ),
            confidence=0.6,
            provenance="archive_v3:correction:chains",
            date_range=_pair_date_range([{"time": c["time"]} for c in chains]),
            related_conversations=list({c["conv"] for c in chains})[:5],
        ))
        for c in chains:
            if c["right_answer"]:
                findings.append(Finding(
                    category="correction", subcategory="specific_correction",
                    name=c["corrected_to"][:50],
                    text=(
                        f"KIO said: {c['kio_said'][:150]}. "
                        f"Correction: {c['corrected_to'][:150]}"
                    ),
                    confidence=0.55,
                    provenance="archive_v3:correction:specific",
                    date_range=(_ts_to_iso(c["time"]), _ts_to_iso(c["time"])),
                    related_conversations=[c["conv"]],
                ))

    return findings


# -- Extractor: KIO Relationship -------------------------------------------

def _extract_relationship(conversations: List[Dict]) -> List[Finding]:
    findings: List[Finding] = []
    complaints: List[Dict] = []
    trust_signals: List[Dict] = []
    expectations: List[Dict] = []
    interactions_over_time: List[Dict] = []

    complaint_re = re.compile(
        r"\b(you keep|you always|you don.t|why do you|this is (?:wrong|bad|terrible)"
        r"|that.s (?:wrong|not right|bad)|you (?:should|need to|must))\b",
        re.IGNORECASE,
    )
    trust_re = re.compile(
        r"\b(can you (?:help|build|create|write|make|fix|handle)"
        r"|do this for me|I trust you|you decide|go ahead|do it"
        r"|handle this|take care of)\b",
        re.IGNORECASE,
    )
    expectation_re = re.compile(
        r"\b(I need you to|you should|don.t (?:do|say|use|make)"
        r"|please (?:don.t|never|always)|make sure you|remember to"
        r"|from now on|every time)\b",
        re.IGNORECASE,
    )

    for conv in conversations:
        title = conv.get("title", "Untitled")
        create_time = conv.get("create_time")
        msgs = _walk_message_tree(conv.get("mapping", {}))
        user_msg_count = sum(1 for m in msgs if m["role"] == "user")
        interactions_over_time.append({
            "conv": title, "time": create_time, "user_msgs": user_msg_count,
        })
        for msg in msgs:
            if msg["role"] != "user":
                continue
            text = msg["text"]
            if complaint_re.search(text):
                complaints.append({"text": text[:200], "conv": title, "time": msg.get("time")})
            if trust_re.search(text):
                trust_signals.append({"text": text[:200], "conv": title, "time": msg.get("time")})
            if expectation_re.search(text):
                expectations.append({"text": text[:200], "conv": title, "time": msg.get("time")})

    if complaints:
        topic_counts: Dict[str, int] = defaultdict(int)
        for c in complaints:
            topic_counts[c["conv"]] += 1
        samples = [c["text"][:100] for c in complaints[:3]]
        findings.append(Finding(
            category="relationship", subcategory="complaints",
            name="recurring_complaints",
            text=(
                f"{len(complaints)} complaints across "
                f"{len(topic_counts)} conversations. "
                f"Examples: {' | '.join(samples)}"
            ),
            confidence=0.6,
            provenance="archive_v3:relationship:complaints",
            date_range=_pair_date_range([{"time": c["time"]} for c in complaints]),
            related_conversations=list({c["conv"] for c in complaints})[:5],
        ))

    if trust_signals:
        samples = [t["text"][:100] for t in trust_signals[:3]]
        findings.append(Finding(
            category="relationship", subcategory="trust",
            name="trust_signals",
            text=(
                f"{len(trust_signals)} trust/complexity signals. "
                f"Examples: {' | '.join(samples)}"
            ),
            confidence=0.6,
            provenance="archive_v3:relationship:trust",
            date_range=_pair_date_range([{"time": t["time"]} for t in trust_signals]),
            related_conversations=list({t["conv"] for t in trust_signals})[:5],
        ))

    if expectations:
        samples = [e["text"][:100] for e in expectations[:3]]
        findings.append(Finding(
            category="relationship", subcategory="expectations",
            name="stated_expectations",
            text=(
                f"{len(expectations)} stated expectations/rules. "
                f"Examples: {' | '.join(samples)}"
            ),
            confidence=0.65,
            provenance="archive_v3:relationship:expectations",
            date_range=_pair_date_range([{"time": e["time"]} for e in expectations]),
            related_conversations=list({e["conv"] for e in expectations})[:5],
        ))

    if interactions_over_time:
        sorted_convos = sorted(
            [c for c in interactions_over_time if c.get("time")],
            key=lambda c: c["time"],
        )
        if len(sorted_convos) >= 4:
            mid = len(sorted_convos) // 2
            early_avg = sum(c["user_msgs"] for c in sorted_convos[:mid]) / max(mid, 1)
            late_avg = sum(c["user_msgs"] for c in sorted_convos[mid:]) / max(len(sorted_convos) - mid, 1)
            trajectory = (
                "increasing" if late_avg > early_avg * 1.2
                else "decreasing" if late_avg < early_avg * 0.8
                else "stable"
            )
            findings.append(Finding(
                category="relationship", subcategory="engagement",
                name="engagement_trajectory",
                text=(
                    f"{len(sorted_convos)} conversations over time. "
                    f"Early avg msgs/conv: {early_avg:.1f}, "
                    f"late avg: {late_avg:.1f}. Trajectory: {trajectory}"
                ),
                confidence=0.55,
                provenance="archive_v3:relationship:engagement",
                date_range=(
                    _ts_to_iso(sorted_convos[0]["time"]),
                    _ts_to_iso(sorted_convos[-1]["time"]),
                ),
            ))

    return findings


# -- Public API -------------------------------------------------------------

def extract_all() -> List[Dict[str, Any]]:
    """Parse all ChatGPT export files and extract structured findings.

    Returns a list of Finding dicts, each with:
        category, subcategory, name, text, confidence,
        provenance, date_range, related_conversations
    """
    conversations = _load_all_conversations()
    if not conversations:
        logger.warning("No conversations loaded from %s", EXPORT_DIR)
        return []

    logger.info("Mining %d conversations...", len(conversations))
    all_findings: List[Finding] = []
    all_findings.extend(_extract_projects(conversations))
    all_findings.extend(_extract_behaviors(conversations))
    all_findings.extend(_extract_emotions(conversations))
    all_findings.extend(_extract_decisions(conversations))
    all_findings.extend(_extract_corrections(conversations))
    all_findings.extend(_extract_relationship(conversations))

    logger.info("Extracted %d findings across 6 categories", len(all_findings))
    return [f.to_dict() for f in all_findings]


if __name__ == "__main__":
    import pprint
    results = extract_all()
    by_cat: Dict[str, int] = defaultdict(int)
    for r in results:
        by_cat[r["category"]] += 1
    print(f"\n=== Archive Miner Results: {len(results)} findings ===")
    for cat, count in sorted(by_cat.items()):
        print(f"  {cat}: {count}")
    print()
    for cat in ("project", "behavior", "emotion", "decision", "correction", "relationship"):
        subset = [r for r in results if r["category"] == cat][:3]
        if subset:
            print(f"--- {cat.upper()} ---")
            for r in subset:
                print(f"  [{r['subcategory']}] {r['name']}: {r['text'][:120]}...")
            print()
