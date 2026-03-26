"""Ses notları: transkript benzerliği (Jaccard) ile otomatik bağlantı + öneri skorları."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import VoiceNote


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\wçğıöşüÇĞİÖŞ]+", text.lower()))


def score_similar_neighbors(
    db: Session, note: VoiceNote, limit: int = 8
) -> tuple[list[tuple[int, float]], str | None]:
    """
    Aynı kullanıcıdaki notlara Jaccard skoru. (id, skor) azalan sırada.
    reason: 'too_short' | None
    """
    text = (note.transcript or "").strip()
    words = _tokens(text)
    if len(words) < 4:
        return [], "too_short"

    others = (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == note.user_id,
            VoiceNote.id != note.id,
            VoiceNote.transcript.isnot(None),
        )
        .order_by(VoiceNote.created_at.desc())
        .limit(400)
        .all()
    )

    scored: list[tuple[float, int]] = []
    for o in others:
        ow = _tokens(o.transcript or "")
        if not ow:
            continue
        inter = len(words & ow)
        if inter < 2:
            continue
        union = len(words | ow) or 1
        jaccard = inter / union
        scored.append((jaccard, o.id))

    scored.sort(key=lambda x: x[0], reverse=True)
    out = [(i, round(s, 4)) for s, i in scored[:limit]]
    return out, None


def find_related_notes(db: Session, note: VoiceNote, limit: int = 8) -> dict:
    """Benzer notları hesaplar ve `related_note_ids` alanına yazar (otomatik bağ)."""
    pairs, reason = score_similar_neighbors(db, note, limit=limit)
    if reason == "too_short":
        note.related_note_ids = []
        db.commit()
        return {"related_note_ids": [], "reason": "too_short"}

    ids = [i for i, _ in pairs]
    note.related_note_ids = ids
    db.commit()
    top = pairs[0][1] if pairs else None
    return {"related_note_ids": ids, "top_score": top}


def suggest_similar_notes(
    db: Session, note: VoiceNote, limit: int = 8
) -> list[dict]:
    """Kalıcı yazmadan öneri listesi (API / UI)."""
    pairs, reason = score_similar_neighbors(db, note, limit=limit)
    if reason == "too_short":
        return []
    return [{"note_id": i, "score": s, "kind": "similarity"} for i, s in pairs]
