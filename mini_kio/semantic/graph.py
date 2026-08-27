"""graph.py — the canonical Node/Link semantic graph store (FINAL architecture).

Node = anything addressable. Link = relationship between Nodes carrying the
UNIVERSAL metadata: stance, attributed_to, confidence, status, event_time,
provenance, supersession. One graph per session_id under the existing
SQLAlchemy persistence substrate (mini_kio.backend.db).

Design rules enforced here:
- Node.kind is descriptive data — never a switch/domain router.
- Link vocabulary is open; adding a relation never requires a new subsystem.
- Corrections SUPERSEDE (status + supersedes_id, history preserved), they
  never delete.
- Contradictions are represented as explicit links; conflicting evidence is
  preserved, never silently overwritten.
- Attribution is symmetric: user, KIO and third parties are ordinary
  participant nodes addressed by key (participant:user, participant:kio, ...).
- 'forget' marks status=forgotten (excluded from recall) without destroying
  provenance.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mini_kio.backend.db import db_session, init_db
from mini_kio.backend.models import SemanticLinkModel, SemanticNodeModel

logger = logging.getLogger(__name__)

# Node keys for the two permanent implicit participants (ordinary nodes, not
# special conversation objects).
USER_KEY = "participant:user"
KIO_KEY = "participant:kio"

_STOPWORDS = frozenset(
    "a an the and or but so if then than to of for with about on at in from by "
    "i you me my your we our he she him his her they them their it its this that "
    "these those is are was were be been being do does did have has had what why "
    "how who when where which there here now just really very like want would "
    "will can could should shall may might am not no yes ok okay please tell say "
    "said says think thinks thought believe believes know knows want wants "
    "suggest suggests recommend recommends prefer prefers decide decided "
    "something anything everything nothing someone anybody else also still "
    "already today tomorrow yesterday".split()
)


def _norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower()).strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SemanticNode:
    """In-memory projection of a stored node."""

    __slots__ = ("id", "session_id", "kind", "name", "key", "description",
                 "status", "meta", "created_at", "updated_at")

    def __init__(self, id, session_id, kind, name, key, description="",
                 status="active", meta=None):
        self.id = id
        self.session_id = session_id
        self.kind = kind
        self.name = name
        self.key = key
        self.description = description
        self.status = status
        self.meta = dict(meta or {})

    @classmethod
    def from_model(cls, m: SemanticNodeModel) -> "SemanticNode":
        meta = {}
        if m.meta_json:
            try:
                import json as _json
                meta = _json.loads(m.meta_json)
            except Exception:
                pass
        return cls(m.id, m.session_id, m.kind, m.name, m.key,
                   m.description or "", m.status or "active", meta)

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<Node {self.id} {self.kind}:{self.name} [{self.status}]>"


class SemanticLink:
    """In-memory projection of a stored link (with resolved names)."""

    __slots__ = ("id", "session_id", "source_id", "target_id", "relation",
                 "attributed_to", "stance", "confidence", "status",
                 "event_time", "supersedes_id", "provenance", "created_at",
                 "source_key", "source_name", "source_kind",
                 "target_key", "target_name", "target_kind")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    @classmethod
    def from_model(cls, m: SemanticLinkModel, nodes: Dict[int, SemanticNode]) -> "SemanticLink":
        src = nodes.get(m.source_id)
        tgt = nodes.get(m.target_id)
        return cls(
            id=m.id, session_id=m.session_id,
            source_id=m.source_id, target_id=m.target_id,
            relation=m.relation, attributed_to=m.attributed_to or "",
            stance=m.stance or "assertion", confidence=m.confidence,
            status=m.status or "active", event_time=m.event_time,
            supersedes_id=m.supersedes_id, provenance=m.provenance or "",
            created_at=m.created_at,
            source_key=src.key if src else "", source_name=src.name if src else "",
            source_kind=src.kind if src else "",
            target_key=tgt.key if tgt else "", target_name=tgt.name if tgt else "",
            target_kind=tgt.kind if tgt else "",
        )

    @property
    def display(self) -> str:
        return f"{self.source_name} -{self.relation}-> {self.target_name}"

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<Link {self.id} {self.display} [{self.status}] by {self.attributed_to}>"


class SemanticGraph:
    """Canonical owner of the semantic graph. ALL state reads/writes go here."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        init_db()

    # ── node ops ──────────────────────────────────────────────────────────
    def ensure_participant(self, name: str, aliases: Optional[List[str]] = None) -> SemanticNode:
        """Ensure an ordinary participant node (user, KIO, or any third party)."""
        base = (name or "user").strip()
        node = self.ensure_node("participant", base)
        if aliases:
            meta = dict(node.meta)
            existing = set(meta.get("aliases", []) or [])
            changed = False
            for a in aliases:
                a = a.strip().lower()
                if a and a not in existing:
                    existing.add(a)
                    changed = True
            if changed:
                meta["aliases"] = sorted(existing)
                node.meta = meta
                self._update_node_meta(node.id, meta)
        return node

    def ensure_node(self, kind: str, name: str, *, description: str = "",
                    meta: Optional[Dict[str, Any]] = None) -> SemanticNode:
        key = f"{kind}:{_norm_key(name)}"
        with db_session() as db:
            row = (
                db.query(SemanticNodeModel)
                .filter(SemanticNodeModel.session_id == self.session_id,
                        SemanticNodeModel.key == key)
                .first()
            )
            if row:
                if row.status == "forgotten":
                    # Explicit re-reference reactivates the entity: forgetting
                    # makes it unavailable to ORDINARY recall, but a direct new
                    # mention re-addresses it (live: forgetting Zorbion then
                    # saying "I'm researching Zorbion Dynamics" again must make
                    # the topic addressable once more — history stays, only the
                    # recall-default changes).
                    row.status = "active"
                    row.updated_at = datetime.now(timezone.utc)
                return SemanticNode.from_model(row)
            row = SemanticNodeModel(
                session_id=self.session_id, kind=kind, name=name.strip(),
                key=key, description=description,
                meta_json=dict(meta or {}),
            )
            db.add(row)
            db.flush()
            return SemanticNode.from_model(row)

    def get_node_by_key(self, key: str) -> Optional[SemanticNode]:
        with db_session() as db:
            row = (
                db.query(SemanticNodeModel)
                .filter(SemanticNodeModel.session_id == self.session_id,
                        SemanticNodeModel.key == key)
                .first()
            )
            return SemanticNode.from_model(row) if row else None

    def get_node(self, node_id: int) -> Optional[SemanticNode]:
        with db_session() as db:
            row = db.get(SemanticNodeModel, node_id)
            return SemanticNode.from_model(row) if row else None

    def forget(self, key: str) -> bool:
        """Exclude a node (and its links) from ordinary recall. History stays."""
        with db_session() as db:
            row = (
                db.query(SemanticNodeModel)
                .filter(SemanticNodeModel.session_id == self.session_id,
                        SemanticNodeModel.key == key)
                .first()
            )
            if not row:
                return False
            row.status = "forgotten"
            db.query(SemanticLinkModel).filter(
                SemanticLinkModel.session_id == self.session_id,
                SemanticLinkModel.status == "active",
                (SemanticLinkModel.source_id == row.id) | (SemanticLinkModel.target_id == row.id),
            ).update({"status": "retracted"}, synchronize_session=False)
            return True

    def set_node_meta(self, node_id: int, meta: Dict[str, Any]) -> bool:
        """Public meta write (e.g. proactive-notified markers). Graph state,
        not a new store."""
        try:
            self._update_node_meta(node_id, dict(meta or {}))
            return True
        except Exception:
            return False

    # ── project representation (general: any project, no per-name logic) ──
    # A project is an ordinary Node with kind="project"; its LIFECYCLE status
    # lives in node meta (descriptive data, not a domain router). Status
    # changes append to status_history — prior state is preserved, never
    # destroyed. Related goals/decisions/claims stay ordinary Links.

    PROJECT_LIFECYCLE_ORDER = (
        "mentioned", "interested", "researching", "planning",
        "building", "active", "paused", "completed", "abandoned",
    )

    def _find_project_identity(self, name: str) -> Optional[SemanticNode]:
        """Unify near-identical project names on ONE node (general project
        identity, no per-name logic): when no exact-key node exists, reuse an
        existing project whose normalized name is CONTAINED in the new name
        or vice versa ("tidal kite turbine" vs "tidal kite turbine
        prototype"), or whose significant tokens overlap substantially.
        "ceramic heat exchanger" and "tidal kite turbine" never collide.
        Returns None when no existing project is plausibly the same one.
        """
        key = f"project:{_norm_key(name)}"
        with db_session() as db:
            rows = (db.query(SemanticNodeModel)
                    .filter(SemanticNodeModel.session_id == self.session_id,
                            SemanticNodeModel.kind == "project")
                    .all())
        if not rows:
            return None
        norm_new = re.sub(r"[^a-z0-9]+", "", name.lower())
        _stop = frozenset(
            "the my our that this these those a an of for with on in at to from "
            "by and or but is are was were be been it its their his her me now "
            "today tomorrow later about around over under new old next last "
            "first again back still also so just very really".split()
        )
        new_toks = set(re.findall(r"[a-z0-9]+", name.lower()))
        new_toks = {t for t in new_toks if len(t) >= 3 and t not in _stop}
        best, best_score = None, 0
        for row in rows:
            existing = (row.name or "").strip()
            norm_ex = re.sub(r"[^a-z0-9]+", "", existing.lower())
            if not norm_ex or not norm_new:
                continue
            score = 0
            if norm_ex in norm_new or norm_new in norm_ex:
                score = max(len(norm_ex), len(norm_new))
            else:
                ex_toks = set(re.findall(r"[a-z0-9]+", existing.lower()))
                ex_toks = {t for t in ex_toks if len(t) >= 3 and t not in _stop}
                if new_toks and ex_toks:
                    shared = len(new_toks & ex_toks)
                    if shared >= 2 and shared * 2 >= max(len(new_toks), 2):
                        score = 100 + shared
            if score > best_score:
                best_score = score
                best = row
        if best is None:
            return None
        return best

    def ensure_project(self, name: str, *, objective: str = "",
                       priority: float = 0.0, confidence: float = 1.0,
                       provenance: str = "", lifecycle: str = "mentioned") -> SemanticNode:
        key = f"project:{_norm_key(name)}"
        with db_session() as db:
            row = (db.query(SemanticNodeModel)
                   .filter(SemanticNodeModel.session_id == self.session_id,
                           SemanticNodeModel.key == key)
                   .first())
            if not row:
                existing_row = self._find_project_identity(name)
                if existing_row is not None:
                    # Reuse the unified node (rename to the fuller name when
                    # the new mention is longer, preserving history).
                    if len(name.strip()) > len((existing_row.name or "")):
                        existing_row.name = name.strip()
                        existing_row.key = key
                    if existing_row.status == "forgotten":
                        existing_row.status = "active"
                        existing_row.updated_at = datetime.now(timezone.utc)
                    db.add(existing_row)
                    db.flush()
                    return SemanticNode.from_model(existing_row)
            if row:
                if row.status == "forgotten":
                    row.status = "active"
                    row.updated_at = datetime.now(timezone.utc)
                return SemanticNode.from_model(row)
            meta = {
                "lifecycle": lifecycle if lifecycle in self.PROJECT_LIFECYCLE_ORDER else "mentioned",
                "objective": objective or "",
                "priority": float(priority or 0.0),
                "created_at": now_iso(),
                "last_activity": now_iso(),
                "confidence": float(confidence or 0.5),
                "provenance": provenance or "",
                "status_history": [],
            }
            row = SemanticNodeModel(session_id=self.session_id, kind="project",
                                    name=name.strip(), key=key, meta_json=meta)
            db.add(row)
            db.flush()
            return SemanticNode.from_model(row)

    def project_state(self, name: str) -> Optional[SemanticNode]:
        return self.get_node_by_key(f"project:{_norm_key(name)}")

    def set_project_status(self, name: str, status: str, *,
                           confidence: float = 1.0, provenance: str = "",
                           objective: str = "") -> Optional[SemanticNode]:
        """Transition a project's lifecycle. History preserved in
        status_history; last_activity refreshed. Idempotent for same status."""
        node = self.ensure_project(name, lifecycle=status, confidence=confidence,
                                   provenance=provenance, objective=objective)
        if status not in self.PROJECT_LIFECYCLE_ORDER:
            status = "mentioned"
        meta = dict(node.meta or {})
        prev = meta.get("lifecycle") or "mentioned"
        hist = list(meta.get("status_history") or [])
        if prev != status:
            hist.append({"from": prev, "to": status, "at": now_iso(),
                         "provenance": provenance or ""})
            meta["lifecycle"] = status
        meta["last_activity"] = now_iso()
        meta["confidence"] = max(float(meta.get("confidence", 0) or 0.5),
                                 float(confidence or 0.5))
        if objective:
            meta["objective"] = objective
        meta["status_history"] = hist[-30:]
        self.set_node_meta(node.id, meta)
        return node

    def active_projects(self) -> List[SemanticNode]:
        out = []
        for n in self.all_active_nodes():
            if n.kind != "project":
                continue
            lc = (n.meta or {}).get("lifecycle") or "mentioned"
            if lc in ("active", "building", "planning", "researching",
                      "interested", "mentioned", "paused"):
                out.append(n)
        out.sort(key=lambda n: (n.meta or {}).get("last_activity") or "", reverse=True)
        return out

    def all_projects(self) -> List[SemanticNode]:
        out = [n for n in self.all_active_nodes() if n.kind == "project"]
        out.sort(key=lambda n: (n.meta or {}).get("last_activity") or "", reverse=True)
        return out

    def _update_node_meta(self, node_id: int, meta: Dict[str, Any]) -> None:
        with db_session() as db:
            row = db.get(SemanticNodeModel, node_id)
            if row:
                row.meta_json = meta

    # ── link ops ──────────────────────────────────────────────────────────
    def add_link(self, source_key: str, target_key: str, relation: str, *,
                 attributed_to: str = "", stance: str = "assertion",
                 confidence: float = 1.0, event_time: Optional[str] = None,
                 supersedes_id: Optional[int] = None,
                 provenance: str = "") -> Optional[SemanticLink]:
        # Attributors are ordinary participant nodes: auto-ensure a missing
        # participant attributor so record_statement('participant:alex', ...)
        # works without a separate ensure call (symmetric for user/KIO/third
        # parties — the key IS the address).
        if source_key.startswith("participant:") and self.get_node_by_key(source_key) is None:
            self.ensure_participant(source_key.split(":", 1)[1] or source_key)
        src = self.get_node_by_key(source_key)
        tgt = self.get_node_by_key(target_key)
        if src is None or tgt is None or src.status == "forgotten":
            return None
        with db_session() as db:
            row = SemanticLinkModel(
                session_id=self.session_id, source_id=src.id, target_id=tgt.id,
                relation=relation, attributed_to=attributed_to,
                stance=stance, confidence=float(confidence),
                event_time=event_time, supersedes_id=supersedes_id,
                provenance=provenance,
            )
            db.add(row)
            db.flush()
            nodes = {src.id: src, tgt.id: tgt}
            return SemanticLink.from_model(row, nodes)

    def record_statement(self, attributor_key: str, claim_text: str, *,
                         about_key: Optional[str] = None,
                         relation: str = "said",
                         stance: str = "assertion",
                         confidence: float = 1.0,
                         event_time: Optional[str] = None,
                         supersede_prior: bool = True,
                         provenance: str = "") -> Optional[SemanticLink]:
        """Record that `attributor` made a statement. A claim is a claim NODE;
        the link carries attribution + stance. Prior active statement by the
        same attributor with the same stance is superseded (correction
        semantics) — history is preserved, never erased."""
        # Ingestion quality gate: malformed decomposer fragments must not become user facts
        _low = (claim_text or "").lower().strip()
        if any(x in _low for x in ("pro pt", "youtubr", "whtever", "puase")):
            return None
        if _low.startswith(("for ", "in ", "on ", "at ", "to ", "the ", "a ", "an ")) and len(_low.split()) >= 3 and not _low.startswith("for me"):
            return None
        claim = self.ensure_node("claim", claim_text.strip())
        link = self.add_link(attributor_key, claim.key, relation,
                             attributed_to=attributor_key, stance=stance,
                             confidence=confidence, event_time=event_time,
                             provenance=provenance)
        if link is None:
            return None
        if about_key:
            self.add_link(claim.key, about_key, "about",
                          attributed_to=attributor_key, stance=stance,
                          provenance="decomposer")
        if supersede_prior:
            for prior in self.attributed_statements(attributor_key, relation=relation,
                                                    stance=stance, active_only=True):
                if prior.id != link.id:
                    self.supersede(prior.id, successor_id=link.id)
        return link

    def attributed_statements(self, attributor_key: str, *,
                              relation: Optional[str] = None,
                              stance: Optional[str] = None,
                              active_only: bool = True,
                              limit: int = 20) -> List[SemanticLink]:
        """What did X say / believe / prefer? Symmetric for user, KIO, third
        parties, sources — one query, no per-participant machinery."""
        with db_session() as db:
            q = db.query(SemanticLinkModel).filter(
                SemanticLinkModel.session_id == self.session_id,
                SemanticLinkModel.attributed_to == attributor_key,
            )
            if relation:
                q = q.filter(SemanticLinkModel.relation == relation)
            if stance:
                q = q.filter(SemanticLinkModel.stance == stance)
            if active_only:
                q = q.filter(SemanticLinkModel.status == "active")
            rows = q.order_by(SemanticLinkModel.id.desc()).limit(limit).all()
            nodes = self._nodes_for(rows)
            return [SemanticLink.from_model(r, nodes) for r in rows]

    def supersede(self, link_id: int, successor_id: Optional[int] = None) -> bool:
        """Mark a link superseded (status + supersedes_id). Prior state stays."""
        with db_session() as db:
            row = db.get(SemanticLinkModel, link_id)
            if not row:
                return False
            row.status = "superseded"
            if successor_id:
                row.supersedes_id = successor_id
            return True

    def contradict(self, link_a_id: int, link_b_id: int) -> Optional[SemanticLink]:
        """Represent that two statements contradict each other. Both survive."""
        a = self._link_row(link_a_id)
        b = self._link_row(link_b_id)
        if a is None or b is None:
            return None
        with db_session() as db:
            src_a = db.get(SemanticNodeModel, a.source_id)
            src_b = db.get(SemanticNodeModel, b.source_id)
            if src_a is None or src_b is None:
                return None
            row = SemanticLinkModel(
                session_id=self.session_id, source_id=src_a.id, target_id=src_b.id,
                relation="contradicts", attributed_to=KIO_KEY,
                stance="observation", confidence=0.9, provenance="evidence-conflict",
            )
            db.add(row)
            db.flush()
            nodes = self._nodes_for([row])
            return SemanticLink.from_model(row, nodes)

    def retract(self, link_id: int) -> bool:
        """'Never mind / don't send that / forget what I said' — retract without
        deleting: the statement stays in history, excluded from active recall."""
        with db_session() as db:
            row = db.get(SemanticLinkModel, link_id)
            if not row:
                return False
            row.status = "retracted"
            return True

    def _link_row(self, link_id: int) -> Optional[SemanticLinkModel]:
        with db_session() as db:
            return db.get(SemanticLinkModel, link_id)

    # ── graph reads for activation / resolution / planner ─────────────────
    def recent_links(self, limit: int = 80, active_only: bool = True) -> List[SemanticLink]:
        with db_session() as db:
            q = db.query(SemanticLinkModel).filter(
                SemanticLinkModel.session_id == self.session_id)
            if active_only:
                q = q.filter(SemanticLinkModel.status == "active")
            rows = q.order_by(SemanticLinkModel.id.desc()).limit(limit).all()
            nodes = self._nodes_for(rows)
            return [SemanticLink.from_model(r, nodes) for r in rows]

    def links_for(self, node_id: int, active_only: bool = True) -> List[SemanticLink]:
        with db_session() as db:
            q = db.query(SemanticLinkModel).filter(
                SemanticLinkModel.session_id == self.session_id,
                (SemanticLinkModel.source_id == node_id) | (SemanticLinkModel.target_id == node_id))
            if active_only:
                q = q.filter(SemanticLinkModel.status == "active")
            rows = q.order_by(SemanticLinkModel.id.desc()).limit(60).all()
            nodes = self._nodes_for(rows)
            return [SemanticLink.from_model(r, nodes) for r in rows]

    def all_active_nodes(self) -> List[SemanticNode]:
        with db_session() as db:
            rows = (
                db.query(SemanticNodeModel)
                .filter(SemanticNodeModel.session_id == self.session_id,
                        SemanticNodeModel.status == "active")
                .order_by(SemanticNodeModel.id.desc())
                .limit(200)
                .all()
            )
            return [SemanticNode.from_model(r) for r in rows]

    def all_nodes_for_forget(self) -> List[SemanticNode]:
        """All nodes regardless of status (active first) for forget-target
        resolution. Forgetting is idempotent and must find BOTH live and
        already-forgotten entities (live: re-forgetting a topic fell through
        to the legacy store because only active nodes were scanned).
        History stays intact — this is recall, not deletion."""
        with db_session() as db:
            rows = (
                db.query(SemanticNodeModel)
                .filter(SemanticNodeModel.session_id == self.session_id)
                .order_by(SemanticNodeModel.status.desc(),
                          SemanticNodeModel.id.desc())
                .limit(300)
                .all()
            )
            return [SemanticNode.from_model(r) for r in rows]

    def _nodes_for(self, links: List[SemanticLinkModel]) -> Dict[int, SemanticNode]:
        ids = set()
        for r in links:
            ids.add(r.source_id)
            ids.add(r.target_id)
        out: Dict[int, SemanticNode] = {}
        if not ids:
            return out
        with db_session() as db:
            for row in db.query(SemanticNodeModel).filter(SemanticNodeModel.id.in_(ids)).all():
                out[row.id] = SemanticNode.from_model(row)
        return out

    # ── maintenance ───────────────────────────────────────────────────────
    def prune(self, keep: int = 400) -> int:
        """Bounded growth: drop the OLDEST active links beyond `keep`, keeping
        node history (nodes are cheap, referenced state is kept by links).
        Returns how many links were removed."""
        removed = 0
        with db_session() as db:
            ids = (
                db.query(SemanticLinkModel.id)
                .filter(SemanticLinkModel.session_id == self.session_id)
                .order_by(SemanticLinkModel.id.desc())
                .offset(keep)
                .all()
            )
            if ids:
                id_list = [r[0] for r in ids]
                db.query(SemanticLinkModel).filter(
                    SemanticLinkModel.id.in_(id_list)).delete(synchronize_session=False)
                removed = len(id_list)
        return removed
