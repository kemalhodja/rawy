"""
AI Meeting Assistant servisi
Toplantı botu yönetimi, kayıt, transkript ve özet
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import MeetingBot, Task, VoiceNote


def create_meeting_bot(
    db: Session,
    user_id: int,
    title: str,
    scheduled_at: datetime,
    meeting_url: str = None,
    workspace_id: int = None,
    calendar_event_id: str = None,
    participants: list = None
) -> MeetingBot:
    """Yeni toplantı botu planla"""
    
    bot = MeetingBot(
        user_id=user_id,
        workspace_id=workspace_id,
        title=title,
        meeting_url=meeting_url,
        calendar_event_id=calendar_event_id,
        scheduled_at=scheduled_at,
        participants=participants or [],
        status="scheduled"
    )
    
    db.add(bot)
    db.commit()
    db.refresh(bot)
    
    return bot


def get_meeting_bot(db: Session, bot_id: int, user_id: int) -> Optional[MeetingBot]:
    """Toplantı botu detayını getir"""
    return (
        db.query(MeetingBot)
        .filter(MeetingBot.id == bot_id, MeetingBot.user_id == user_id)
        .first()
    )


def list_meeting_bots(
    db: Session,
    user_id: int,
    status: str = None,
    limit: int = 50
) -> list[MeetingBot]:
    """Toplantı botlarını listele"""
    query = db.query(MeetingBot).filter(MeetingBot.user_id == user_id)
    
    if status:
        query = query.filter(MeetingBot.status == status)
    
    return query.order_by(MeetingBot.scheduled_at.desc()).limit(limit).all()


def update_bot_status(
    db: Session,
    bot_id: int,
    user_id: int,
    status: str,
    error_message: str = None
) -> Optional[MeetingBot]:
    """Bot durumunu güncelle"""
    bot = get_meeting_bot(db, bot_id, user_id)
    if not bot:
        return None
    
    bot.status = status
    
    if status == "joining":
        bot.started_at = datetime.now(timezone.utc)
    elif status in ["completed", "failed"]:
        bot.ended_at = datetime.now(timezone.utc)
    
    if error_message:
        bot.error_message = error_message
    
    db.commit()
    db.refresh(bot)
    return bot


def extract_action_items(transcript: str) -> list[dict]:
    """
    Transkriptten action item'ları çıkar (basit kural tabanlı)
    Gelecekte: GPT-4 ile daha gelişmiş
    """
    action_items = []
    
    # Türkçe ve İngilizce action pattern'leri
    patterns = [
        r"(?i)(\w+)\s+(?:yapacak|yapmalı|yapacak|will do|to do)\s*:?\s*(.+?)(?:\.|$)",
        r"(?i)action\s*:?\s*(.+?)(?:\.|$)",
        r"(?i)(?:todo|todo:|yapılacak)\s*:?\s*(.+?)(?:\.|$)",
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, transcript, re.MULTILINE)
        for match in matches:
            assignee = match.group(1) if len(match.groups()) > 1 else ""
            task = match.group(2) if len(match.groups()) > 1 else match.group(1)
            
            action_items.append({
                "task": task.strip(),
                "assignee": assignee.strip() if assignee else None,
                "due": None,  # Tarih çıkarımı eklenebilir
                "completed": False
            })
    
    # Tekrarları kaldır
    seen = set()
    unique_items = []
    for item in action_items:
        key = item["task"].lower()
        if key not in seen:
            seen.add(key)
            unique_items.append(item)
    
    return unique_items[:10]  # Max 10 action item


def generate_meeting_summary(transcript: str) -> str:
    """
    Toplantı özeti oluştur (basit implementasyon)
    Gelecekte: GPT-4 ile daha gelişmiş
    """
    if not transcript:
        return "Transkript bulunamadi."
    
    # Cümleleri böl
    sentences = re.split(r'[.!?]+', transcript)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    if not sentences:
        return "Yeterli icerik bulunamadi."
    
    # Basit özet: İlk ve son cümleler + uzun cümleler
    summary_parts = []
    
    # Başlangıç
    if sentences:
        summary_parts.append(f"Toplanti basladi: {sentences[0]}")
    
    # Ana konular (uzun cümleler)
    key_sentences = [s for s in sentences[1:-1] if len(s) > 50][:3]
    if key_sentences:
        summary_parts.append("Ana konular:")
        for i, s in enumerate(key_sentences, 1):
            summary_parts.append(f"  {i}. {s[:100]}...")
    
    # Sonuç
    if len(sentences) > 1:
        summary_parts.append(f"Sonuc: {sentences[-1]}")
    
    return "\n".join(summary_parts)


def process_meeting_recording(
    db: Session,
    bot_id: int,
    user_id: int,
    transcript: str,
    recording_path: str = None
) -> MeetingBot:
    """
    Toplantı kaydını işle: transkript, özet, action items
    """
    bot = get_meeting_bot(db, bot_id, user_id)
    if not bot:
        raise ValueError("Bot bulunamadi")
    
    # Transkript kaydet
    bot.transcript = transcript
    bot.recording_path = recording_path
    
    # Özet oluştur
    bot.summary = generate_meeting_summary(transcript)
    
    # Action items çıkar
    bot.action_items = extract_action_items(transcript)
    
    # Status güncelle
    bot.status = "completed"
    bot.ended_at = datetime.now(timezone.utc)
    
    # VoiceNote olarak da kaydet (opsiyonel)
    voice_note = VoiceNote(
        user_id=user_id,
        workspace_id=bot.workspace_id,
        title=f"Toplanti: {bot.title}",
        transcript=transcript,
        storage_path=recording_path or "",
        meeting_summary=bot.summary,
        meeting_action_items=bot.action_items,
        is_processed=True
    )
    db.add(voice_note)
    
    # Action item'ları görev olarak ekle
    for item in (bot.action_items or []):
        task = Task(
            user_id=user_id,
            title=item["task"],
            depth="shallow",
            source_voice_note_id=voice_note.id
        )
        db.add(task)
    
    db.commit()
    db.refresh(bot)
    
    return bot


def delete_meeting_bot(db: Session, bot_id: int, user_id: int) -> bool:
    """Toplantı botunu sil"""
    bot = get_meeting_bot(db, bot_id, user_id)
    if bot:
        db.delete(bot)
        db.commit()
        return True
    return False


def get_upcoming_meetings(db: Session, user_id: int, minutes: int = 30) -> list[MeetingBot]:
    """Yaklaşan toplantıları getir"""
    from datetime import timedelta
    
    now = datetime.now(timezone.utc)
    soon = now + timedelta(minutes=minutes)
    
    return (
        db.query(MeetingBot)
        .filter(
            MeetingBot.user_id == user_id,
            MeetingBot.scheduled_at >= now,
            MeetingBot.scheduled_at <= soon,
            MeetingBot.status == "scheduled"
        )
        .order_by(MeetingBot.scheduled_at)
        .all()
    )
