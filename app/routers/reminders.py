"""
Hatırlatıcı / Alarm Router
- CRUD işlemleri
- Sesle hatırlatıcı oluşturma
- Snooze (erteleme) ve dismiss (kapatma)
- Tetiklenmiş hatırlatıcıları listeleme
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Reminder, User, Task
from app.schemas import (
    ReminderCreate, 
    ReminderOut, 
    ReminderUpdate, 
    ReminderSnooze,
    ReminderDismiss,
    ReminderListOut,
    VoiceReminderCommand
)

router = APIRouter(prefix="/reminders", tags=["reminders"])


def _reminder_out(r: Reminder) -> ReminderOut:
    return ReminderOut(
        id=r.id,
        user_id=r.user_id,
        title=r.title,
        note=r.note,
        remind_at=r.remind_at,
        timezone=r.timezone,
        recurrence=r.recurrence,
        recurrence_count=r.recurrence_count,
        is_triggered=r.is_triggered,
        is_dismissed=r.is_dismissed,
        is_snoozed=r.is_snoozed,
        snooze_until=r.snooze_until,
        notify_methods=r.notify_methods or ["push"],
        linked_task_id=r.linked_task_id,
        trigger_count=r.trigger_count,
        last_triggered_at=r.last_triggered_at,
        created_at=r.created_at,
    )


def _get_user_now(user: User) -> datetime:
    """Kullanıcının zaman dilimine göre şu anki zaman"""
    # Basit implementasyon - UTC kullan
    return datetime.now(timezone.utc)


# ========== CRUD ENDPOINTLERİ ==========

@router.post("/", response_model=ReminderOut)
def create_reminder(
    body: ReminderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Yeni hatırlatıcı oluştur"""
    reminder = Reminder(
        user_id=current_user.id,
        title=body.title,
        note=body.note,
        remind_at=body.remind_at,
        timezone=body.timezone,
        recurrence=body.recurrence,
        recurrence_count=body.recurrence_count,
        notify_methods=body.notify_methods,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return _reminder_out(reminder)


@router.get("/", response_model=ReminderListOut)
def list_reminders(
    include_dismissed: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tüm hatırlatıcıları listele (kategorize edilmiş)"""
    now = _get_user_now(current_user)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    query = db.query(Reminder).filter(Reminder.user_id == current_user.id)
    
    if not include_dismissed:
        query = query.filter(Reminder.is_dismissed == False)
    
    reminders = query.order_by(Reminder.remind_at.asc()).all()
    
    upcoming = []
    overdue = []
    today = []
    
    for r in reminders:
        # Snooze kontrolü
        if r.is_snoozed and r.snooze_until and r.snooze_until > now:
            continue  # Erteleme devam ediyor
        
        ro = _reminder_out(r)
        
        if r.remind_at < now and not r.is_triggered:
            overdue.append(ro)
        elif today_start <= r.remind_at < today_end:
            today.append(ro)
        elif r.remind_at >= now:
            upcoming.append(ro)
    
    return ReminderListOut(upcoming=upcoming, overdue=overdue, today=today)


@router.get("/active", response_model=list[ReminderOut])
def get_active_reminders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Şu an tetiklenmesi gereken hatırlatıcılar (ALARM!)"""
    now = _get_user_now(current_user)
    
    reminders = db.query(Reminder).filter(
        Reminder.user_id == current_user.id,
        Reminder.is_dismissed == False,
        or_(
            and_(
                Reminder.remind_at <= now,
                Reminder.is_triggered == False,
                Reminder.is_snoozed == False,
            ),
            and_(
                Reminder.is_snoozed == True,
                Reminder.snooze_until <= now,
            )
        )
    ).all()
    
    return [_reminder_out(r) for r in reminders]


@router.post("/{reminder_id}/trigger", response_model=ReminderOut)
def trigger_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hatırlatıcıyı tetikle (alarm çaldı olarak işaretle)"""
    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id,
        Reminder.user_id == current_user.id
    ).first()
    
    if not reminder:
        raise HTTPException(404, "Hatırlatıcı bulunamadı")
    
    reminder.is_triggered = True
    reminder.trigger_count += 1
    reminder.last_triggered_at = datetime.now(timezone.utc)
    reminder.is_snoozed = False
    reminder.snooze_until = None
    
    db.commit()
    db.refresh(reminder)
    return _reminder_out(reminder)


@router.post("/{reminder_id}/snooze", response_model=ReminderOut)
def snooze_reminder(
    reminder_id: int,
    body: ReminderSnooze,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hatırlatıcıyı ertele (5 dk - 24 saat)"""
    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id,
        Reminder.user_id == current_user.id
    ).first()
    
    if not reminder:
        raise HTTPException(404, "Hatırlatıcı bulunamadı")
    
    now = datetime.now(timezone.utc)
    reminder.is_snoozed = True
    reminder.snooze_until = now + timedelta(minutes=body.minutes)
    
    db.commit()
    db.refresh(reminder)
    return _reminder_out(reminder)


@router.post("/{reminder_id}/dismiss", response_model=ReminderOut)
def dismiss_reminder(
    reminder_id: int,
    body: ReminderDismiss,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hatırlatıcıyı kapat/kapat"""
    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id,
        Reminder.user_id == current_user.id
    ).first()
    
    if not reminder:
        raise HTTPException(404, "Hatırlatıcı bulunamadı")
    
    reminder.is_dismissed = True
    reminder.is_snoozed = False
    
    # Tekrarlayan hatırlatıcıyı durdur (eğer istenirse)
    if body.dismiss_permanently:
        reminder.recurrence = None
        reminder.recurrence_count = None
    
    db.commit()
    db.refresh(reminder)
    return _reminder_out(reminder)


@router.patch("/{reminder_id}", response_model=ReminderOut)
def update_reminder(
    reminder_id: int,
    body: ReminderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hatırlatıcıyı güncelle"""
    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id,
        Reminder.user_id == current_user.id
    ).first()
    
    if not reminder:
        raise HTTPException(404, "Hatırlatıcı bulunamadı")
    
    if body.title is not None:
        reminder.title = body.title
    if body.note is not None:
        reminder.note = body.note
    if body.remind_at is not None:
        reminder.remind_at = body.remind_at
        reminder.is_triggered = False  # Yeni zamanda tekrar tetiklenecek
    if body.recurrence is not None:
        reminder.recurrence = body.recurrence
    if body.recurrence_count is not None:
        reminder.recurrence_count = body.recurrence_count
    
    db.commit()
    db.refresh(reminder)
    return _reminder_out(reminder)


@router.delete("/{reminder_id}", status_code=204)
def delete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hatırlatıcıyı kalıcı sil"""
    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id,
        Reminder.user_id == current_user.id
    ).first()
    
    if not reminder:
        raise HTTPException(404, "Hatırlatıcı bulunamadı")
    
    db.delete(reminder)
    db.commit()
    return None


# ========== SESLE HATIRLATICI ==========

@router.post("/voice", response_model=ReminderOut)
def create_reminder_from_voice(
    body: VoiceReminderCommand,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ses komutundan hatırlatıcı oluştur.
    Örnekler:
    - "Yarın saat 9'da toplantıyı hatırlat"
    - "3 saat sonra su içmeyi hatırlat"
    - "Her gün saat 8'de ilacımı hatırlat"
    """
    from app.services.voice_deadline import parse_deadline_from_voice
    
    text_lower = body.text.lower()
    now = datetime.now(timezone.utc)
    
    # Başlık çıkarımı
    title = body.text
    
    # Tekrar kontrolü
    recurrence = None
    recurrence_keywords = {
        "her gün": "daily", "hergun": "daily", "daily": "daily",
        "her hafta": "weekly", "herhafta": "weekly", "weekly": "weekly",
        "her ay": "monthly", "heray": "monthly", "monthly": "monthly",
    }
    
    for keyword, rec_type in recurrence_keywords.items():
        if keyword in text_lower:
            recurrence = rec_type
            # Tekrar kelimesini başlıktan çıkar
            title = title.replace(keyword, "").strip()
            break
    
    # Zaman ayrıştırma
    parsed_deadline = parse_deadline_from_voice(body.text, body.timezone)
    remind_at = parsed_deadline if parsed_deadline else (now + timedelta(hours=1))
    
    # Başlık temizleme
    clean_words = ["hatırlat", "hatırlatıcı", "alarm", "kur", "ekle", "remind", "reminder"]
    for word in clean_words:
        title = title.replace(word, "").replace(word.capitalize(), "")
    
    # Fazla boşlukları temizle
    title = " ".join(title.split()).strip()
    if not title:
        title = "Hatırlatıcı"
    
    reminder = Reminder(
        user_id=current_user.id,
        title=title,
        remind_at=remind_at,
        timezone=body.timezone,
        recurrence=recurrence,
        notify_methods=["push", "voice"],
    )
    
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return _reminder_out(reminder)
