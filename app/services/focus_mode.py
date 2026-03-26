"""
Aktif odak: şu anki blok, Freedom tarzı bildirim susturma (istemci politikası), bitiş yansıtması.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.models import FocusBlock, User


def now_in_tz(user: User) -> datetime:
    tz = ZoneInfo(user.timezone or "UTC")
    return datetime.now(tz)


def get_current_block(db: Session, user: User) -> FocusBlock | None:
    """Ajanda: yalnızca 'şu anki' odak bloğu (now ∈ [start, end))."""
    now = now_in_tz(user)
    return (
        db.query(FocusBlock)
        .filter(
            FocusBlock.user_id == user.id,
            FocusBlock.start_at <= now,
            FocusBlock.end_at > now,
        )
        .order_by(FocusBlock.start_at.desc())
        .first()
    )


def user_in_declared_focus(db: Session, user: User) -> bool:
    """Kullanıcı aktif odak oturumunu başlatmış mı (çıkışa kadar)?"""
    bid = getattr(user, "active_focus_block_id", None)
    if not bid:
        return False
    blk = db.query(FocusBlock).filter(FocusBlock.id == bid).first()
    return blk is not None and blk.user_id == user.id


def enter_focus_session(db: Session, user: User, block_id: int) -> FocusBlock:
    blk = (
        db.query(FocusBlock)
        .filter(FocusBlock.id == block_id, FocusBlock.user_id == user.id)
        .first()
    )
    if not blk:
        raise ValueError("Blok bulunamadı")
    user.active_focus_block_id = blk.id
    db.commit()
    db.refresh(user)
    return blk


def exit_focus_session(db: Session, user: User) -> None:
    user.active_focus_block_id = None
    db.commit()


def focus_session_phase(db: Session, user: User) -> str:
    """
    during: ilan edilmiş odak + blok henüz bitmemiş
    after: ilan edilmiş odak + şimdi blok bitişinden sonra (yansıtma zamanı)
    none: odak oturumu yok
    """
    bid = getattr(user, "active_focus_block_id", None)
    if not bid:
        return "none"
    blk = db.query(FocusBlock).filter(FocusBlock.id == bid).first()
    if not blk:
        return "none"
    now = now_in_tz(user)
    if now < blk.end_at:
        return "during"
    return "after"


def block_to_dict(b: FocusBlock) -> dict:
    return {
        "id": b.id,
        "title": b.title,
        "start_at": b.start_at,
        "end_at": b.end_at,
        "is_focus": b.is_focus,
        "source": b.source,
    }
