"""Odak bitişi: 'nasıl geçti?' sesli log — kısa duygu özeti (LLM yok)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import VoiceNote
from app.services.reflection_mood import build_pattern_snippet, score_mood


def process_focus_debrief(db: Session, note: VoiceNote) -> dict:
    text = (note.transcript or "").strip()
    mood = score_mood(text)
    note.mood_score = mood
    note.reflection_patterns = build_pattern_snippet(mood, text)
    note.ai_category = "focus_debrief"
    tags = list(note.tags) if note.tags else []
    for t in ("odak", "nasıl geçti"):
        if t not in tags:
            tags.append(t)
    note.tags = tags
    db.commit()
    return {"mood_score": mood, "kind": "focus_debrief"}
