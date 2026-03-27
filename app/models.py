from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
# ARRAY type removed for SQLite compatibility - using JSON instead
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    plan = Column(String(20), nullable=False, default="starter")
    billing_interval = Column(String(16), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    timezone = Column(String(64), nullable=False, default="UTC")
    last_task_nudge_at = Column(DateTime(timezone=True), nullable=True)
    active_focus_block_id = Column(
        Integer, ForeignKey("focus_blocks.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, server_default=func.now())

    voice_notes = relationship("VoiceNote", back_populates="user")
    focus_blocks = relationship("FocusBlock", back_populates="user", foreign_keys="FocusBlock.user_id")
    active_focus_block = relationship("FocusBlock", foreign_keys=[active_focus_block_id])
    tasks = relationship("Task", back_populates="user")
    focus_sessions_hosted = relationship(
        "FocusSession", foreign_keys="FocusSession.host_user_id", back_populates="host_user"
    )
    focus_sessions_joined = relationship(
        "FocusSession", foreign_keys="FocusSession.partner_user_id", back_populates="partner_user"
    )
    calendar_events = relationship("CalendarEvent", back_populates="user")
    workspace_memberships = relationship("WorkspaceMember", back_populates="user", foreign_keys="WorkspaceMember.user_id")


class VoiceNote(Base):
    __tablename__ = "voice_notes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)

    original_filename = Column(String(255))
    storage_path = Column(String(500), nullable=False)
    file_size = Column(Integer)
    duration = Column(Float)
    mime_type = Column(String(50))

    transcript = Column(Text)
    transcript_confidence = Column(Float)
    language = Column(String(10))

    title = Column(String(255))
    tags = Column(JSON)  # List of strings stored as JSON
    is_processed = Column(Boolean, default=False)
    processing_error = Column(Text)

    # Çevrimdışı kayıt senkronu (istemci üretimi id)
    client_id = Column(String(64), nullable=True)
    client_recorded_at = Column(DateTime(timezone=True), nullable=True)
    requested_language = Column(String(16), nullable=True)
    quick_capture_exceeded = Column(Boolean, nullable=False, default=False)

    recording_type = Column(String(32), nullable=False, default="quick_note")
    meeting_summary = Column(Text, nullable=True)
    meeting_action_items = Column(JSON, nullable=True)
    related_note_ids = Column(JSON, nullable=True)  # List of integers stored as JSON
    mood_score = Column(Float, nullable=True)
    reflection_patterns = Column(Text, nullable=True)

    ai_category = Column(String(32), nullable=True)
    linked_task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    linked_focus_block_id = Column(Integer, ForeignKey("focus_blocks.id", ondelete="SET NULL"), nullable=True)
    pipeline_error = Column(Text, nullable=True)
    task_converted = Column(Boolean, nullable=False, default=False)
    review_at = Column(DateTime(timezone=True), nullable=True)
    review_status = Column(String(20), nullable=False, default="none")
    capsule_at = Column(DateTime(timezone=True), nullable=True)
    capsule_message = Column(Text, nullable=True)
    capsule_delivered_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    user = relationship("User", back_populates="voice_notes")
    linked_task = relationship("Task", foreign_keys=[linked_task_id])
    linked_focus_block = relationship("FocusBlock", foreign_keys=[linked_focus_block_id])
    calendar_events = relationship("CalendarEvent", back_populates="source_note")
    workspace = relationship("Workspace", back_populates="voice_notes")
    
    # Knowledge Graph ilişkileri
    outgoing_edges = relationship("NoteEdge", foreign_keys="NoteEdge.source_note_id", back_populates="source_note", cascade="all, delete-orphan")
    incoming_edges = relationship("NoteEdge", foreign_keys="NoteEdge.target_note_id", back_populates="target_note", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    done = Column(Boolean, default=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    depth = Column(String(16), nullable=False, default="shallow")
    snooze_until = Column(DateTime(timezone=True), nullable=True)
    source_voice_note_id = Column(Integer, ForeignKey("voice_notes.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="tasks")


class FocusBlock(Base):
    __tablename__ = "focus_blocks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    title = Column(String(500), nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    is_focus = Column(Boolean, default=True)
    source = Column(String(32), default="manual")
    source_voice_note_id = Column(Integer, ForeignKey("voice_notes.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="focus_blocks", foreign_keys=[user_id])


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id = Column(Integer, primary_key=True)
    host_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    partner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    mode = Column(String(20), nullable=False, default="solo")
    status = Column(String(20), nullable=False, default="active")
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    checkin_note = Column(Text, nullable=True)

    host_user = relationship("User", foreign_keys=[host_user_id], back_populates="focus_sessions_hosted")
    partner_user = relationship("User", foreign_keys=[partner_user_id], back_populates="focus_sessions_joined")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    source_note_id = Column(Integer, ForeignKey("voice_notes.id", ondelete="SET NULL"), nullable=True)
    is_focus_block = Column(Boolean, nullable=False, default=False)
    external_event_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="calendar_events")
    source_note = relationship("VoiceNote", back_populates="calendar_events")


class NoteEdge(Base):
    """Knowledge Graph: Notlar arası bağlantılar (Obsidian tarzı)"""
    __tablename__ = "note_edges"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    source_note_id = Column(Integer, ForeignKey("voice_notes.id", ondelete="CASCADE"), nullable=False)
    target_note_id = Column(Integer, ForeignKey("voice_notes.id", ondelete="CASCADE"), nullable=False)
    
    edge_type = Column(String(50), nullable=False, default="link")  # 'link', 'similar', 'reference', 'wiki'
    strength = Column(Float, nullable=False, default=1.0)  # 0-1 benzerlik skoru
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    source_note = relationship("VoiceNote", foreign_keys=[source_note_id], back_populates="outgoing_edges")
    target_note = relationship("VoiceNote", foreign_keys=[target_note_id], back_populates="incoming_edges")


class Workspace(Base):
    """Takım/Workspace modeli - B2B için kritik"""
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan = Column(String(20), nullable=False, default="starter")  # starter, pro, team, enterprise
    
    # Davet sistemi
    invite_token = Column(String(64), unique=True, nullable=True, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    voice_notes = relationship("VoiceNote", back_populates="workspace")


class WorkspaceMember(Base):
    """Workspace üyelikleri"""
    __tablename__ = "workspace_members"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Rol bazlı yetkilendirme
    role = Column(String(20), nullable=False, default="member")  # owner, admin, member, viewer
    
    invited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", foreign_keys=[user_id], back_populates="workspace_memberships")


class ApiKey(Base):
    """Public API erişim anahtarları"""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String(100), nullable=False)  # API key adı (örn: "Zapier Integration")
    key_hash = Column(String(255), nullable=False, unique=True, index=True)  # API key hash'i
    key_prefix = Column(String(10), nullable=False)  # Key'in ilk 8 karakteri (görüntüleme için)
    
    # Rate limiting
    rate_limit = Column(Integer, default=1000)  # Saatlik request limiti
    
    # Son kullanım
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    usage_count = Column(Integer, default=0)
    
    # Webhook URL (opsiyonel)
    webhook_url = Column(String(500), nullable=True)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")


class SamlConfig(Base):
    """SAML/SSO konfigürasyonu - Enterprise için"""
    __tablename__ = "saml_configs"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # IdP (Identity Provider) bilgileri
    idp_entity_id = Column(String(500), nullable=False)
    idp_sso_url = Column(String(500), nullable=False)  # Single Sign-On URL
    idp_slo_url = Column(String(500), nullable=True)   # Single Logout URL
    idp_x509_cert = Column(Text, nullable=False)       # IdP sertifikası
    
    # SP (Service Provider) bilgileri - biz
    sp_entity_id = Column(String(500), nullable=False)
    
    # Attribute mapping
    email_attribute = Column(String(100), default="email")
    name_attribute = Column(String(100), default="name")
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    workspace = relationship("Workspace")


class MeetingBot(Base):
    """AI Meeting Assistant - Toplantı botu konfigürasyonu"""
    __tablename__ = "meeting_bots"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)
    
    # Toplantı bilgileri
    title = Column(String(255), nullable=False)
    meeting_url = Column(String(500), nullable=True)  # Zoom, Google Meet, Teams URL
    calendar_event_id = Column(String(255), nullable=True)
    
    # Bot durumu
    status = Column(String(20), default="scheduled")  # scheduled, joining, recording, completed, failed
    
    # Zamanlama
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    
    # Sonuçlar
    recording_path = Column(String(500), nullable=True)
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    action_items = Column(JSON, nullable=True)  # [{"task": "...", "assignee": "...", "due": "..."}]
    
    # Katılımcılar
    participants = Column(JSON, nullable=True)  # ["email1", "email2"]
    
    # Hata bilgisi
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User")
    workspace = relationship("Workspace")


class Reminder(Base):
    """Hatırlatıcı / Alarm sistemi"""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Hatırlatıcı içeriği
    title = Column(String(255), nullable=False)  # "Su iç", "Toplantı", "İlaç"
    note = Column(Text, nullable=True)  # Detaylı not
    
    # Zamanlama
    remind_at = Column(DateTime(timezone=True), nullable=False, index=True)  # Ne zaman hatırlat
    timezone = Column(String(64), nullable=False, default="UTC")
    
    # Tekrar (recurrence)
    recurrence = Column(String(20), nullable=True)  # null, "daily", "weekly", "monthly"
    recurrence_count = Column(Integer, nullable=True)  # Kaç kez tekrar edecek (null = sonsuz)
    
    # Durumlar
    is_triggered = Column(Boolean, default=False)  # Alarm çaldı mı?
    is_dismissed = Column(Boolean, default=False)  # Kullanıcı kapat/kapat dedi mi?
    is_snoozed = Column(Boolean, default=False)  # Erteleme aktif mi?
    snooze_until = Column(DateTime(timezone=True), nullable=True)  # Erteleme ne zamana
    
    # Bildirim tercihleri
    notify_methods = Column(JSON, default=list)  # ["push", "email", "voice"]
    
    # İlişkiler
    source_voice_note_id = Column(Integer, ForeignKey("voice_notes.id", ondelete="SET NULL"), nullable=True)
    linked_task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    
    # İstatistik
    trigger_count = Column(Integer, default=0)  # Kaç kez hatırlatıldı
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User")
    source_voice_note = relationship("VoiceNote")
    linked_task = relationship("Task")
