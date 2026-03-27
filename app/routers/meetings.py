"""
AI Meeting Assistant API
Toplantı botu yönetimi
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import MeetingBot, User
from app.services import meeting_bot as meeting_service

router = APIRouter(prefix="/meetings", tags=["meeting-assistant"])


class MeetingCreate(BaseModel):
    title: str
    scheduled_at: datetime
    meeting_url: Optional[str] = None
    workspace_id: Optional[int] = None
    calendar_event_id: Optional[str] = None
    participants: Optional[list] = None


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    meeting_url: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class TranscriptSubmit(BaseModel):
    transcript: str
    recording_path: Optional[str] = None


@router.get("")
def list_meetings(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toplantıları listele"""
    meetings = meeting_service.list_meeting_bots(
        db, current_user.id, status=status, limit=limit
    )
    
    return [
        {
            "id": m.id,
            "title": m.title,
            "status": m.status,
            "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
            "meeting_url": m.meeting_url,
            "has_recording": bool(m.recording_path),
            "has_summary": bool(m.summary),
            "action_count": len(m.action_items) if m.action_items else 0
        }
        for m in meetings
    ]


@router.post("")
def create_meeting(
    data: MeetingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Yeni toplantı planla"""
    meeting = meeting_service.create_meeting_bot(
        db,
        user_id=current_user.id,
        title=data.title,
        scheduled_at=data.scheduled_at,
        meeting_url=data.meeting_url,
        workspace_id=data.workspace_id,
        calendar_event_id=data.calendar_event_id,
        participants=data.participants
    )
    
    return {
        "id": meeting.id,
        "title": meeting.title,
        "status": meeting.status,
        "message": "Toplanti planlandi. Bot otomatik katilacak."
    }


@router.get("/upcoming")
def get_upcoming(
    minutes: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Yaklaşan toplantıları getir"""
    meetings = meeting_service.get_upcoming_meetings(db, current_user.id, minutes)
    
    return [
        {
            "id": m.id,
            "title": m.title,
            "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
            "meeting_url": m.meeting_url,
            "minutes_until": int((m.scheduled_at - datetime.now(m.scheduled_at.tzinfo)).total_seconds() / 60)
        }
        for m in meetings
    ]


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toplantı detayını getir"""
    meeting = meeting_service.get_meeting_bot(db, meeting_id, current_user.id)
    if not meeting:
        raise HTTPException(404, "Toplanti bulunamadi")
    
    return {
        "id": meeting.id,
        "title": meeting.title,
        "status": meeting.status,
        "meeting_url": meeting.meeting_url,
        "scheduled_at": meeting.scheduled_at.isoformat() if meeting.scheduled_at else None,
        "started_at": meeting.started_at.isoformat() if meeting.started_at else None,
        "ended_at": meeting.ended_at.isoformat() if meeting.ended_at else None,
        "participants": meeting.participants,
        "transcript": meeting.transcript,
        "summary": meeting.summary,
        "action_items": meeting.action_items,
        "error_message": meeting.error_message
    }


@router.patch("/{meeting_id}")
def update_meeting(
    meeting_id: int,
    data: MeetingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toplantı güncelle"""
    meeting = meeting_service.get_meeting_bot(db, meeting_id, current_user.id)
    if not meeting:
        raise HTTPException(404, "Toplanti bulunamadi")
    
    if data.title:
        meeting.title = data.title
    if data.meeting_url:
        meeting.meeting_url = data.meeting_url
    if data.scheduled_at:
        meeting.scheduled_at = data.scheduled_at
    
    db.commit()
    db.refresh(meeting)
    
    return {"message": "Toplanti guncellendi"}


@router.post("/{meeting_id}/join")
def join_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toplantıya bot olarak katıl (manuel başlatma)"""
    meeting = meeting_service.update_bot_status(
        db, meeting_id, current_user.id, "joining"
    )
    
    if not meeting:
        raise HTTPException(404, "Toplanti bulunamadi")
    
    # Gerçek implementasyonda: Bot meeting URL'sine katılır
    # Şimdilik simülasyon
    
    return {
        "message": "Bot toplantiya katiliyor",
        "meeting_url": meeting.meeting_url,
        "status": meeting.status
    }


@router.post("/{meeting_id}/transcript")
def submit_transcript(
    meeting_id: int,
    data: TranscriptSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toplantı transkripti gönder ve işle"""
    try:
        meeting = meeting_service.process_meeting_recording(
            db,
            bot_id=meeting_id,
            user_id=current_user.id,
            transcript=data.transcript,
            recording_path=data.recording_path
        )
        
        return {
            "message": "Toplanti islenerek kaydedildi",
            "summary": meeting.summary,
            "action_items": meeting.action_items,
            "voice_note_id": meeting.id  # Yeni oluşturulan not
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{meeting_id}/extract-actions")
def extract_actions(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mevcut transkriptten action item'ları tekrar çıkar"""
    meeting = meeting_service.get_meeting_bot(db, meeting_id, current_user.id)
    if not meeting:
        raise HTTPException(404, "Toplanti bulunamadi")
    
    if not meeting.transcript:
        raise HTTPException(400, "Transkript bulunmuyor")
    
    actions = meeting_service.extract_action_items(meeting.transcript)
    
    # Güncelle
    meeting.action_items = actions
    db.commit()
    
    return {
        "action_items": actions,
        "count": len(actions)
    }


@router.delete("/{meeting_id}")
def delete_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toplantıyı sil"""
    success = meeting_service.delete_meeting_bot(db, meeting_id, current_user.id)
    if not success:
        raise HTTPException(404, "Toplanti bulunamadi")
    
    return {"message": "Toplanti silindi"}
