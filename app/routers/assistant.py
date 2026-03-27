"""Metin tabanlı minimal asistan (LLM yok): haftalık özet, arama, yarın planı."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, VoiceNote
from app.services.ai_smart import smart_ai_service
from app.services.assistant_lindy import (
    dispatch_message,
    interpret_user_message,
    search_ideas_transcripts,
    suggest_tomorrow_plan,
    weekly_what_did_i_do,
)

router = APIRouter()


class SearchBody(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class WeeklyEmailBody(BaseModel):
    to_email: str | None = None


@router.post("/weekly-summary")
def assistant_weekly_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """«Bu hafta ne yaptım?» — özet + sesli notlardan kısa alıntılar."""
    return weekly_what_did_i_do(db, current_user)


@router.post("/search")
def assistant_search(
    body: SearchBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transkript/başlıkta anahtar kelime; ilişkili not id'leri ile."""
    return search_ideas_transcripts(db, current_user, body.query)


@router.post("/tomorrow-plan")
def assistant_tomorrow_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Yarın için kural tabanlı ajanda / görev önerisi."""
    return suggest_tomorrow_plan(db, current_user)


@router.post("/chat")
def assistant_chat(
    body: ChatBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Serbest metin — sınırlı kalıplarla yönlendirme.
    Örnek: «Bu hafta ne yaptım?», «Fikirlerimde 'ürün' geçenleri bul», «Yarın için plan öner»
    """
    return dispatch_message(db, current_user, body.message)


@router.get("/interpret-preview")
def assistant_interpret_preview(
    message: str = Query(..., min_length=1, max_length=2000),
    current_user: User = Depends(get_current_user),
):
    """Sadece niyet önizlemesi (DB sorgusu yok)."""
    _ = current_user
    return interpret_user_message(message)


@router.get("/daily-summary")
def assistant_daily_summary(
    days: int = Query(1, ge=1, le=7),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tz = ZoneInfo(current_user.timezone or "UTC")
    now = datetime.now(tz)
    start = datetime.combine((now - timedelta(days=days - 1)).date(), time.min, tzinfo=tz)
    end = now + timedelta(minutes=1)
    notes = (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == current_user.id,
            VoiceNote.created_at >= start,
            VoiceNote.created_at < end,
            VoiceNote.transcript.isnot(None),
        )
        .order_by(VoiceNote.created_at.asc())
        .all()
    )
    corpus = "\n".join((n.transcript or "").strip() for n in notes if (n.transcript or "").strip())
    summary = smart_ai_service.summarize(corpus)
    mood = smart_ai_service.sentiment(corpus)
    return {
        "intent": "daily_summary",
        "days": days,
        "note_count": len(notes),
        "summary_tr": summary["summary"],
        "summary_meta": {"model": summary.get("model"), "fallback": summary.get("fallback")},
        "sentiment": mood,
    }


@router.get("/weekly-themes")
def assistant_weekly_themes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tz = ZoneInfo(current_user.timezone or "UTC")
    now = datetime.now(tz)
    start = datetime.combine((now - timedelta(days=now.weekday())).date(), time.min, tzinfo=tz)
    end = start + timedelta(days=7)
    notes = (
        db.query(VoiceNote)
        .filter(
            VoiceNote.user_id == current_user.id,
            VoiceNote.created_at >= start,
            VoiceNote.created_at < end,
            VoiceNote.transcript.isnot(None),
        )
        .order_by(VoiceNote.created_at.asc())
        .all()
    )
    corpus = "\n".join((n.transcript or "").strip() for n in notes if (n.transcript or "").strip())
    top_terms = smart_ai_service.top_terms(corpus, top_n=12)
    candidate_labels = [t for t, _ in top_terms[:6]] or ["planlama", "odak", "is", "saglik", "egitim"]
    themed = smart_ai_service.classify_themes(corpus, candidate_labels)
    return {
        "intent": "weekly_themes",
        "note_count": len(notes),
        "top_terms": [{"term": t, "count": c} for t, c in top_terms],
        "ai_themes": [{"label": l, "score": s} for l, s in zip(themed.get("labels", []), themed.get("scores", []))],
        "ai_meta": {"model": themed.get("model"), "fallback": themed.get("fallback")},
    }


@router.post("/weekly-email-report")
def assistant_weekly_email_report(
    body: WeeklyEmailBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    daily = assistant_daily_summary(days=7, db=db, current_user=current_user)
    themes = assistant_weekly_themes(db=db, current_user=current_user)
    to_email = body.to_email or current_user.email
    subject = "Rawy Haftalik Rapor"
    lines = [
        "Haftalik rapor",
        f"Not sayisi: {daily['note_count']}",
        f"Ozet: {daily['summary_tr']}",
        f"Duygu: {daily['sentiment']['label']}",
        "Temalar: " + ", ".join(x["term"] for x in themes["top_terms"][:6]),
    ]
    mail = smart_ai_service.send_weekly_email(to_email=to_email, subject=subject, body="\n".join(lines))
    return {
        "intent": "weekly_email_report",
        "to_email": to_email,
        "mail": mail,
        "summary": daily,
        "themes": themes,
    }
