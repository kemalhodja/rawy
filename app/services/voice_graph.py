"""
Graf görünümü: kenarlar = otomatik benzerlik + ortak [[wikilink]].
İsteğe bağlı: öneri kenarları (henüz kayıtlı olmayan yüksek skorlu komşular).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.models import VoiceNote
from app.services.note_graph_insights import extract_wikilinks
from app.services.note_similarity import score_similar_neighbors


def _bfs_nodes(adj: dict[int, set[int]], start: int, hops: int) -> set[int]:
    if hops <= 0:
        return {start}
    seen: set[int] = {start}
    frontier: set[int] = {start}
    for _ in range(hops):
        nxt: set[int] = set()
        for u in frontier:
            for v in adj.get(u, ()):
                if v not in seen:
                    seen.add(v)
                    nxt.add(v)
        frontier = nxt
    return seen


def build_voice_graph(
    db: Session,
    user_id: int,
    *,
    center_id: int | None = None,
    max_hops: int = 2,
    note_limit: int = 500,
    include_suggested_edges: bool = False,
) -> dict[str, Any]:
    """
    max_hops: merkezden en fazla bu kadar kenar uzaklık (2 tık = 2).
    """
    notes = (
        db.query(VoiceNote)
        .filter(VoiceNote.user_id == user_id, VoiceNote.transcript.isnot(None))
        .order_by(VoiceNote.created_at.desc())
        .limit(note_limit)
        .all()
    )
    if center_id is not None:
        have = {n.id for n in notes}
        if center_id not in have:
            extra = (
                db.query(VoiceNote)
                .filter(VoiceNote.id == center_id, VoiceNote.user_id == user_id)
                .first()
            )
            if not extra or not (extra.transcript or "").strip():
                return {
                    "nodes": [],
                    "edges": [],
                    "view": {"default": "graph", "max_hops": max_hops, "error": "center_not_found"},
                }
            notes.insert(0, extra)

    nid = {n.id for n in notes}
    if not notes:
        return {
            "nodes": [],
            "edges": [],
            "view": {"default": "graph", "max_hops": max_hops},
        }

    # Kenar türü -> (a,b) kümesi, a < b
    edge_kinds: dict[tuple[int, int], set[str]] = defaultdict(set)
    adj: dict[int, set[int]] = defaultdict(set)

    def add_edge(a: int, b: int, kind: str) -> None:
        if a == b:
            return
        u, v = (a, b) if a < b else (b, a)
        edge_kinds[(u, v)].add(kind)
        adj[a].add(b)
        adj[b].add(a)

    anchor_to_ids: dict[str, list[int]] = defaultdict(list)
    for n in notes:
        for a in extract_wikilinks(n.transcript or ""):
            anchor_to_ids[a.strip()].append(n.id)

    for ids in anchor_to_ids.values():
        uq = list({i for i in ids if i in nid})
        for i in range(len(uq)):
            for j in range(i + 1, len(uq)):
                add_edge(uq[i], uq[j], "wikilink")

    for n in notes:
        for rid in n.related_note_ids or []:
            if rid in nid:
                add_edge(n.id, rid, "auto_link")

    if include_suggested_edges and center_id and center_id in nid:
        cn = db.query(VoiceNote).filter(VoiceNote.id == center_id).first()
        if cn:
            pairs, _ = score_similar_neighbors(db, cn, limit=12)
            for oid, _sc in pairs:
                if oid in nid:
                    add_edge(center_id, oid, "suggested")

    nodes_subset: set[int] | None = None
    if center_id is not None:
        nodes_subset = _bfs_nodes(adj, center_id, max_hops)
        nodes_subset.add(center_id)

    nodes_out: list[dict[str, Any]] = []
    id_to_note = {n.id: n for n in notes}
    ids_render = sorted(nodes_subset) if nodes_subset is not None else sorted(id_to_note.keys())

    for i in ids_render:
        n = id_to_note.get(i)
        if not n:
            continue
        tr = n.transcript or ""
        nodes_out.append(
            {
                "id": n.id,
                "title": n.title or f"Not #{n.id}",
                "preview": tr[:120] + ("..." if len(tr) > 120 else ""),
                "wikilinks": extract_wikilinks(tr),
                "recording_type": n.recording_type or "quick_note",
            }
        )

    allowed = set(ids_render)
    edges_out: list[dict[str, Any]] = []
    for (u, v), kinds in edge_kinds.items():
        if u not in allowed or v not in allowed:
            continue
        edges_out.append(
            {
                "source": u,
                "target": v,
                "kinds": sorted(kinds),
            }
        )

    return {
        "nodes": nodes_out,
        "edges": edges_out,
        "view": {
            "default": "graph",
            "max_hops": max_hops,
            "center_id": center_id,
            "edge_legend": {
                "auto_link": "Transkript benzerliği (kayıtlı)",
                "wikilink": "Ortak [[köprü]]",
                "suggested": "AI önerisi (yüksek skor)",
            },
        },
    }
