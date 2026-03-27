"""
Hatırlatıcı Scheduler Servisi
- Periyodik olarak tetiklenmesi gereken hatırlatıcıları kontrol eder
- WebSocket/SSE üzerinden bildirim gönderir (opsiyonel)
- Tekrarlayan hatırlatıcıları yeniden zamanlar

Kullanım:
    from app.services.reminder_scheduler import ReminderScheduler
    scheduler = ReminderScheduler(db_session)
    scheduler.check_and_trigger()
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable, List

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import Reminder, User


class ReminderAlarm:
    """Tek bir hatırlatıcı alarmı"""
    
    def __init__(self, reminder: Reminder):
        self.reminder_id = reminder.id
        self.user_id = reminder.user_id
        self.title = reminder.title
        self.note = reminder.note
        self.remind_at = reminder.remind_at
        self.recurrence = reminder.recurrence
        self.recurrence_count = reminder.recurrence_count
        self.trigger_count = reminder.trigger_count
    
    def to_dict(self):
        return {
            "id": self.reminder_id,
            "user_id": self.user_id,
            "title": self.title,
            "note": self.note,
            "remind_at": self.remind_at.isoformat() if self.remind_at else None,
            "recurrence": self.recurrence,
        }


class ReminderScheduler:
    """Hatırlatıcı scheduler ve alarm servisi"""
    
    def __init__(self, db: Session):
        self.db = db
        self._callbacks: List[Callable[[ReminderAlarm], None]] = []
    
    def on_alarm(self, callback: Callable[[ReminderAlarm], None]):
        """Alarm tetiklendiğinde çağrılacak callback'i kaydet"""
        self._callbacks.append(callback)
    
    def get_due_reminders(self, user_id: int = None) -> List[ReminderAlarm]:
        """
        Tetiklenmesi gereken hatırlatıcıları getir
        
        Koşullar:
        - remind_at <= şimdi
        - is_dismissed = False
        - is_triggered = False VEYA snooze süresi doldu
        """
        now = datetime.now(timezone.utc)
        
        query = self.db.query(Reminder).filter(
            Reminder.is_dismissed == False,
            or_(
                # İlk kez tetiklenecek
                and_(
                    Reminder.remind_at <= now,
                    Reminder.is_triggered == False,
                    Reminder.is_snoozed == False,
                ),
                # Snooze'dan çıkacak
                and_(
                    Reminder.is_snoozed == True,
                    Reminder.snooze_until <= now,
                )
            )
        )
        
        if user_id:
            query = query.filter(Reminder.user_id == user_id)
        
        reminders = query.all()
        return [ReminderAlarm(r) for r in reminders]
    
    def trigger_reminder(self, reminder_id: int) -> ReminderAlarm | None:
        """Hatırlatıcıyı tetikle ve alarm döndür"""
        reminder = self.db.query(Reminder).filter(
            Reminder.id == reminder_id
        ).first()
        
        if not reminder:
            return None
        
        # Tetikle
        reminder.is_triggered = True
        reminder.trigger_count += 1
        reminder.last_triggered_at = datetime.now(timezone.utc)
        reminder.is_snoozed = False
        reminder.snooze_until = None
        
        # Tekrarlayan mı?
        if reminder.recurrence and reminder.recurrence_count != 0:
            self._schedule_next_occurrence(reminder)
        
        self.db.commit()
        
        alarm = ReminderAlarm(reminder)
        
        # Callback'leri çağır
        for callback in self._callbacks:
            try:
                callback(alarm)
            except Exception as e:
                print(f"Alarm callback hatası: {e}")
        
        return alarm
    
    def _schedule_next_occurrence(self, reminder: Reminder):
        """Tekrarlayan hatırlatıcı için sonraki zamanı hesapla"""
        if reminder.recurrence == "daily":
            delta = timedelta(days=1)
        elif reminder.recurrence == "weekly":
            delta = timedelta(weeks=1)
        elif reminder.recurrence == "monthly":
            # Basit: 30 gün
            delta = timedelta(days=30)
        else:
            return
        
        # Sonraki zaman
        next_time = reminder.remind_at + delta
        
        # Yeni hatırlatıcı oluştur (veya mevcudu güncelle)
        # Strateji: Yenisini oluştur (geçmiş kayıt kalsın)
        new_reminder = Reminder(
            user_id=reminder.user_id,
            title=reminder.title,
            note=reminder.note,
            remind_at=next_time,
            timezone=reminder.timezone,
            recurrence=reminder.recurrence,
            recurrence_count=reminder.recurrence_count - 1 if reminder.recurrence_count else None,
            notify_methods=reminder.notify_methods,
        )
        
        self.db.add(new_reminder)
        
        # Eski hatırlatıcıyı kapat
        reminder.recurrence = None
        reminder.recurrence_count = None
    
    def check_and_trigger(self, user_id: int = None) -> List[ReminderAlarm]:
        """
        Tüm tetiklenmesi gereken hatırlatıcıları kontrol et ve tetikle
        
        Returns:
            List[ReminderAlarm]: Tetiklenen alarmların listesi
        """
        due_reminders = self.get_due_reminders(user_id)
        triggered = []
        
        for alarm in due_reminders:
            triggered_alarm = self.trigger_reminder(alarm.reminder_id)
            if triggered_alarm:
                triggered.append(triggered_alarm)
        
        return triggered
    
    def snooze_reminder(self, reminder_id: int, minutes: int) -> bool:
        """Hatırlatıcıyı ertele"""
        reminder = self.db.query(Reminder).filter(
            Reminder.id == reminder_id
        ).first()
        
        if not reminder:
            return False
        
        now = datetime.now(timezone.utc)
        reminder.is_snoozed = True
        reminder.snooze_until = now + timedelta(minutes=minutes)
        reminder.is_triggered = False  # Tekrar tetiklenebilir
        
        self.db.commit()
        return True
    
    def dismiss_reminder(self, reminder_id: int, permanently: bool = False) -> bool:
        """Hatırlatıcıyı kapat"""
        reminder = self.db.query(Reminder).filter(
            Reminder.id == reminder_id
        ).first()
        
        if not reminder:
            return False
        
        reminder.is_dismissed = True
        reminder.is_snoozed = False
        
        if permanently:
            reminder.recurrence = None
            reminder.recurrence_count = None
        
        self.db.commit()
        return True


# ===== ARKA PLAN GÖREVİ (Background Task) =====

class ReminderBackgroundService:
    """
    Arka planda çalışan hatırlatıcı servisi
    
    Örnek kullanım (FastAPI lifespan):
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            service = ReminderBackgroundService(db_factory)
            asyncio.create_task(service.start())
            yield
            service.stop()
    """
    
    def __init__(self, db_factory: Callable[[], Session], check_interval: int = 30):
        self.db_factory = db_factory
        self.check_interval = check_interval  # saniye
        self._running = False
        self._task = None
    
    async def start(self):
        """Arka plan görevini başlat"""
        self._running = True
        while self._running:
            try:
                db = self.db_factory()
                scheduler = ReminderScheduler(db)
                triggered = scheduler.check_and_trigger()
                
                if triggered:
                    print(f"[ALARM] {len(triggered)} hatırlatıcı tetiklendi!")
                    for alarm in triggered:
                        print(f"  - {alarm.title} (User: {alarm.user_id})")
                
                db.close()
            except Exception as e:
                print(f"[ALARM ERROR] {e}")
            
            await asyncio.sleep(self.check_interval)
    
    def stop(self):
        """Servisi durdur"""
        self._running = False


# ===== SESLİ BİLDİRİM =====

class VoiceNotifier:
    """Sesli hatırlatma bildirimi (TTS)"""
    
    @staticmethod
    def format_alarm_message(alarm: ReminderAlarm) -> str:
        """Alarm mesajını formatla"""
        messages = [
            f"Hatırlatma: {alarm.title}",
        ]
        
        if alarm.note:
            messages.append(f"Not: {alarm.note}")
        
        if alarm.recurrence:
            messages.append("Bu tekrarlayan bir hatırlatıcı.")
        
        return " ".join(messages)
    
    @staticmethod
    def format_snooze_confirmation(minutes: int) -> str:
        """Erteleme onay mesajı"""
        return f"Hatırlatıcı {minutes} dakika sonra tekrar gösterilecek."
    
    @staticmethod
    def format_list_reminders(reminders: List[ReminderAlarm]) -> str:
        """Hatırlatıcı listesini sesli formatla"""
        if not reminders:
            return "Aktif hatırlatıcınız yok."
        
        messages = [f"{len(reminders)} hatırlatıcınız var:"]
        
        for i, r in enumerate(reminders[:5], 1):  # Max 5
            messages.append(f"{i}. {r.title}")
        
        if len(reminders) > 5:
            messages.append(f"Ve {len(reminders) - 5} hatırlatıcı daha...")
        
        return " ".join(messages)
