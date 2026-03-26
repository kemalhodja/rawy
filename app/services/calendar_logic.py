"""Anti-busywork: önceki blok ile çakışmayı buffer ile gider."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import FocusBlock


def apply_buffer_before_start(
    db: Session,
    user_id: int,
    proposed_start: datetime,
    proposed_end: datetime,
    buffer_minutes: int | None = None,
) -> tuple[datetime, datetime, bool]:
    """
    Aynı kullanıcı için proposed_start'tan önce biten son blok varsa
    ve ara < buffer ise başlangıcı kaydırır.
    Dönüş: (start, end, adjusted)
    """
    buf = buffer_minutes if buffer_minutes is not None else settings.CALENDAR_BUFFER_MINUTES
    delta = timedelta(minutes=buf)

    prev = (
        db.query(FocusBlock)
        .filter(
            FocusBlock.user_id == user_id,
            FocusBlock.end_at <= proposed_start,
        )
        .order_by(FocusBlock.end_at.desc())
        .first()
    )

    adjusted = False
    start = proposed_start
    end = proposed_end

    if prev and prev.end_at + delta > start:
        start = prev.end_at + delta
        adjusted = True
        duration = proposed_end - proposed_start
        end = start + duration
        if end <= start:
            end = start + timedelta(hours=2)

    return start, end, adjusted


def focus_duration_hours(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600.0


def validate_focus_duration(hours: float) -> None:
    lo = settings.FOCUS_BLOCK_MIN_HOURS
    hi = settings.FOCUS_BLOCK_MAX_HOURS
    if hours < lo or hours > hi:
        raise ValueError(
            f"Odak bloğu {lo:g}-{hi:g} saat arasında olmalı (şu an {hours:.2f} saat)"
        )
