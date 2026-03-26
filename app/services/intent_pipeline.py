"""
Transkript sonrası: kategori → (takvim | görev | not) + etiket önerisi.
Wispr Flow benzeri kural tabanlı MVP (harici LLM yok).
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models import FocusBlock, Task, User, VoiceNote
from app.services.calendar_logic import apply_buffer_before_start, focus_duration_hours
from app.services.voice_deadline import has_deadline_speech, parse_task_deadline
from app.services.voice_planning import has_time_range, parse_voice_planning


def classify_transcript(text: str) -> str:
    """Dönüş: calendar | task | note"""
    t = text.lower()
    task_kw = (
        "yapılacak",
        "yapilacak",
        "görev",
        "gorev",
        "hatırlat",
        "hatirlat",
        "todo",
        "unutma",
        "deadline",
        "remind",
        "listeme ekle",
        "alıyorum",
    )

    if has_time_range(text):
        return "calendar"
    if any(k in t for k in task_kw) or has_deadline_speech(text):
        return "task"
    return "note"


def suggest_tags(text: str, max_n: int = 5) -> list[str]:
    tags: list[str] = []
    for m in re.finditer(r"#([\w\u00c0-\u024f]+)", text, re.UNICODE):
        tags.append(m.group(1)[:48])
    hints = (
        ("toplantı", "toplantı"),
        ("meeting", "meeting"),
        ("iş", "iş"),
        ("kişisel", "kişisel"),
        ("proje", "proje"),
        ("fikir", "fikir"),
        ("sağlık", "sağlık"),
    )
    low = text.lower()
    for needle, label in hints:
        if needle in low and label not in tags:
            tags.append(label)
    return tags[:max_n]


def extract_task_title(text: str) -> str:
    one = text.strip().split("\n")[0].strip()
    if len(one) > 400:
        return one[:397] + "..."
    return one or "Görev"


def _overlap(
    db: Session, user_id: int, start: datetime, end: datetime
) -> FocusBlock | None:
    return (
        db.query(FocusBlock)
        .filter(
            FocusBlock.user_id == user_id,
            FocusBlock.start_at < end,
            FocusBlock.end_at > start,
        )
        .first()
    )


def run_intent_pipeline(db: Session, note_id: int) -> dict:
    note = db.query(VoiceNote).filter(VoiceNote.id == note_id).first()
    if not note or not note.transcript:
        return {"skipped": True, "reason": "no_transcript"}

    user = db.query(User).filter(User.id == note.user_id).first()
    if not user:
        return {"skipped": True, "reason": "no_user"}

    text = note.transcript.strip()
    tz = user.timezone or "UTC"
    category = classify_transcript(text)
    note.ai_category = category

    tags = suggest_tags(text)
    if tags:
        note.tags = tags

    result: dict = {"category": category, "tags": tags}

    try:
        if category == "calendar":
            try:
                start, end, title = parse_voice_planning(text, tz)
            except ValueError:
                note.ai_category = "note"
                result["category"] = "note"
                result["calendar_parse_failed"] = True
                db.commit()
                return result

            buf_start, buf_end, adjusted = apply_buffer_before_start(
                db, user.id, start, end
            )
            if _overlap(db, user.id, buf_start, buf_end):
                note.pipeline_error = "Takvim: bu aralıkta başka blok var"
                db.commit()
                result["calendar_skipped"] = "overlap"
                return result

            hours = focus_duration_hours(buf_start, buf_end)
            is_focus = settings.FOCUS_BLOCK_MIN_HOURS <= hours <= settings.FOCUS_BLOCK_MAX_HOURS

            block = FocusBlock(
                user_id=user.id,
                title=title[:500],
                start_at=buf_start,
                end_at=buf_end,
                is_focus=is_focus,
                source="voice_pipeline" if not adjusted else "voice_pipeline+buffer",
                source_voice_note_id=note.id,
            )
            db.add(block)
            db.flush()
            note.linked_focus_block_id = block.id
            result["focus_block_id"] = block.id
            result["adjusted_for_buffer"] = adjusted

        elif category == "task" and (note.recording_type or "") == "meeting":
            result["task_skipped"] = "meeting_action_items"
            result["note_only"] = True
            db.commit()
            return result

        elif category == "task":
            t_title = extract_task_title(text)
            due_at = parse_task_deadline(text, tz)
            task = Task(
                user_id=user.id,
                title=t_title[:500],
                done=False,
                due_at=due_at,
                depth="shallow",
                source_voice_note_id=note.id,
            )
            db.add(task)
            db.flush()
            note.linked_task_id = task.id
            note.task_converted = True
            result["task_id"] = task.id
            if due_at is not None:
                result["due_at"] = due_at.isoformat()

        else:
            result["note_only"] = True

        db.commit()
        return result

    except Exception as e:
        db.rollback()
        note = db.query(VoiceNote).filter(VoiceNote.id == note_id).first()
        if note:
            note.pipeline_error = str(e)[:2000]
            db.commit()
        result["error"] = str(e)
        return result
