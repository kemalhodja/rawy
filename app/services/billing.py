"""
Monetizasyon: etkin plan, ses yükleme kotası (Başlangıç 50/ay), Pro deneme.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, VoiceNote


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def month_bounds_utc() -> tuple[datetime, datetime]:
    """Takvim ayı [start, end) UTC."""
    now = _now_utc()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        end = start.replace(year=now.year + 1, month=1)
    else:
        end = start.replace(month=now.month + 1)
    return start, end


def effective_plan(user: User) -> str:
    """
    Ödenen plan veya aktif Pro deneme.
    starter | pro | team
    """
    p = (getattr(user, "plan", None) or "starter").lower()
    if p == "free":
        p = "starter"
    if p in ("pro", "team"):
        return p
    te = getattr(user, "trial_ends_at", None)
    if te is not None:
        te_aware = te if te.tzinfo else te.replace(tzinfo=timezone.utc)
        if te_aware > _now_utc():
            return "pro"
    return "starter"


def voice_uploads_this_month(db: Session, user_id: int) -> int:
    start, end = month_bounds_utc()
    return (
        db.query(func.count(VoiceNote.id))
        .filter(
            VoiceNote.user_id == user_id,
            VoiceNote.created_at >= start,
            VoiceNote.created_at < end,
        )
        .scalar()
        or 0
    )


def can_upload_voice(db: Session, user: User) -> tuple[bool, dict[str, Any]]:
    """
    Pro / Team / aktif deneme → sınırsız.
    Başlangıç (deneme bitti) → ayda STARTER_VOICE_MONTHLY_LIMIT.
    """
    ep = effective_plan(user)
    used = voice_uploads_this_month(db, user.id)

    if ep in ("pro", "team"):
        return True, {
            "effective_plan": ep,
            "voice_uploads_this_month": used,
            "voice_upload_limit": None,
            "unlimited": True,
        }

    limit = settings.STARTER_VOICE_MONTHLY_LIMIT
    if used >= limit:
        return False, {
            "effective_plan": "starter",
            "voice_uploads_this_month": used,
            "voice_upload_limit": limit,
            "unlimited": False,
            "code": "STARTER_VOICE_LIMIT",
            "message_tr": f"Aylık {limit} ses kaydı sınırına ulaşıldı. Pro veya yıllık plana geçin.",
        }

    return True, {
        "effective_plan": "starter",
        "voice_uploads_this_month": used,
        "voice_upload_limit": limit,
        "unlimited": False,
    }


def subscription_snapshot(db: Session, user: User) -> dict[str, Any]:
    ep = effective_plan(user)
    used = voice_uploads_this_month(db, user.id)
    limit = None if ep in ("pro", "team") else settings.STARTER_VOICE_MONTHLY_LIMIT
    te = getattr(user, "trial_ends_at", None)
    te_active = False
    if te is not None:
        te_aware = te if te.tzinfo else te.replace(tzinfo=timezone.utc)
        te_active = te_aware > _now_utc() and (user.plan or "starter").lower() in (
            "starter",
            "free",
        )
    return {
        "plan": (user.plan or "starter").lower() if (user.plan or "").lower() != "free" else "starter",
        "effective_plan": ep,
        "trial_ends_at": te.isoformat() if te else None,
        "trial_active": te_active,
        "voice_uploads_this_month": used,
        "voice_upload_limit": limit,
        "billing_interval": getattr(user, "billing_interval", None),
    }


def plans_catalog() -> dict[str, Any]:
    """Önceki model tablosu — ödeme entegrasyonu yok, fiyatlandırma bilgisi."""
    return {
        "currency": "USD",
        "trial_days": settings.TRIAL_DAYS,
        "plans": [
            {
                "id": "starter",
                "name": "Başlangıç",
                "price_usd_month": 0,
                "features_tr": [
                    f"Ayda {settings.STARTER_VOICE_MONTHLY_LIMIT} ses kaydı",
                    "Temel transkript",
                    "1 cihaz (önerilen)",
                ],
            },
            {
                "id": "pro",
                "name": "Pro",
                "price_usd_month": 10,
                "price_usd_year": 96,
                "features_tr": [
                    "Sınırsız ses",
                    "AI özet ve bağlantılar",
                    "Çoklu cihaz",
                    "Offline senkron",
                ],
            },
            {
                "id": "team",
                "name": "Takım",
                "price_usd_month_per_seat": 15,
                "features_tr": [
                    "Paylaşımlı notlar",
                    "Toplantı özeti",
                    "Yönetici / admin",
                ],
            },
        ],
    }


def stripe_enabled() -> bool:
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_PRO_MONTHLY)
