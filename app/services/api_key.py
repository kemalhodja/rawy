"""
API Key yönetimi ve doğrulama
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ApiKey, User


def generate_api_key() -> tuple[str, str]:
    """
    API key oluştur. Dönen: (full_key, key_hash)
    """
    # 32 byte'lık rastgele key
    full_key = "rw_" + secrets.token_urlsafe(32)
    
    # Hash için salt + sha256
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    
    return full_key, key_hash


def create_api_key(
    db: Session,
    user_id: int,
    name: str,
    rate_limit: int = 1000,
    webhook_url: str = None,
    expires_days: int = None
) -> tuple[ApiKey, str]:
    """
    Yeni API key oluştur. Dönen: (api_key_object, full_key)
    full_key sadece bir kez gösterilir!
    """
    full_key, key_hash = generate_api_key()
    
    # Prefix (son 8 karakter hariç)
    key_prefix = full_key[:10]
    
    # Expiration
    expires_at = None
    if expires_days:
        expires_at = datetime.now(timezone.utc) + datetime.timedelta(days=expires_days)
    
    api_key = ApiKey(
        user_id=user_id,
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        rate_limit=rate_limit,
        webhook_url=webhook_url,
        expires_at=expires_at,
        is_active=True
    )
    
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    
    return api_key, full_key


def verify_api_key(db: Session, key: str) -> Optional[ApiKey]:
    """
    API key doğrula. Geçerliyse ApiKey nesnesi döner.
    """
    if not key or not key.startswith("rw_"):
        return None
    
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    
    api_key = (
        db.query(ApiKey)
        .filter(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True
        )
        .first()
    )
    
    if not api_key:
        return None
    
    # Expiration kontrolü
    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        return None
    
    # Kullanım güncelle
    api_key.last_used_at = datetime.now(timezone.utc)
    api_key.usage_count += 1
    db.commit()
    
    return api_key


def get_user_api_keys(db: Session, user_id: int) -> list[ApiKey]:
    """Kullanıcının API key'lerini getir"""
    return (
        db.query(ApiKey)
        .filter(ApiKey.user_id == user_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


def revoke_api_key(db: Session, key_id: int, user_id: int) -> bool:
    """API key'i iptal et"""
    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.user_id == user_id)
        .first()
    )
    
    if api_key:
        api_key.is_active = False
        db.commit()
        return True
    return False


def delete_api_key(db: Session, key_id: int, user_id: int) -> bool:
    """API key'i tamamen sil"""
    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.user_id == user_id)
        .first()
    )
    
    if api_key:
        db.delete(api_key)
        db.commit()
        return True
    return False


def update_webhook(db: Session, key_id: int, user_id: int, webhook_url: str) -> Optional[ApiKey]:
    """Webhook URL güncelle"""
    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.user_id == user_id)
        .first()
    )
    
    if api_key:
        api_key.webhook_url = webhook_url
        db.commit()
        db.refresh(api_key)
    
    return api_key


def check_rate_limit(db: Session, api_key: ApiKey) -> bool:
    """
    Rate limit kontrolü. Limit aşıldıysa False döner.
    """
    # Saatlik window kontrolü (basit implementasyon)
    if api_key.usage_count >= api_key.rate_limit:
        # Son kullanım 1 saatten eskiyse reset
        if api_key.last_used_at:
            hour_ago = datetime.now(timezone.utc) - datetime.timedelta(hours=1)
            if api_key.last_used_at < hour_ago:
                api_key.usage_count = 0
                db.commit()
                return True
        return False
    return True
