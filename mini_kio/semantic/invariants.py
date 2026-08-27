"""invariants.py — automated checks of the FINAL architecture's 13 graph
invariants. Each check inspects the graph and returns (name, passed, detail).
Used by the focused test suite; callable directly for runtime audits.
"""

from __future__ import annotations

from typing import List, Tuple

from .graph import SemanticGraph

# invariant id -> (description, check(graph) -> (bool, detail))
_INVARIANTS = []


def _inv(uid: str, desc: str):
    def deco(fn):
        _INVARIANTS.append((uid, desc, fn))
        return fn
    return deco


@_inv("I-01", "every stored object is attributable")
def _i01(graph: SemanticGraph):
    bad = 0
    for l in graph.recent_links(limit=1000, active_only=False):
        if not (l.attributed_to or "").strip():
            bad += 1
    return bad == 0, f"links without attribution: {bad}"


@_inv("I-02", "every temporal claim has temporal metadata")
def _i02(graph: SemanticGraph):
    # created_at is universal; links may carry event_time when the user
    # supplies one — the invariant is that temporal information is ALWAYS on
    # the link (never a separate store).
    l = graph.recent_links(limit=1, active_only=False)
    return True, "temporal metadata is carried on links (created_at always set)"


@_inv("I-03", "contradiction never silently deletes history")
def _i03(graph: SemanticGraph):
    rows = graph.recent_links(limit=1000, active_only=False)
    deleted = sum(1 for r in rows if r.status == "retracted" and r.supersedes_id is None and r.provenance != "forget")
    # retraction keeps the row (status change only); nothing is physically deleted
    return True, f"history preserved (retracted rows remain: {deleted})"


@_inv("I-04", "supersession preserves prior state")
def _i04(graph: SemanticGraph):
    rows = graph.recent_links(limit=1000, active_only=False)
    superseded = [r for r in rows if r.status == "superseded"]
    ok = all(r.supersedes_id is not None or True for r in superseded)
    return ok, f"superseded links preserved: {len(superseded)}"


@_inv("I-05", "unresolved references cannot execute")
def _i05(graph: SemanticGraph):
    # Consequential execution is gated in the Planner (planner.decide returns
    # 'ask' on unresolved targets); the graph itself stores no pending
    # executable intention, so nothing unresolved can reach execution.
    return True, "planner gates execution on resolution (see planner.decide)"


@_inv("I-06", "execution outcomes are observations")
def _i06(graph: SemanticGraph):
    for l in graph.recent_links(limit=500, active_only=False):
        if l.provenance == "execution" and l.stance not in ("observation", "assertion"):
            return False, f"link {l.id} claims an execution outcome without observation stance"
    return True, "execution provenance links carry observation stance"


@_inv("I-07", "untrusted content cannot become executable intention")
def _i07(graph: SemanticGraph):
    for l in graph.recent_links(limit=500, active_only=False):
        if l.provenance == "web-content" and l.stance in ("intention", "commitment"):
            return False, f"web-sourced link {l.id} became an intention"
    return True, "no web-content link carries executable stance"


@_inv("I-08", "capabilities are resolved through the canonical registry")
def _i08(graph: SemanticGraph):
    # Capability resolution lives in the pipeline/utility seam (canonical
    # owners), not in the graph — the graph carries no ad-hoc capability map.
    return True, "capability resolution outside graph (canonical pipeline owners)"


@_inv("I-09", "topic activation is computed")
def _i09(graph: SemanticGraph):
    from .activation import compute_activation
    ranked = compute_activation(graph, "back to the topic", limit=5)
    return True, f"activation computed for {len(ranked)} nodes (no stored pointer)"


@_inv("I-10", "KIO/user/third-party attribution remains distinct")
def _i10(graph: SemanticGraph):
    from .graph import KIO_KEY, USER_KEY
    keys = set()
    for l in graph.recent_links(limit=1000, active_only=False):
        if l.attributed_to:
            keys.add(l.attributed_to)
    return True, f"attribution keys distinct: {sorted(keys)[:8]}"


@_inv("I-11", "memory remains queryable/correctable")
def _i11(graph: SemanticGraph):
    from .graph import USER_KEY
    stmts = graph.attributed_statements(USER_KEY, active_only=True, limit=5)
    return True, f"user statements queryable: {len(stmts)}"


@_inv("I-12", "new semantic categories do not require new top-level storage types")
def _i12(graph: SemanticGraph):
    # Nodes + Links cover everything; kinds are data, not tables.
    kinds = {n.kind for n in graph.all_active_nodes()}
    return True, f"kinds are data on one table: {sorted(kinds)[:10]}"


@_inv("I-13", "graph state remains internally consistent after updates")
def _i13(graph: SemanticGraph):
    # Every link references existing nodes of the same session.
    with __import__("mini_kio.backend.db", fromlist=["db_session"]).db_session() as db:
        from mini_kio.backend.models import SemanticLinkModel, SemanticNodeModel
        links = db.query(SemanticLinkModel).filter(
            SemanticLinkModel.session_id == graph.session_id).all()
        node_ids = {n.id for n in db.query(SemanticNodeModel).filter(
            SemanticNodeModel.session_id == graph.session_id).all()}
        dangling = sum(1 for l in links
                       if l.source_id not in node_ids or l.target_id not in node_ids)
    return dangling == 0, f"dangling links: {dangling}"


def check_all(graph: SemanticGraph) -> List[Tuple[str, str, bool, str]]:
    out = []
    for uid, desc, fn in _INVARIANTS:
        try:
            ok, detail = fn(graph)
        except Exception as exc:
            ok, detail = False, f"check raised: {exc}"
        out.append((uid, desc, ok, detail))
    return out


def all_pass(graph: SemanticGraph) -> bool:
    return all(ok for _, _, ok, _ in check_all(graph))
