"""
Public API - Developer erişimi
API Key ile kimlik doğrulama
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, VoiceNote
from app.services import api_key as api_key_service

router = APIRouter(prefix="/api/v1", tags=["public-api"])


# Public API için dependency
def get_api_user(
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> User:
    """API Key ile kullanıcı doğrulama"""
    if not x_api_key:
        raise HTTPException(401, "API Key gerekli. Header: X-API-Key")
    
    api_key = api_key_service.verify_api_key(db, x_api_key)
    if not api_key:
        raise HTTPException(401, "Gecersiz API Key")
    
    # Rate limit kontrolü
    if not api_key_service.check_rate_limit(db, api_key):
        raise HTTPException(429, "Rate limit asildi. Saatlik limit: " + str(api_key.rate_limit))
    
    return api_key.user


class WebhookPayload(BaseModel):
    event: str
    data: dict


# ========== PUBLIC API ENDPOINTS ==========

@router.get("/me")
def get_current_api_user(
    user: User = Depends(get_api_user),
):
    """API ile erişilen kullanıcı bilgisi"""
    return {
        "id": user.id,
        "email": user.email,
        "plan": user.plan,
        "timezone": user.timezone
    }


@router.get("/voices")
def list_voices(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_api_user),
):
    """Ses notlarını listele"""
    notes = (
        db.query(VoiceNote)
        .filter(VoiceNote.user_id == user.id)
        .order_by(VoiceNote.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    
    return {
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "transcript": n.transcript,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "duration": n.duration,
                "language": n.language
            }
            for n in notes
        ],
        "total": len(notes),
        "limit": limit,
        "offset": offset
    }


@router.get("/voices/{note_id}")
def get_voice(
    note_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_api_user),
):
    """Ses notu detayı"""
    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == note_id, VoiceNote.user_id == user.id)
        .first()
    )
    
    if not note:
        raise HTTPException(404, "Not bulunamadi")
    
    return {
        "id": note.id,
        "title": note.title,
        "transcript": note.transcript,
        "summary": note.meeting_summary,
        "action_items": note.meeting_action_items,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "duration": note.duration,
        "language": note.language,
        "tags": note.tags
    }


@router.post("/webhook/test")
def test_webhook(
    payload: WebhookPayload,
    user: User = Depends(get_api_user),
):
    """Webhook test et"""
    return {
        "message": "Webhook alindi",
        "received": payload.dict(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ========== API KEY MANAGEMENT (Auth required) ==========

class ApiKeyCreate(BaseModel):
    name: str
    rate_limit: int = 1000
    webhook_url: str = None
    expires_days: int = None


class ApiKeyUpdate(BaseModel):
    webhook_url: str = None


@router.get("/keys", tags=["api-keys"])
def list_api_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kullanıcının API key'lerini listele"""
    keys = api_key_service.get_user_api_keys(db, current_user.id)
    
    return [
        {
            "id": k.id,
            "name": k.name,
            "prefix": k.key_prefix + "...",
            "rate_limit": k.rate_limit,
            "usage_count": k.usage_count,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "webhook_url": k.webhook_url
        }
        for k in keys
    ]


@router.post("/keys", tags=["api-keys"])
def create_api_key(
    data: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Yeni API key oluştur. Key sadece bir kez gösterilir!"""
    api_key, full_key = api_key_service.create_api_key(
        db,
        user_id=current_user.id,
        name=data.name,
        rate_limit=data.rate_limit,
        webhook_url=data.webhook_url,
        expires_days=data.expires_days
    )
    
    return {
        "message": "API Key olusturuldu. Bu keyi saklayin, bir daha gosterilmeyecek!",
        "api_key": full_key,
        "id": api_key.id,
        "name": api_key.name,
        "prefix": api_key.key_prefix + "...",
        "rate_limit": api_key.rate_limit
    }


@router.delete("/keys/{key_id}", tags=["api-keys"])
def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """API key sil"""
    success = api_key_service.delete_api_key(db, key_id, current_user.id)
    if not success:
        raise HTTPException(404, "API Key bulunamadi")
    return {"message": "API Key silindi"}


@router.patch("/keys/{key_id}", tags=["api-keys"])
def update_api_key(
    key_id: int,
    data: ApiKeyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """API key güncelle (webhook)"""
    api_key = api_key_service.update_webhook(
        db, key_id, current_user.id, data.webhook_url
    )
    if not api_key:
        raise HTTPException(404, "API Key bulunamadi")
    return {"message": "Webhook guncellendi"}


from datetime import datetime, timezone
