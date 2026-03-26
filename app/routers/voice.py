from datetime import date, datetime, timedelta, timezone
from datetime import time as dt_time

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import get_current_user
from app.models import FocusBlock, Task, User, VoiceNote
from app.services.note_graph_insights import (
    extract_wikilinks,
    find_notes_by_anchor_title,
    pair_theme_analysis,
)
from app.services.note_similarity import suggest_similar_notes
from app.services.billing import can_upload_voice
from app.services.post_processing import run_post_processing
from app.services.voice_graph import build_voice_graph
from app.services.recording_types import normalize_recording_type
from app.services.storage import storage_service
from app.services.whisper_service import whisper_service

router = APIRouter()

ALLOWED_TYPES = frozenset(
    {
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/mp4",
        "audio/webm",
        "audio/ogg",
    }
)


def _parse_client_recorded_at(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


@router.post("/upload")
async def upload_voice(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    recording_type: str = Form("quick_note"),
    client_id: str | None = Form(None),
    language: str | None = Form(None),
    client_recorded_at: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Desteklenmeyen format: {file.content_type}")

    cid = (client_id or "").strip()[:64]
    if cid:
        existing = (
            db.query(VoiceNote)
            .filter(VoiceNote.user_id == current_user.id, VoiceNote.client_id == cid)
            .first()
        )
        if existing:
            return {
                "id": existing.id,
                "status": "duplicate",
                "deduplicated": True,
                "recording_type": existing.recording_type,
                "is_processed": existing.is_processed,
                "message": "Bu kayıt zaten senkronize edildi",
            }

    ok_upload, upload_info = can_upload_voice(db, current_user)
    if not ok_upload:
        raise HTTPException(
            403,
            detail={
                "code": upload_info.get("code", "STARTER_VOICE_LIMIT"),
                "message_tr": upload_info.get("message_tr", "Ses kotası"),
                "voice_uploads_this_month": upload_info.get("voice_uploads_this_month"),
                "voice_upload_limit": upload_info.get("voice_upload_limit"),
                "upgrade": "https://rawy.app/plans",
            },
        )

    await file.seek(0)
    file_info = storage_service.save_upload(file, current_user.id)

    req_lang = (language.strip()[:16] if language and language.strip() else None)

    voice_note = VoiceNote(
        user_id=current_user.id,
        original_filename=file_info["original_filename"],
        storage_path=file_info["storage_path"],
        file_size=file_info["file_size"],
        mime_type=file_info["mime_type"],
        is_processed=False,
        recording_type=normalize_recording_type(recording_type),
        client_id=cid or None,
        client_recorded_at=_parse_client_recorded_at(client_recorded_at),
        requested_language=req_lang,
    )
    db.add(voice_note)
    db.commit()
    db.refresh(voice_note)

    background_tasks.add_task(process_transcription, voice_note.id)

    return {
        "id": voice_note.id,
        "status": "processing",
        "recording_type": voice_note.recording_type,
        "client_id": voice_note.client_id,
        "message": "Ses kaydedildi, transkript işleniyor",
        "file_info": {
            "original_name": file_info["original_filename"],
            "size_bytes": file_info["file_size"],
        },
    }


@router.get("/")
def list_voice_notes(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notes = (
        db.query(VoiceNote)
        .filter(VoiceNote.user_id == current_user.id)
        .order_by(VoiceNote.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [
        {
            "id": n.id,
            "title": n.title or f"Not #{n.id}",
            "preview": (n.transcript or "")[:100] + "..."
            if n.transcript and len(n.transcript) > 100
            else (n.transcript or ""),
            "is_processed": n.is_processed,
            "ai_category": n.ai_category,
            "recording_type": getattr(n, "recording_type", None) or "quick_note",
            "client_id": n.client_id,
            "quick_capture_exceeded": bool(getattr(n, "quick_capture_exceeded", False)),
            "related_count": len(n.related_note_ids) if n.related_note_ids else 0,
            "task_converted": bool(getattr(n, "task_converted", False)),
            "review_status": getattr(n, "review_status", None),
            "review_at": getattr(n, "review_at", None),
            "capsule_at": getattr(n, "capsule_at", None),
            "created_at": n.created_at,
        }
        for n in notes
    ]

    return {
        "items": items,
        "view": {
            "default": "graph",
            "max_hops": 2,
            "graph_path": "/voice/graph",
            "hint": "Liste varsayılanı graf ile uyumlu; 2 tık = graph?hops=2",
        },
    }


@router.get("/insights/weekly")
def weekly_reflection_insights(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Günlük yansıtma kayıtları: haftalık özet (mood ortalaması + liste)."""
    d = date.fromisocalendar(year, week, 1)
    start = datetime.combine(d, dt_time.min)
    end = start + timedelta(days=7)
    notes = (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == current_user.id,
            VoiceNote.recording_type == "reflection",
            VoiceNote.created_at >= start,
            VoiceNote.created_at < end,
        )
        .order_by(VoiceNote.created_at.asc())
        .all()
    )
    moods = [n.mood_score for n in notes if n.mood_score is not None]
    avg_mood = sum(moods) / len(moods) if moods else None

    return {
        "year": year,
        "week": week,
        "count": len(notes),
        "average_mood": round(avg_mood, 4) if avg_mood is not None else None,
        "entries": [
            {
                "id": n.id,
                "created_at": n.created_at,
                "mood_score": n.mood_score,
                "reflection_patterns": n.reflection_patterns,
                "title": n.title,
            }
            for n in notes
        ],
    }


@router.post("/{note_id}/set-review")
def set_review(
    note_id: int,
    hours: int = Query(48, ge=1, le=24 * 30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(404, "Not bulunamadı")
    note.review_at = datetime.now(timezone.utc) + timedelta(hours=hours)
    note.review_status = "waiting"
    db.commit()
    db.refresh(note)
    return {"id": note.id, "review_at": note.review_at, "review_status": note.review_status}


@router.get("/review-due")
def list_review_due(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    notes = (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == current_user.id,
            VoiceNote.review_status == "waiting",
            VoiceNote.review_at.isnot(None),
            VoiceNote.review_at <= now,
        )
        .order_by(VoiceNote.review_at.asc())
        .all()
    )
    return {
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "review_at": n.review_at,
                "review_status": n.review_status,
            }
            for n in notes
        ]
    }


@router.post("/{note_id}/review-answer")
def review_answer(
    note_id: int,
    answer: str = Query(..., description="evet|hayir|ertele"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(404, "Not bulunamadı")
    ans = (answer or "").strip().lower()
    if ans not in {"evet", "hayir", "ertele"}:
        raise HTTPException(400, "answer: evet|hayir|ertele olmalı")
    if ans == "evet":
        note.review_status = "kept"
    elif ans == "hayir":
        note.review_status = "dropped"
    else:
        note.review_status = "snoozed"
        note.review_at = datetime.now(timezone.utc) + timedelta(hours=24)
    db.commit()
    db.refresh(note)
    return {"id": note.id, "review_status": note.review_status, "review_at": note.review_at}


@router.post("/{note_id}/capsule")
def set_capsule(
    note_id: int,
    days: int = Query(90, ge=1, le=3650),
    message: str = Query("Su anki ben, gecmis sana..."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(404, "Not bulunamadı")
    note.capsule_at = datetime.now(timezone.utc) + timedelta(days=days)
    note.capsule_message = (message or "").strip()[:1000] or "Su anki ben, gecmis sana..."
    db.commit()
    db.refresh(note)
    return {"id": note.id, "capsule_at": note.capsule_at, "capsule_message": note.capsule_message}


@router.get("/capsule-due")
def list_capsule_due(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    notes = (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == current_user.id,
            VoiceNote.capsule_at.isnot(None),
            VoiceNote.capsule_at <= now,
            VoiceNote.capsule_delivered_at.is_(None),
        )
        .order_by(VoiceNote.capsule_at.asc())
        .all()
    )
    return {
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "capsule_at": n.capsule_at,
                "capsule_message": n.capsule_message,
            }
            for n in notes
        ]
    }


@router.post("/{note_id}/capsule-delivered")
def mark_capsule_delivered(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(404, "Not bulunamadı")
    note.capsule_delivered_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(note)
    return {"id": note.id, "capsule_delivered_at": note.capsule_delivered_at}


@router.get("/insights/pair-themes")
def pair_themes_between_notes(
    a: int = Query(..., description="Birinci not id"),
    b: int = Query(..., description="İkinci not id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    İki notun transkriptinde ortak [[wikilink]] + ortak anlamlı kelimeler;
    örnek mesaj: "Bu iki not arasında 3 ortak tema var: ..."
    """
    na = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == a, VoiceNote.user_id == current_user.id)
        .first()
    )
    nb = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == b, VoiceNote.user_id == current_user.id)
        .first()
    )
    if not na or not nb:
        raise HTTPException(404, "Not bulunamadı")
    insight = pair_theme_analysis(na.transcript, nb.transcript)
    return {
        "note_a_id": a,
        "note_b_id": b,
        **insight,
    }


@router.get("/insights/by-anchor")
def notes_by_wikilink_anchor(
    title: str = Query(..., min_length=1, description="Örn. Proje X — [[Proje X]] aranır"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aynı köprü başlığını paylaşan notlar (Not A → [[Proje X]] → Not B grafiği için)."""
    notes = find_notes_by_anchor_title(db, current_user.id, title)
    t = title.strip()
    return {
        "anchor_title": t,
        "count": len(notes),
        "notes": [{"id": n.id, "title": n.title, "created_at": n.created_at} for n in notes],
    }


@router.get("/graph")
def voice_graph(
    center: int | None = Query(None, description="Merkez not; boşsa son notlar kümesi"),
    hops: int = Query(2, ge=1, le=4, description="2 = iki kenar (iki tık)"),
    include_suggested: bool = Query(
        False, description="Merkez için ek AI benzerlik kenarları"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Graf düğümleri + kenarlar (otomatik bağlantı + wikilink)."""
    if center is not None:
        cn = (
            db.query(VoiceNote)
            .filter(VoiceNote.id == center, VoiceNote.user_id == current_user.id)
            .first()
        )
        if not cn:
            raise HTTPException(404, "Merkez not bulunamadı")
        if not (cn.transcript or "").strip():
            raise HTTPException(400, "Merkez notta transkript yok")

    return build_voice_graph(
        db,
        current_user.id,
        center_id=center,
        max_hops=hops,
        include_suggested_edges=include_suggested,
    )


@router.get("/{note_id}/link-suggestions")
def voice_link_suggestions(
    note_id: int,
    limit: int = Query(8, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI benzer not önerileri (kalıcı bağlantıdan önce UI’da göster)."""
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(404, "Not bulunamadı")
    if not (note.transcript or "").strip():
        return {"note_id": note_id, "suggestions": [], "reason": "no_transcript"}
    return {
        "note_id": note_id,
        "suggestions": suggest_similar_notes(db, note, limit=limit),
    }


@router.get("/{note_id}")
def get_voice_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(404, "Not bulunamadı")

    return {
        "id": note.id,
        "title": note.title or "İsimsiz Not",
        "transcript": note.transcript,
        "language": note.language,
        "confidence": note.transcript_confidence,
        "is_processed": note.is_processed,
        "processing_error": note.processing_error,
        "created_at": note.created_at,
        "duration_seconds": note.duration,
        "ai_category": note.ai_category,
        "tags": list(note.tags) if note.tags else [],
        "linked_task_id": note.linked_task_id,
        "task_converted": bool(getattr(note, "task_converted", False)),
        "linked_focus_block_id": note.linked_focus_block_id,
        "pipeline_error": note.pipeline_error,
        "recording_type": getattr(note, "recording_type", None) or "quick_note",
        "meeting_summary": note.meeting_summary,
        "meeting_action_items": note.meeting_action_items,
        "related_note_ids": list(note.related_note_ids) if note.related_note_ids else [],
        "mood_score": note.mood_score,
        "reflection_patterns": note.reflection_patterns,
        "client_id": note.client_id,
        "client_recorded_at": note.client_recorded_at,
        "requested_language": note.requested_language,
        "quick_capture_exceeded": bool(note.quick_capture_exceeded),
        "review_at": getattr(note, "review_at", None),
        "review_status": getattr(note, "review_status", None),
        "capsule_at": getattr(note, "capsule_at", None),
        "capsule_message": getattr(note, "capsule_message", None),
        "capsule_delivered_at": getattr(note, "capsule_delivered_at", None),
        "wikilinks": extract_wikilinks(note.transcript or ""),
    }


@router.delete("/{note_id}")
def delete_voice_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(404, "Not bulunamadı")

    storage_service.delete_file(note.storage_path)
    db.delete(note)
    db.commit()
    return {"deleted": True, "id": note_id}


@router.post("/{note_id}/run-pipeline")
def run_pipeline_manual(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transkript hazırsa kategori + takvim/görev hattını yeniden çalıştırır."""
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(404, "Not bulunamadı")
    if not note.transcript:
        raise HTTPException(400, "Önce transkript tamamlanmalı")

    linked_task_id = note.linked_task_id
    linked_fb_id = note.linked_focus_block_id
    note.linked_task_id = None
    note.linked_focus_block_id = None
    note.pipeline_error = None
    note.ai_category = None
    note.meeting_summary = None
    note.meeting_action_items = None
    note.related_note_ids = None
    note.mood_score = None
    note.reflection_patterns = None
    db.flush()

    db.query(Task).filter(Task.source_voice_note_id == note_id).delete(synchronize_session=False)
    if linked_task_id:
        t = db.query(Task).filter(Task.id == linked_task_id).first()
        if t:
            db.delete(t)

    if linked_fb_id:
        fb = db.query(FocusBlock).filter(FocusBlock.id == linked_fb_id).first()
        if fb:
            db.delete(fb)
    db.query(FocusBlock).filter(FocusBlock.source_voice_note_id == note_id).delete(
        synchronize_session=False
    )
    db.commit()
    return run_post_processing(db, note_id)


def process_transcription(note_id: int) -> None:
    ok = False
    db = SessionLocal()
    try:
        note = db.query(VoiceNote).filter(VoiceNote.id == note_id).first()
        if not note:
            return

        result = whisper_service.transcribe(
            note.storage_path, language=note.requested_language
        )

        note.transcript = result["text"]
        note.language = result["language"]
        note.transcript_confidence = result["confidence"]
        note.duration = result["duration"]
        note.is_processed = True

        if (note.recording_type or "") == "quick_capture":
            dur = float(result.get("duration") or 0)
            if dur > settings.QUICK_CAPTURE_MAX_SECONDS:
                note.quick_capture_exceeded = True

        words = result["text"].split()[:5]
        note.title = " ".join(words) + ("..." if len(result["text"].split()) > 5 else "")

        db.commit()
        ok = True
    except Exception as e:
        db.rollback()
        note = db.query(VoiceNote).filter(VoiceNote.id == note_id).first()
        if note:
            note.processing_error = str(e)
            db.commit()
    finally:
        db.close()

    if ok:
        pipe = SessionLocal()
        try:
            run_post_processing(pipe, note_id)
        finally:
            pipe.close()
