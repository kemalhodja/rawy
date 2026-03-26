"""Plan kataloğu ve abonelik özeti (ödeme sağlayıcı entegrasyonu ayrı)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.services.billing import plans_catalog, subscription_snapshot

router = APIRouter()


@router.get("/plans")
def get_plans():
    """Genel fiyatlandırma tablosu (auth gerekmez)."""
    return plans_catalog()


@router.get("/subscription")
def get_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mevcut kullanıcı: etkin plan, deneme, aylık ses kullanımı."""
    return subscription_snapshot(db, current_user)
