"""Transkript sonrası kayıt türüne göre işlem."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import VoiceNote
from app.services.intent_pipeline import run_intent_pipeline
from app.services.meeting_processor import process_meeting_note
from app.services.focus_debrief import process_focus_debrief
from app.services.note_similarity import find_related_notes
from app.services.reflection_mood import process_reflection_note


def run_post_processing(db: Session, note_id: int) -> dict:
    note = db.query(VoiceNote).filter(VoiceNote.id == note_id).first()
    if not note or not note.transcript:
        return {"skipped": True, "reason": "no_transcript"}

    rt = note.recording_type or "quick_note"
    merged: dict = {"recording_type": rt}

    if rt == "meeting":
        merged.update(process_meeting_note(db, note))
        merged.update(run_intent_pipeline(db, note_id))
        note = db.query(VoiceNote).filter(VoiceNote.id == note_id).first()
        if note:
            note.ai_category = "meeting"
            db.commit()

    elif rt == "walking":
        merged.update(run_intent_pipeline(db, note_id))

    elif rt == "reflection":
        merged.update(process_reflection_note(db, note))

    elif rt == "focus_debrief":
        merged.update(process_focus_debrief(db, note))

    elif rt == "focus_idea":
        merged.update(run_intent_pipeline(db, note_id))

    else:
        merged.update(run_intent_pipeline(db, note_id))

    # Tüm ses notları: transkript benzerliği ile otomatik bağlantı (related_note_ids)
    note = db.query(VoiceNote).filter(VoiceNote.id == note_id).first()
    if note and (note.transcript or "").strip():
        merged.update(find_related_notes(db, note))
    return merged
