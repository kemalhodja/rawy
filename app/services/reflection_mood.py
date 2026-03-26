"""Günlük yansıtma: basit duygu skoru + kısa özet metni (LLM yok)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import VoiceNote

POS_HINTS = (
    "güzel", "iyi", "mutlu", "harika", "teşekkür", "başarı", "huzurlu",
    "good", "great", "happy", "grateful", "calm", "enerjik",
)
NEG_HINTS = (
    "kötü", "yorgun", "stres", "kaygı", "üzgün", "zor", "sıkıcı",
    "bad", "sad", "tired", "anxious", "worried", "angry",
)


def score_mood(text: str) -> float:
    t = text.lower()
    p = sum(1 for w in POS_HINTS if w in t)
    n = sum(1 for w in NEG_HINTS if w in t)
    if p + n == 0:
        return 0.0
    return max(-1.0, min(1.0, (p - n) / (p + n)))


def build_pattern_snippet(mood: float, text: str) -> str:
    direction = "nötr"
    if mood > 0.15:
        direction = "olumlu eğilim"
    elif mood < -0.15:
        direction = "olumsuz eğilim"
    snippet = (text or "").strip().replace("\n", " ")[:160]
    return f"Duygu özeti: {direction} (skor {mood:.2f}). İlk cümle: {snippet}"


def process_reflection_note(db: Session, note: VoiceNote) -> dict:
    text = (note.transcript or "").strip()
    mood = score_mood(text)
    note.mood_score = mood
    note.reflection_patterns = build_pattern_snippet(mood, text)
    note.ai_category = "reflection"
    tags = list(note.tags) if note.tags else []
    if "yansıtma" not in tags:
        tags.append("yansıtma")
    note.tags = tags
    db.commit()
    return {"mood_score": mood, "patterns": note.reflection_patterns}
