from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255))
    is_active = Column(Boolean, default=True)
    plan = Column(String(20), nullable=False, default="starter")
    billing_interval = Column(String(16), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    timezone = Column(String(64), nullable=False, default="UTC")
    last_task_nudge_at = Column(DateTime(timezone=True), nullable=True)
    active_focus_block_id = Column(
        Integer, ForeignKey("focus_blocks.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, server_default=func.now())

    voice_notes = relationship("VoiceNote", back_populates="user")
    focus_blocks = relationship("FocusBlock", back_populates="user")
    active_focus_block = relationship("FocusBlock", foreign_keys=[active_focus_block_id])
    tasks = relationship("Task", back_populates="user")
    focus_sessions_hosted = relationship(
        "FocusSession", foreign_keys="FocusSession.host_user_id", back_populates="host_user"
    )
    focus_sessions_joined = relationship(
        "FocusSession", foreign_keys="FocusSession.partner_user_id", back_populates="partner_user"
    )


class VoiceNote(Base):
    __tablename__ = "voice_notes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    original_filename = Column(String(255))
    storage_path = Column(String(500), nullable=False)
    file_size = Column(Integer)
    duration = Column(Float)
    mime_type = Column(String(50))

    transcript = Column(Text)
    transcript_confidence = Column(Float)
    language = Column(String(10))

    title = Column(String(255))
    tags = Column(ARRAY(String))
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
    related_note_ids = Column(ARRAY(Integer), nullable=True)
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

    user = relationship("User", back_populates="focus_blocks")


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
